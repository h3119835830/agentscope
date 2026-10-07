"""Conservative compiler-backed rule analysis. Never grants execution authority."""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import PurePosixPath
import yaml

VERSION = "policy-normalization.v1"
SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_normalization_runs(
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), stage TEXT NOT NULL,
 owner_id TEXT NOT NULL, report_json TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(task_id,stage,owner_id,id));
CREATE INDEX IF NOT EXISTS normalization_task_owner ON policy_normalization_runs(task_id,stage,owner_id);
CREATE TABLE IF NOT EXISTS policy_statement_rule_links(
 task_id TEXT NOT NULL REFERENCES tasks(id), statement_id TEXT NOT NULL,
 report_id TEXT NOT NULL REFERENCES policy_normalization_runs(id), logical_rule_id TEXT NOT NULL,
 bundle_hash TEXT NOT NULL, clause_id INTEGER NOT NULL, relation TEXT NOT NULL,
 link_json TEXT NOT NULL, PRIMARY KEY(task_id,statement_id,report_id,logical_rule_id,bundle_hash,clause_id));
"""


def digest(value):
    data = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def mode_for(task_id):
    from .. import db
    with db.connect() as con:
        row = con.execute("SELECT state_json FROM managed_tasks WHERE task_id=?", (task_id,)).fetchone()
    if row:
        return json.loads(row[0]).get("normalization_mode", "legacy")
    return configured_mode()


def configured_mode():
    mode = os.getenv("AGENTSCOPE_POLICY_NORMALIZATION", "observe")
    if mode not in ("legacy", "observe", "deduplicate"):
        raise ValueError("Invalid policy normalization mode")
    return mode


def partition(name):
    if name.startswith("bootstrap-"): return "startup"
    if name == "runtime-file-protection": return "runtime"
    return "platform:" + name


def eligible(rule):
    s = rule.get("semantics", {})
    target = rule.get("target_pattern", "")
    return (s.get("schema") == "actplane.rule-semantics.v1"
        and rule.get("effect") == "block" and rule.get("target_kind") == "file"
        and rule.get("clause_op") in ("write", "unlink", "read", "open")
        and 0 < len(target.encode()) < 64
        and target == str(PurePosixPath(target))
        and target.startswith("/") and not any(c in target for c in "*?[]")
        and ".." not in PurePosixPath(target).parts
        and rule.get("target_arg") is None
        and s.get("target_match") == 0
        and all(isinstance(s.get(field),list) for field in ("required_labels","forbidden_labels","source_bindings"))
        and s.get("target_literal") == target and s.get("condition_kind") == 0
        and s.get("condition_negated") is False
        and s.get("gate_mask") == "0" and s.get("since_mask") == "0"
        and s.get("has_transforms") is False)


@lru_cache(maxsize=8)
def _engine_digest(path, size, modified):
    return hashlib.sha256(__import__('pathlib').Path(path).read_bytes()).hexdigest()


def engine_digest():
    from ..config import ACTPLANE_BIN
    if not ACTPLANE_BIN.is_file(): return "unavailable-test-runtime"
    stat=ACTPLANE_BIN.stat()
    return _engine_digest(str(ACTPLANE_BIN.resolve()), stat.st_size, stat.st_mtime_ns)


def identity(rule, task_id, workspace):
    return {"schema": VERSION, "engine":engine_digest(), "task": task_id, "workspace": workspace,
        "authority": partition(rule["name"]), "lifecycle": "task-lifetime",
        "operation": rule.get("clause_op"), "effect": rule.get("effect"),
        "target_kind": rule.get("target_kind"), "target": rule.get("target_pattern"),
        "argument": rule.get("target_arg"), "semantics": rule.get("semantics")}


def replace_policy(bundle, raw, normalized):
    data = yaml.safe_load(bundle)
    if data.get("policy", "").rstrip() != raw.rstrip():
        raise ValueError("Policy YAML and DSL diverge before normalization")
    data["policy"] = normalized
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def stable_compiler(compiler):
    # The compile tool's temporary filename is not policy input or semantics.
    return {key:value for key,value in compiler.items() if key not in ('policy_ref',)}


def analyse(dsl, compiler, task_id, workspace, mode="observe"):
    if mode not in ("observe", "deduplicate"): raise ValueError("Invalid analysis mode")
    if compiler.get("ok") is not True: raise ValueError("Original policy did not compile")
    lines = dsl.splitlines(keepends=True)
    groups = {}
    for rule in compiler.get("rules", []):
        if not rule.get("clause_start_line") or not rule.get("clause_text"):
            raise ValueError("Compiler lacks reliable clause source metadata")
        start, end = rule["clause_start_line"], rule.get("clause_end_line", rule["clause_start_line"])
        if not (0 < start <= end <= len(lines)) or "".join(lines[start-1:end]).rstrip() != rule["clause_text"].rstrip():
            raise ValueError("Compiler clause source does not match original DSL")
        groups.setdefault((start, end), []).append(rule)
    clauses, seen, removed, all_by_rule = [], {}, set(), {}
    for span, lowered in groups.items():
        rule = lowered[0]; safe = len(lowered) == 1 and eligible(rule)
        key = digest(identity(rule, task_id, workspace)) if safe else digest({"task":task_id,"source":rule.get("source_text"),"span":span,"rules":lowered})
        previous = seen.get(key) if safe else None
        entry = {"logical_rule_id":key,"name":rule["name"],"target":rule.get("target_pattern"),
            "operation":rule.get("clause_op"),"reason":rule.get("reason"),"source_start_line":span[0],
            "source_end_line":span[1],"rule_start_line":rule["source_start_line"],"rule_end_line":rule["source_end_line"],
            "raw_clause_ids":[x["rule_id"] for x in lowered],"eligible":safe,
            "relation":"duplicate" if previous else "new" if safe else "unknown",
            "retained_source_line":previous["source_start_line"] if previous else span[0]}
        clauses.append(entry); all_by_rule.setdefault(rule["source_start_line"], []).append(entry)
        if previous and mode == "deduplicate": removed.update(range(span[0], span[1]+1))
        elif safe: seen[key] = entry
    for entries in all_by_rule.values():
        if all(x["source_start_line"] in removed for x in entries):
            removed.update(range(entries[0]["rule_start_line"], entries[0]["rule_end_line"]+1))
    normalized = "".join(line for i,line in enumerate(lines,1) if i not in removed)
    relations = []
    for i,a in enumerate(clauses):
        for b in clauses[i+1:]:
            if a["logical_rule_id"] == b["logical_rule_id"]: continue
            ta,tb = a["target"] or "",b["target"] or ""
            if a["operation"] != b["operation"]: continue
            cover = any(tree.endswith("/**") and not any(c in tree[:-3] for c in "*?[]") and literal.startswith(tree[:-2]) and not any(c in literal for c in "*?[]") for tree,literal in ((ta,tb),(tb,ta)))
            if ta == tb or cover:
                relations.append({"relation":"contains" if cover else "overlap", "left":a["logical_rule_id"],"right":b["logical_rule_id"],"basis":"registered literal subtree" if cover else "same target; distinct identity or conditions", "action":"retain_both"})
    return {"schema":VERSION,"task_id":task_id,"workspace":workspace,"mode":mode,"status":"analysed","raw_dsl":dsl,"normalized_dsl":normalized,
        "raw_dsl_hash":digest(dsl),"normalized_dsl_hash":digest(normalized),
        "raw_clause_count":len(compiler.get("rules",[])),"effective_clause_count":None,
        "duplicate_clause_count":sum(x["relation"]=="duplicate" for x in clauses),
        "clauses":clauses,"relations":relations,"raw_compiler":stable_compiler(compiler)}


def complete(report, compiler):
    # All surviving raw clauses must retain the same lowered semantics, including
    # exceptions and gates. Simple duplicates may only reduce multiplicity.
    def signatures(info):
        return {digest({k:r.get(k) for k in ("effect","clause_op","target_kind","target_pattern","target_arg","semantics")}) for r in info.get("rules", [])}
    if signatures(report["raw_compiler"]) != signatures(compiler):
        raise ValueError("Normalization changed compiled enforcement semantics")
    by_line = {}
    for rule in compiler.get("rules", []):
        by_line.setdefault(rule.get("clause_text", "").strip(), []).append(rule)
    for entry in report["clauses"]:
        original = next(r for r in report["raw_compiler"]["rules"] if r["rule_id"] == entry["raw_clause_ids"][0])
        matches = by_line.get(original["clause_text"].strip(), [])
        same = [r for r in matches if r["name"] == entry["name"]]
        if entry["eligible"]:
            matches = [r for r in matches if digest(identity(r, report["task_id"], report["workspace"])) == entry["logical_rule_id"]]
            selected = [r for r in same if r in matches] or matches[:1]
        else:
            selected = same
        if not selected: raise ValueError("Normalized clause lost source lineage")
        entry["clause_ids"] = [r["rule_id"] for r in selected]
        entry["compiled_names"] = sorted({r["name"] for r in selected})
        entry["compiled_refs"] = [{"clause_id":r["rule_id"], "name":r["name"], "operation":r["clause_op"], "target":r["target_pattern"]} for r in selected]
    report["effective_clause_count"] = len(compiler.get("rules", []))
    report["execution_hash"] = digest(sorted(signatures(compiler)))
    report["compiler_hash"] = digest(stable_compiler(compiler))
    report["id"] = digest({k:v for k,v in report.items() if k != "id"})
    return report


def build(dsl, bundle, task_id, version, mode, compile_fn):
    status, raw, error = compile_fn(bundle, task_id, version)
    if status != "compiled": raise ValueError("Original policy compile failed: " + str(error))
    if mode == "legacy": return dsl, bundle, raw, None
    report = analyse(dsl, raw, task_id, str(__import__('pathlib').Path(workspace_from_task(task_id))), mode)
    normalized = report["normalized_dsl"]
    actual_bundle = replace_policy(bundle, dsl, normalized) if normalized != dsl else bundle
    compiled = raw
    if actual_bundle != bundle:
        status, compiled, error = compile_fn(actual_bundle, task_id, version)
        if status != "compiled": raise ValueError("Normalized policy compile failed: " + str(error))
    complete(report, compiled)
    report["raw_bundle"] = bundle
    report["bundle_hash"] = digest(actual_bundle)
    report["build_version"] = version
    report["engine_hash"] = engine_digest()
    report["id"] = digest({k:v for k,v in report.items() if k!="id"})
    return normalized, actual_bundle, compiled, report


def workspace_from_task(task_id):
    from .. import db
    with db.connect() as con:
        row = con.execute("SELECT workspace FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row: raise ValueError("Unknown normalization task")
    return row[0]


def persist(con, task_id, stage, owner_id, report):
    if not report: return
    from .. import db
    con.execute("INSERT OR IGNORE INTO policy_normalization_runs VALUES(?,?,?,?,?,?)", (report["id"], task_id, stage, owner_id, json.dumps(report,ensure_ascii=False), db.now()))


def link_record(con, task_id, record, report, startup_names=None, persist_links=False):
    if not report:
        record["normalization"] = {"status":"legacy_unanalysed","links":[]}; return record
    targets = set(record.get("targets", []))
    clauses = [e for e in report["clauses"] if e["target"] in targets and (startup_names is None or e["name"] in startup_names)]
    links = []
    first_loads={}
    for logical_id in {e['logical_rule_id'] for e in clauses}:
        receipts=[json.loads(row[0]).get('current_loading') for row in con.execute(
            'SELECT link_json FROM policy_statement_rule_links WHERE task_id=? AND logical_rule_id=?',
            (task_id,logical_id))]
        receipts=[receipt for receipt in receipts if receipt and isinstance(receipt.get('version'),int)]
        first_loads[logical_id]=min(receipts,key=lambda receipt:receipt['version']) if receipts else None
    for e in clauses:
        relation = "reuses" if record.get("effect") in ("no_change","guidance_only") or (e["relation"]=="duplicate" and report["mode"]=="deduplicate") else "equivalent_retained" if e["relation"]=="duplicate" else "new"
        if e["relation"]=="unknown": relation="unknown"
        if record.get("stage")=="runtime" and partition(e["name"])=="startup": relation="baseline_covered"
        for ref in e.get("compiled_refs",[]):
            link={"logical_rule_id":e["logical_rule_id"],"bundle_hash":report["bundle_hash"],"clause_id":ref["clause_id"],"operation":ref["operation"],"target":ref["target"],"relation":relation,"reason":e["reason"],"source_rule":e["name"],"compiled_name":ref["name"]}
            link['first_loading']=first_loads[e['logical_rule_id']]
            links.append(link)
    relations=[v for v in report.get("relations",[]) if v["left"] in {e["logical_rule_id"] for e in clauses} or v["right"] in {e["logical_rule_id"] for e in clauses}]
    related=[]
    for logical_id in {e["logical_rule_id"] for e in clauses}:
        related.extend(row[0] for row in con.execute("SELECT DISTINCT statement_id FROM policy_statement_rule_links WHERE task_id=? AND logical_rule_id=? AND statement_id!=?",(task_id,logical_id,record["id"])))
    record["normalization"]={"status":"analysed","report_id":report["id"],"mode":report["mode"],"links":links,"relations":relations,"related_statements":sorted(set(related))}
    return record


def persist_record_links(con, task_id, record):
    normal=record.get("normalization",{})
    if normal.get("status")!="analysed": return
    for link in normal["links"]:
        if not link.get("current_loading"): continue
        for reference in [link]+link.get('inherited_loading',[]):
            con.execute("INSERT OR IGNORE INTO policy_statement_rule_links VALUES(?,?,?,?,?,?,?,?)", (task_id,record["id"],normal["report_id"],link["logical_rule_id"],reference["bundle_hash"],reference["clause_id"],link["relation"],json.dumps(link,ensure_ascii=False)))


def verify_proof(dsl, bundle, task_id, workspace, report, compile_fn):
    if not report or report.get("schema")!=VERSION: raise ValueError("Missing normalization proof")
    if digest(bundle)!=report.get("bundle_hash") or digest(dsl)!=report.get("normalized_dsl_hash"):
        raise ValueError("Normalization package hash mismatch")
    raw=report.get("raw_dsl","");raw_bundle=report.get("raw_bundle","")
    if digest(raw)!=report.get("raw_dsl_hash"):raise ValueError("Original DSL hash mismatch")
    replace_policy(raw_bundle,raw,raw)
    status,compiled,error=compile_fn(raw_bundle,task_id,0)
    if status!='compiled':raise ValueError("Broker original policy check failed: "+str(error))
    actual=analyse(raw,compiled,task_id,workspace,report['mode'])
    if actual['normalized_dsl']!=dsl:raise ValueError("Broker normalization result mismatch")
    replace_policy(bundle,dsl,dsl)
    status,effective,error=compile_fn(bundle,task_id,1)
    if status!='compiled':raise ValueError("Broker normalized policy check failed: "+str(error))
    complete(actual,effective)
    if actual['execution_hash']!=report.get('execution_hash'):raise ValueError("Broker execution signature mismatch")
    # The Broker also verifies lineage, not only execution. Otherwise a valid
    # package could carry invented source-to-clause or overlap relationships.
    fields=('task_id','workspace','mode','raw_clause_count','effective_clause_count',
        'duplicate_clause_count','clauses','relations','compiler_hash')
    if any(actual[field]!=report.get(field) for field in fields):
        raise ValueError("Broker normalization lineage mismatch")
    if engine_digest()!=report.get('engine_hash'):raise ValueError("Compiler changed after candidate analysis")
    return effective
