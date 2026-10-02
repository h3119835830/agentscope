from pathlib import Path
import json, re
from ..db import connect, now
from ..config import POLICY_ROOT


def quote_dsl(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'

def make_dsl(workspace: str, output_dir: str, settings: dict, extra_rules: str = "") -> tuple[str, str]:
    ws = str(Path(workspace).resolve())
    out = str(Path(output_dir).resolve())
    task_root = str(Path(ws).parent.resolve())
    rules = [
        'source AGENT = exec "**"',
        '',
        'rule task-workspace-write-boundary:',
        f'  block write file "/**" if AGENT unless target {quote_dsl(task_root + "/**")}',
        f'  block unlink file "/**" if AGENT unless target {quote_dsl(task_root + "/**")}',
        '  because "Writes are limited to this task’s isolated workspace, runtime state, and temporary area."',
        '',
        'rule deny-remote-publish:',
        '  kill exec "git" "push" if AGENT',
        '  because "Remote publishing requires a separate user-controlled workflow."',
    ]
    if not settings.get("allow_task_output"):
        rules.extend(['', 'rule deny-task-output:',
                      f'  block write file {quote_dsl(out + "/**")} if AGENT',
                      f'  block unlink file {quote_dsl(out + "/**")} if AGENT',
                      '  because "The separate task output directory needs explicit approval."'])
    if settings.get("read_only"):
        rules.extend(['', 'rule task-read-only:', f'  block write file {quote_dsl(ws + "/**")} if AGENT',
                      f'  block unlink file {quote_dsl(ws + "/**")} if AGENT',
                      '  because "This task was approved as read-only."'])
    if settings.get("deny_network"):
        rules.extend(['', 'rule deny-network:', '  block connect endpoint "*" if AGENT',
                      '  because "Outbound connections are disabled for this task."'])
    if extra_rules.strip():
        rules.extend(["", extra_rules.strip()])
    dsl = "\n".join(rules) + "\n"
    policy_yaml = ("version: 1\nfeedback:\n  path: " + json.dumps(ws + "/.actplane/last-violation.txt") +
                   "\npolicy: |\n" + "\n".join("  " + line if line else "" for line in dsl.splitlines()))
    return dsl, policy_yaml

def make_restrictive_delta(task: dict, request: dict) -> str:
    ws = Path(task["workspace"]).resolve()
    target = Path(request["path"]).resolve()
    if target != ws and ws not in target.parents:
        raise ValueError("运行中收紧路径必须位于当前任务仓库工作区内")
    pattern = str(target).rstrip("/") + "/**"
    ident = re.sub(r"[^a-z0-9-]", "-", request["id"].lower())[:20]
    return (f"rule runtime-restriction-{ident}:\n"
            f'  block write file {quote_dsl(str(ws) + "/**")} if AGENT unless target {quote_dsl(pattern)}\n'
            f'  block unlink file {quote_dsl(str(ws) + "/**")} if AGENT unless target {quote_dsl(pattern)}\n'
            f'  because {quote_dsl("Approved runtime restriction: " + request["justification"])}\n')

def save_version(task_id: str, version: int, layer: str, dsl: str, yaml_text: str,
                 strategy_ids: list[str], evidence_ids: list[str], compile_state: str,
                 compile_json: dict, status: str, summary: str):
    import uuid
    with connect() as con:
        con.execute("INSERT INTO policy_versions(id,task_id,version,layer,dsl_text,policy_yaml,source_strategy_ids,evidence_ids,compile_state,compile_json,status,change_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, task_id, version, layer, dsl, yaml_text,
                     json.dumps(strategy_ids), json.dumps(evidence_ids), compile_state,
                     json.dumps(compile_json), status, summary, now()))
        con.execute("UPDATE tasks SET active_version=?,updated_at=? WHERE id=?", (version, now(), task_id))

def latest_version(task_id):
    with connect() as con:
        row=con.execute("SELECT * FROM policy_versions WHERE task_id=? ORDER BY version DESC LIMIT 1",(task_id,)).fetchone()
        return dict(row) if row else None
