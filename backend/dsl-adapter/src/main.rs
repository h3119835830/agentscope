//! A control-plane adapter over ActPlane's parser, not another DSL grammar.
use actplane_ifc_compiler::{ast::*, compile_str, parse};
use serde_json::{Value, json};
use std::io::{self, Read};

// ActPlane's lexer preserves backslashes literally; JSON escaping would alter
// path patterns and reasons. A parsed string cannot contain an embedded quote.
fn quoted(s: &str) -> String { format!("\"{}\"",s) }
fn op(o: Op) -> &'static str { match o { Op::Exec=>"exec",Op::Read=>"read",Op::Write=>"write",Op::Unlink=>"unlink",Op::Connect=>"connect",Op::Recv=>"recv",Op::Open=>"open" } }
fn kind(k: Kind) -> &'static str { match k { Kind::File=>"file",Kind::Endpoint=>"endpoint",Kind::Exec=>"exec" } }
fn effect(e: Effect) -> &'static str { match e { Effect::Block=>"block",Effect::Kill=>"kill",Effect::Notify=>"notify" } }
fn label(ns: &str, value: &str) -> String { format!("{ns}_{value}") }
fn expr(e: &Expr, ns: &str) -> String {
    // The real parser is left associative and does not accept parentheses.
    match e { Expr::True=>"true".into(),Expr::Label(v)=>label(ns,v),Expr::Not(v)=>format!("not {}",label(ns,v)),Expr::And(a,b)=>format!("{} and {}",expr(a,ns),expr(b,ns)),Expr::Or(a,b)=>format!("{} or {}",expr(a,ns),expr(b,ns)) }
}
fn uses_history(e: &Expr, p: &Policy) -> bool {
    match e {
        Expr::True=>false,
        // A specific exec source marks its descendant subtree. The wildcard
        // executor identity is the only source label without a lineage filter.
        Expr::Label(v)|Expr::Not(v)=>p.sources.iter().any(|s|s.label==*v && (s.kind!=Kind::Exec || !matches!(s.pattern.as_str(),"*"|"**"|"**/*"))) || p.xforms.iter().any(|x|x.label==*v),
        Expr::And(a,b)|Expr::Or(a,b)=>uses_history(a,p)||uses_history(b,p),
    }
}
fn labels_declared(e: &Expr, declared: &std::collections::HashSet<&str>) -> bool {
    match e {Expr::True=>true,Expr::Label(v)|Expr::Not(v)=>declared.contains(v.as_str()),Expr::And(a,b)|Expr::Or(a,b)=>labels_declared(a,declared)&&labels_declared(b,declared)}
}
fn path(value: &str, resources: &[String]) -> String {
    for (i,root) in resources.iter().enumerate() {
        if value==root { return format!("/w/{i}"); }
        if let Some(rest)=value.strip_prefix(&(root.clone()+"/")) { return format!("/w/{i}/{rest}"); }
    }
    value.into()
}
fn pinned_runtime_unsupported(bytes: &[u8]) -> Result<Vec<&'static str>,String> {
    // PinnedEngine::full_profile reserves all hooks and write/open sinks but
    // excludes FEAT_PATH_CONTAINS and FEAT_PATH_SUFFIX. Inspect ActPlane's real
    // lowered taint_config ABI, including file sources and target exceptions.
    // Fail closed on ABI drift rather than guessing from source-text globs.
    const UPDATES:usize=320;const RULES:usize=128;
    const UPDATE_SIZE:usize=144;const RULE_SIZE:usize=224;
    if bytes.len()!=8+UPDATES*UPDATE_SIZE+RULES*RULE_SIZE {return Err("Unknown ActPlane taint_config ABI; runtime capability check unavailable".into());}
    let count=|offset|u32::from_ne_bytes(bytes[offset..offset+4].try_into().unwrap()) as usize;
    let nu=count(0);let nr=count(4);
    if nu>UPDATES || nr>RULES {return Err("Invalid ActPlane taint_config counts".into());}
    let mut contains=false;let mut suffix=false;
    let mut inspect=|m| {contains|=m==4;suffix|=m==2;};
    for i in 0..nu {let offset=8+i*UPDATE_SIZE;if matches!(bytes[offset],1|2) {inspect(bytes[offset+1]);}}
    for i in 0..nr {let offset=8+UPDATES*UPDATE_SIZE+i*RULE_SIZE;if matches!(bytes[offset],1|2) {inspect(bytes[offset+1]);if bytes[offset+2]==3 {inspect(bytes[offset+4]);}}}
    let mut out=Vec::new();if contains {out.push("文件路径包含匹配");}if suffix {out.push("文件路径后缀匹配");}Ok(out)
}
fn event(o: Op, pattern: &str, arg: Option<&String>, resources: &[String]) -> String {
    let pattern=if matches!(o,Op::Read|Op::Write|Op::Unlink|Op::Open) {path(pattern,resources)} else {pattern.into()};
    format!("{} {}{}",op(o),quoted(&pattern),arg.map(|s|format!(" {}",quoted(s))).unwrap_or_default())
}
fn clause(c: &Clause, ns: &str, resources: &[String]) -> String {
    let target=if c.target.kind==Kind::File {path(&c.target.pattern,resources)} else {c.target.pattern.clone()};
    let mut s=format!("  {} {} {}{}{} if {}",effect(c.effect),op(c.op),if c.target.kind==Kind::Exec {""} else {kind(c.target.kind)},if c.target.kind==Kind::Exec {""} else {" "},quoted(&target),expr(&c.when,ns));
    if let Some(arg)=&c.target.arg {
        // argv tokens precede `if`, rather than becoming part of the path.
        s=format!("  {} {} {} {} if {}",effect(c.effect),op(c.op),quoted(&target),quoted(arg),expr(&c.when,ns));
    }
    if let Some(cond)=&c.unless {
        let text=match cond {
            Cond::Target{negate,pattern}=>format!("target {}{}",if *negate {"not "} else {""},quoted(&path(pattern,resources))),
            Cond::LineageIncludes{exec}=>format!("lineage-includes exec {}",quoted(exec)),
            Cond::After{gate_op,gate_pattern,gate_exit,since}=>{
                let mut t=format!("after {}",event(*gate_op,gate_pattern,None,resources));
                if let Some(exit)=gate_exit {t+=&format!(" exits {exit}");}
                if !since.is_empty() {t+=" since ";t+=&since.iter().map(|(o,p,a)|event(*o,p,a.as_ref(),resources)).collect::<Vec<_>>().join(" or ");}
                t
            }
        };
        s+=&format!(" unless {text}");
    }
    s
}

