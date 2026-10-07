"""Deterministic restricted PolicyIR -> DSL. Models cannot supply executable DSL."""
import json
from pathlib import Path
from .. import db
from ..services.policy import make_dsl, quote_dsl
from ..services import policy_normalization as normalization
from .models import Draft
from .scene import context, digest
from .library import approved_record

CAPABILITIES = {"version": "bootstrap-ir/1", "admission_boundary": {"assessed_by_pi": "Whether necessary OS safety constraints can be enforced with evidence-resolved targets", "assessed_by_executor": "Task completion, implementation feasibility and business test outcomes", "nonblocking_task_risks": "Record in guidance; preserving safety does not require predicting that the task will succeed", "unresolved": "Only necessary OS safety constraints with unknown targets or unsupported enforcement"}, "operations": ["write", "unlink"],
                "semantics": "block mutations to evidence-resolved files/subtrees; descendants inherit domain",
                "object_scope":"Honor declared registered_existing_files sets using exact registered targets. Derived artifacts and adjacent legitimate files remain available. directory_subtree means an explicitly declared entire tree. Ancestor identity is guarded separately by the managed loader.",
                "history_parameterization":"The reviewed configuration selector covers registered shell/Git configuration and JSON/TOML/YAML/INI/CONF/CFG assets; it excludes Python source and tests. A different object kind needs a current-task new candidate.",
                "unsupported": ["dialogue semantics", "arbitrary command semantics", "new allow rules", "policy relaxation"],
                "draft_schema": Draft.model_json_schema()}

def configuration_asset(path):
    name=Path(path).name
    return name in ('.bashrc','.bash_profile','.profile','.gitconfig') or Path(path).suffix.lower() in ('.json','.toml','.yaml','.yml','.ini','.conf','.cfg')