fn adapt(v: &Value) -> Result<Value,String> {
    let src=v["dsl"].as_str().ok_or("Missing DSL")?;
    if src.len()>60000 {return Err("DSL exceeds 60000 bytes".into());}
    let ns=v["namespace"].as_str().ok_or("Missing namespace")?;
    if ns.is_empty() || ns.len()>48 || !ns.bytes().all(|c|c.is_ascii_alphanumeric()||c==b'_') {return Err("Invalid namespace".into());}
    let resources:Vec<String>=v["resources"].as_array().map(|a|a.iter().filter_map(|v|v.as_str().map(String::from)).collect()).unwrap_or_default();
    if src.contains("${") || src.contains("{{") {return Err("DSL 包含未解决的上下文占位符；请先填写具体目标再校验".into());}
    let p=parse::parse(src).map_err(|error| {
        // Upstream reports token errors without offsets. Locate the last
        // accepted line prefix using that same parser; do not invent a column.
        let lines:Vec<&str>=src.lines().collect();let mut accepted=0;
        for i in 1..lines.len() {if parse::parse(&lines[..i].join("\n")).is_ok() {accepted=i;}}
        format!("第 {} 行附近（ActPlane 未提供列号）：{}",(accepted+1).min(lines.len().max(1)),error)
    })?;
    if p.rules.is_empty() {return Err("DSL must contain at least one rule".into());}
    let mut names=std::collections::HashSet::new();
    for r in &p.rules {if !names.insert(r.name.clone()) {return Err(format!("Duplicate rule name: {}",r.name));}}
    let declared:std::collections::HashSet<_>=p.sources.iter().map(|s|s.label.as_str()).collect();
    if p.labels.iter().any(|s|!declared.contains(s.as_str())) || p.xforms.iter().any(|x|!declared.contains(x.label.as_str())) || p.rules.iter().flat_map(|r|&r.clauses).any(|c|!labels_declared(&c.when,&declared)) {return Err("Every label must be declared by this document's sources".into());}
    let mut dsl=String::new();
    for s in &p.sources {
        let pattern=if s.kind==Kind::File {path(&s.pattern,&resources)} else {s.pattern.clone()};
        dsl+=&format!("source {} = {} {}\n",label(ns,&s.label),kind(s.kind),quoted(&pattern));
    }
    for x in &p.xforms {dsl+=&format!("{} {} by exec {}\n",if x.endorse {"endorse"} else {"declassify"},label(ns,&x.label),quoted(&x.gate));}
    let lines:Vec<&str>=src.lines().collect();
    // Only locate source spans here. ActPlane's AST is authoritative for syntax.
    let mut records=Vec::new();
    for (index,r) in p.rules.iter().enumerate() {
        let start=lines.iter().position(|l|l.trim().strip_prefix("rule").is_some_and(|s|s.starts_with(char::is_whitespace)&&s.split(':').next().unwrap_or("").trim()==r.name)).ok_or("Cannot locate original rule declaration")?;
        let end=lines.iter().enumerate().skip(start+1).find(|(_,l)|{let t=l.trim();t.starts_with("rule ")||t.starts_with("source ")||t.starts_with("declassify ")||t.starts_with("endorse ")}).map(|(i,_)|i).unwrap_or(lines.len());
        let compiled_name=format!("{ns}-{}",r.name);
        dsl+=&format!("\n# actplane-rule-source ref={ns}:{index}{}\nrule {compiled_name}:\n",if v["locked"].as_bool().unwrap_or(false) {" mode=locked"} else {""});
        let mut effects=Vec::new();let mut types=Vec::new();let mut clauses=Vec::new();
        for c in &r.clauses {
            let rendered=clause(c,ns,&resources);dsl+=&(rendered.clone()+"\n");
            let ty=if matches!(c.unless,Some(Cond::After{..}|Cond::LineageIncludes{..})) || uses_history(&c.when,&p) {"cross_event"} else {"per_event"};
            if !effects.contains(&effect(c.effect)) {effects.push(effect(c.effect));}
            if !types.contains(&ty) {types.push(ty);}
            clauses.push(json!({"effect":effect(c.effect),"operation":op(c.op),"target":c.target.pattern,"event_type":ty,"effective_clause":rendered}));
        }
        dsl+=&format!("  because {}\n",quoted(&r.reason));
        records.push(json!({"rule_name":r.name,"compiled_name":compiled_name,"source_ref":format!("{ns}:{index}"),"source_start_line":start+1,"source_end_line":end,"original_dsl":lines[start..end].join("\n"),"effects":effects,"event_types":types,"clauses":clauses,"reason":r.reason}));
    }
    // Round-trip the complete document, including transforms and gate invalidation.
    // Lowering is performed by the real compiler after resource binding.
    let compiled=compile_str(&dsl)?;
    let unsupported=pinned_runtime_unsupported(&compiled.bytes)?;
    Ok(json!({"schema":"agentscope.dsl-document.v1","effective_dsl":dsl,"rules":records,"namespace":ns,"pinned_runtime_unsupported":unsupported}))
}
fn main() {
    let mut src=String::new();
    let result=io::stdin().take(300000).read_to_string(&mut src).map_err(|e|e.to_string())
        .and_then(|_|serde_json::from_str(&src).map_err(|e|e.to_string())).and_then(|v|adapt(&v));
    match result {Ok(v)=>println!("{}",json!({"ok":true,"document":v})),Err(e)=>{println!("{}",json!({"ok":false,"error":e}));std::process::exit(1);}}
}