def validate(task_id, draft, compile_bundle=True):
    draft = Draft.model_validate(draft)
    ctx = context(task_id)
    if draft.context_hash != ctx["context_hash"]: raise ValueError("expected current context hash: "+json.dumps({"code":"stale_or_malformed_context_reference","expected":ctx["context_hash"],"received":draft.context_hash,"read_tool":"get_task_context"}))
    if draft.no_op != (len(draft.atoms) == 0): raise ValueError("no_op must describe an empty enforcement proposal")
    with db.connect() as con:
        sources = {r["id"]: dict(r) for r in con.execute("SELECT * FROM bootstrap_sources WHERE task_id=?", (task_id,))}
        task = dict(con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
        bindings = []
        for atom_index,atom in enumerate(draft.atoms):
            if any(sid not in sources for sid in atom.evidence_ids): raise ValueError("unknown or cross-task evidence IDs: " + ", ".join(sid for sid in atom.evidence_ids if sid not in sources) + "; use actual IDs from list_policy_sources")
            evidence = [sources[sid] for sid in atom.evidence_ids]
            if any(digest(s["text"]) != s["content_hash"] for s in evidence): raise ValueError("registered evidence content hash mismatch")
            if not any(s["role"] in ("task", "platform") for s in evidence): raise ValueError("atom["+str(atom_index)+"] paths="+json.dumps(atom.paths)+" lacks task/platform authority evidence; cited roles="+json.dumps({s["id"]:s["role"] for s in evidence})+"; actual task/platform source IDs="+json.dumps([s["id"] for s in sources.values() if s["role"] in ("task","platform")])+". Environment and assets resolve targets; they cannot authorize constraints.")
            asset_paths = [s["path"] for s in evidence if s["role"] == "asset"]
            resolved = []
            for target in atom.paths:
                subtree = target.endswith("/**")
                base = target[:-3] if subtree else target
                if not base.startswith("/") or any(c in base for c in ('*', '?', '\\', '\n', '\r', '\x00')): raise ValueError("target must be canonical absolute registered path")
                path = Path(base)
                if str(path.resolve()) != base or Path(task["workspace"]) not in path.parents: raise ValueError("path escapes workspace or is not canonical")
                if subtree:
                    if not path.is_dir() or not any(p.startswith(base + "/") for p in asset_paths): raise ValueError("subtree requires registered descendant evidence")
                elif base not in asset_paths and not (path.is_dir() and any(p.startswith(base + "/") for p in asset_paths)):
                    raise ValueError("target is not among cited registered assets or evidenced directories: "+json.dumps({"target":target,"cited_asset_paths":asset_paths,"read_tool":"list_policy_sources and read_policy_source"}))
                resolved.append({"path": target, "parameter_sources": [s["id"] for s in evidence if s["role"] == "asset" and (s["path"] == base or s["path"].startswith(base + "/"))]})
            if atom.decision in ("reuse", "parameterize"):
                if not atom.history_id or not atom.history_hash: raise ValueError("reuse requires immutable history id/hash")
                historical = approved_record(atom.history_id, atom.history_hash, con)
                allowed = historical.get("operations")
                if allowed is not None and not set(atom.operations).issubset(set(allowed)): raise ValueError("reuse exceeds reviewed template capabilities")
                selector=historical.get('parameterization',{}).get('protected_paths')
                if selector=='current-task registered configuration assets':
                    for target in atom.paths:
                        base=target.removesuffix('/**')
                        selected=[s['path'] for s in sources.values() if s['role']=='asset' and (s['path']==base or s['path'].startswith(base+'/'))]
                        if not selected or any(not configuration_asset(p) for p in selected):
                            raise ValueError('reviewed configuration template cannot bind source code or test assets; use a current-task new candidate for a different object kind')
            elif atom.history_id or atom.history_hash: raise ValueError("new candidate cannot claim history reuse")
            bindings.append({"history_id": atom.history_id, "history_hash": atom.history_hash, "decision": atom.decision,
                             "paths": resolved, "applicability_reason": atom.reason})
        # Coverage is independent of history ranking: a valid reused atom cannot
        # displace an explicit current-task requirement.
        for requirement in ctx.get('declared_constraints',[]):
            authority=[s for s in sources.values() if s['role']==requirement['authority_role'] and s['content_hash']==requirement['authority_hash']]
            if not authority or not any(requirement['source_quote'] in s['text'] for s in authority):raise ValueError('declared requirement has no pinned source quote')
            if requirement['intent']=='semantic_guidance':
                if not draft.guidance and not draft.unresolved:raise ValueError('declared semantic requirement needs guidance or clarification: '+requirement['id'])
                continue
            if requirement.get('object_scope')=='registered_existing_files':
                for atom in draft.atoms:
                    if not set(atom.evidence_ids)&{s['id'] for s in authority}:continue
                    for pattern in atom.paths:
                        base=pattern.removesuffix('/**')
                        if any(target.startswith(base+'/') for target in requirement['targets']):
                            raise ValueError('overbroad registered object collection: '+requirement['id']+' protects existing files, not every descendant or derived artifact. Use exact authority-bound targets: '+json.dumps(requirement['targets']))
            for target in requirement['targets']:
                for op in ('write','unlink'):
                    covered=any(op in atom.operations and set(atom.evidence_ids)&{s['id'] for s in authority}
                                and any(p==target or (p.endswith('/**') and target.startswith(p[:-2])) for p in atom.paths)
                                for atom in draft.atoms)
                    if not covered and not draft.unresolved:raise ValueError('uncovered declared requirement '+requirement['id']+': '+op+' '+target)
    from ..policy_ir import PolicyIR, Rule, Clause, render
    ir_rules = []
    for number, atom in enumerate(draft.atoms):
        ir_rules.append(Rule(name=f"bootstrap-{number + 1}",reason=atom.statement,
            clauses=[Clause(operation=operation,pattern=target) for operation in dict.fromkeys(atom.operations) for target in dict.fromkeys(atom.paths)]))
    ir = PolicyIR(rules=ir_rules,guidance=draft.guidance)
    dsl = render(ir, "") or ""
    raw_dsl=dsl
    full_dsl, bundle = make_dsl(task["workspace"], task["output_dir"], ctx["base_settings"], dsl)
    report=None
    state, info, diagnostic = "not_run", {}, ""
    if compile_bundle:
        from ..main import compile_policy
        mode=normalization.mode_for(task_id)
        if mode!='legacy':
            try:
                full_dsl,bundle,info,report=normalization.build(full_dsl,bundle,task_id,0,mode,compile_policy)
                base=make_dsl(task["workspace"],task["output_dir"],ctx["base_settings"])[0]
                if not full_dsl.startswith(base):raise ValueError("Normalization changed startup platform boundary")
                dsl=full_dsl[len(base):].strip()
                state='compiled'
            except ValueError as error:state,diagnostic='compile_failed',str(error)
        else:state, info, diagnostic = compile_policy(bundle, task_id, 0)
    valid = not draft.unresolved and state in ("compiled", "not_run")
    if not valid and not diagnostic: diagnostic = "Blocking execution gaps: " + "; ".join(draft.unresolved) if draft.unresolved else "Backend clauses are not fully supported"
    proposal = {"schema": "TaskPolicyProposal/1", "draft": draft.model_dump(), "scenario_hash": ctx["scenario_hash"],
                "history_bindings": bindings, "policy_ir": ir.model_dump(),
                "actplane_dsl": dsl, "raw_actplane_dsl":raw_dsl, "normalization":report,"guidance": draft.guidance, "gaps": draft.unresolved,
                "metadata_pseudocode": [f"IF AGENT {','.join(a.operations)} {','.join(a.paths)} THEN deny BECAUSE {a.statement}" for a in draft.atoms],
                "scope_diff": {"base": ctx["base_settings"], "additional_blocks": [a.model_dump() for a in draft.atoms]},
                "context_hash": ctx["context_hash"]}
    proposal_state = "validated" if valid else "needs_clarification" if draft.unresolved and state == "compiled" else "invalid"
    return {"valid": valid, "state": proposal_state, "compile_state": state, "compiler": info, "diagnostic": diagnostic,
            "normalization":report,"blocking_gaps": draft.unresolved, "proposal": proposal, "proposal_hash": digest(proposal)}

def verify_version(con, task_id, version_id, expected_context=None, expected_proposal=None, approval=False):
    row = con.execute("SELECT * FROM bootstrap_versions WHERE policy_version_id=?", (version_id,)).fetchone()
    if not row:
        version=con.execute("SELECT layer FROM policy_versions WHERE id=?",(version_id,)).fetchone()
        if version and (version["layer"]=="task_bootstrap" or con.execute("SELECT 1 FROM bootstrap_contexts WHERE task_id=?",(task_id,)).fetchone()):raise ValueError("startup version has no immutable proposal binding")
        return None
    ctx = context(task_id, con)
    proposal = con.execute("SELECT * FROM bootstrap_proposals WHERE id=? AND task_id=?", (row["proposal_id"], task_id)).fetchone()
    if not proposal or proposal["state"] != "validated" or digest(json.loads(proposal["proposal_json"])) != row["proposal_hash"] or proposal["content_hash"] != row["proposal_hash"]:
        raise ValueError("proposal changed after version construction")
    if ctx["context_hash"] != row["context_hash"]: raise ValueError("scene changed after version construction")
    task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if task["workspace"] != ctx["workspace"] or digest(task["prompt"]) != ctx["raw_prompt_hash"] or json.loads(task["settings_json"]) != ctx["base_settings"]:
        raise ValueError("task state diverges from frozen scene")
    if approval and (expected_context != row["context_hash"] or expected_proposal != row["proposal_hash"]):
        raise ValueError("generated version approval requires expected context and proposal hashes")
    data = json.loads(proposal["proposal_json"])
    for binding in data["history_bindings"]:
        if binding["history_id"]: approved_record(binding["history_id"], binding["history_hash"], con)
    if digest(row["prompt_text"]) != row["prompt_hash"]: raise ValueError("DSH prompt hash mismatch")
    for atom in data["draft"]["atoms"]:
        for sid in atom["evidence_ids"]:
            source=con.execute("SELECT text,content_hash FROM bootstrap_sources WHERE task_id=? AND id=?",(task_id,sid)).fetchone()
            if not source or digest(source["text"])!=source["content_hash"]: raise ValueError("approved evidence is missing or has changed")
    version=con.execute("SELECT dsl_text,policy_yaml FROM policy_versions WHERE id=? AND task_id=?",(version_id,task_id)).fetchone()
    expected_dsl,expected_yaml=make_dsl(task["workspace"],task["output_dir"],ctx["base_settings"],data["actplane_dsl"] if row["condition"]=="B" else "")
    if not version or version['dsl_text']!=expected_dsl or version['policy_yaml']!=expected_yaml:raise ValueError("approved bundle does not match the bound proposal and experiment condition")
    return dict(row)

def verify_initial_assets(task_id):
    ctx = context(task_id)
    from .scene import effective_dsh
    if effective_dsh() != ctx["dsh"]: raise ValueError("DSH effective profile changed after generation")
    for asset in ctx["assets"]:
        path = Path(asset["mapped_path"])
        if not path.is_file() or path.is_symlink() or __import__('hashlib').sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError("initial asset changed before launch: " + asset["relative_path"])