#[cfg(test)]
mod tests {
    use super::*;
    fn prepare(s:&str)->Value {adapt(&json!({"dsl":s,"namespace":"doc1","resources":["/home/happy/projects/example"]})).unwrap()}
    #[test] fn isolates_labels_and_maps_paths() {
        let v=prepare("source AGENT = exec \"**\"\nrule protect:\n block write file \"/home/happy/projects/example/a\" if AGENT\n notify read file \"/home/happy/projects/example/b\" if AGENT\n because \"保护\"\n");
        assert!(v["effective_dsl"].as_str().unwrap().contains("/w/0/a"));
        assert_eq!(v["rules"][0]["effects"],json!(["block","notify"]));
        assert_eq!(v["rules"][0]["event_types"],json!(["per_event"]));
        assert!(v["rules"][0]["original_dsl"].as_str().unwrap().contains("/home/happy/projects/example/a"));
    }
    #[test] fn gate_and_taint_are_cross_event() {
        let v=prepare("source AGENT = exec \"**\"\nsource SECRET = file \"**/.env\"\nrule gate:\n kill exec \"git\" \"commit\" if AGENT unless after exec \"pytest\" exits 0 since write \"src/**\" or write \"tests/**\"\n because \"Run tests\"\nrule flow:\n block connect endpoint \"10.0.0.1\" if SECRET\n because \"Secret\"\n");
        for r in v["rules"].as_array().unwrap() {assert_eq!(r["event_types"],json!(["cross_event"]));}
        assert!(v["effective_dsl"].as_str().unwrap().contains("exits 0 since write"));
        let lineage=prepare("source A = exec \"agent.py\"\nrule descendants:\n kill exec \"git\" if A\n because \"Subtree identity\"");
        assert_eq!(lineage["rules"][0]["event_types"],json!(["cross_event"]));
    }
    #[test] fn pinned_capabilities_come_from_real_lowering() {
        let exact=prepare("source A = exec \"**\"\nsource F = file \"/w/0/context\"\nrule r:\n kill exec \"git\" \"commit\" if A unless after exec \"pytest\" exits 0 since write \"/w/0/src/**\"\n notify read file \"/w/0/public\" if F\n because \"x\"");
        assert_eq!(exact["pinned_runtime_unsupported"],json!([]));
        let suffix=prepare("source A = exec \"**\"\nsource F = file \"**/.env\"\nrule r:\n block read file \"/w/0/a\" if A\n because \"x\"");
        assert_eq!(suffix["pinned_runtime_unsupported"],json!(["文件路径后缀匹配"]));
        let contains=prepare("source A = exec \"**\"\nrule r:\n block write file \"/w/0/**\" if A unless target \"**/src/**\"\n because \"x\"");
        assert_eq!(contains["pinned_runtime_unsupported"],json!(["文件路径包含匹配"]));
        assert!(pinned_runtime_unsupported(&[0;8]).is_err());
    }
    #[test] fn duplicate_and_foreign_labels_are_rejected() {
        assert!(adapt(&json!({"dsl":"source A = exec \"**\"\nrule r:\n block exec \"git\" if FOREIGN\n because \"x\"","namespace":"d"})).is_err());
    }
    #[test] fn complete_boolean_transform_and_exception_round_trip() {
        let v=prepare("source A = exec \"**\"\nsource B = file \"**/.env\"\nsource C = exec \"**/trusted\"\ndeclassify B by exec \"sanitizer\"\nrule p:\n block exec \"git\" if A and not C or B unless target not \"**/safe\"\n notify read file \"**/public\"\n kill exec \"curl\" if A unless lineage-includes exec \"approved\"\n because \"Reason\"\n");
        let p=parse::parse(v["effective_dsl"].as_str().unwrap()).unwrap();
        assert_eq!(p.rules[0].clauses[0].when,Expr::Or(Box::new(Expr::And(Box::new(Expr::Label("doc1_A".into())),Box::new(Expr::Not("doc1_C".into())))),Box::new(Expr::Label("doc1_B".into()))));
        assert_eq!(p.rules[0].clauses[1].when,Expr::True);
        assert_eq!(p.xforms[0].label,"doc1_B");
    }
}
