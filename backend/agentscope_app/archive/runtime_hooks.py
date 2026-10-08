"""Offline runtime-hook metadata, separate from the current mechanism definition.

Only frozen job/request metadata is projected. No live managed state, model-visible
prompt, observation content, candidate explanation, or executor is consulted.
"""
import re

from fastapi import HTTPException

from .. import db
from ..managed.records import HOOKS
from . import projection as archive


FLAGS = {"history_only": True, "historical": True, "live": False}
ACTORS = {
    "native_context": "原生上下文变化",
    "kernel": "ActPlane 拒绝反馈",
    "verified_feedback": "误拦截复核",
    "recovery": "原生会话恢复",
    "control_review": "控制面复核",
    "native_user": "真实用户消息",
    "user": "管理员约束",
    "administrator": "管理员约束",
    "DSH": "执行能力申请",
}
# These are public event names admitted by the native observation adapter.
OBSERVATION_TYPES = {
    "system_prompt": "system/message",
    "instructions": "developer/message",
    "tools": "request/header",
    "memory": "compaction/summary",
    "memory_prune": "compaction/prune",
    "context": "user/message",
}
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,256}\Z")
SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
CURSOR_CATEGORY = "runtime_hooks"


def _object(value):
    return value if isinstance(value, dict) else {}


def _number(value):
    return value if type(value) is int and value >= 0 else None


def _identifier(value):
    if type(value) is int and value >= 0:
        return str(value)
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else None


def mechanism():
    """Explain today's mechanism without claiming it was frozen for a task."""
    definition = HOOKS["runtime"]
    return {
        "name": definition["name"],
        "events": list(definition["events"]),
        "sequence": list(definition["sequence"]),
        "source": "current_definition",
        "configuration_status": "not_historical_configuration",
        "historical_configuration": False,
        "notice": "当前代码的 Hook 机制说明；不是该历史任务冻结的配置，也不证明这些来源都曾实际触发。",
    }


def _observations(context):
    native = _object(context.get("native_execution_context"))
    result = []
    seen = set()
    for value in native.values():
        if not isinstance(value, dict):
            continue
        category = value.get("category")
        category = category if isinstance(category, str) and category in OBSERVATION_TYPES else None
        typ = value.get("type")
        typ = typ if category and typ == OBSERVATION_TYPES[category] else None
        seq = _number(value.get("seq"))
        content_hash = value.get("content_hash")
        content_hash = content_hash.lower() if isinstance(content_hash, str) and SHA256.fullmatch(content_hash) else None
        key = (category, typ, seq, content_hash)
        if key in seen:
            continue
        seen.add(key)
        missing = [name for name, item in zip(("category", "type", "seq", "content_hash"), key) if item is None]
        result.append({
            "category": category, "type": typ, "seq": seq,
            "content_hash": content_hash,
            "status": "unrecorded" if missing else "recorded",
            "missing_fields": missing,
        })
    return sorted(result, key=lambda item: (item["seq"] if item["seq"] is not None else -1, item["category"] or "", item["type"] or "", item["content_hash"] or ""))


def _record(con, task_id, row):
    context = _object(archive.decode(row["context_json"]))
    request_id = _identifier(context.get("request_evidence_id"))
    sources = context.get("sources")
    sources = sources if isinstance(sources, list) else []
    source_matches = [
        _object(value.get("content")) for value in sources
        if isinstance(value, dict) and request_id is not None
        and _identifier(value.get("evidence_id")) == request_id
        and value.get("source") in (None, "request")
    ]
    # Repeated frozen references are harmless, conflicting sources are ambiguous.
    identities = {(value.get("actor") if isinstance(value.get("actor"), str) else None, _number(value.get("turn"))) for value in source_matches}
    ambiguous = len(identities) > 1
    source = source_matches[0] if source_matches and not ambiguous else {}
    request = con.execute(
        "SELECT id,payload_json FROM managed_events WHERE task_id=? AND kind='request' AND id=?",
        (task_id, request_id),
    ).fetchone() if request_id is not None and "managed_events" in archive.tables(con) else None
    dispatch = _object(archive.decode(request["payload_json"])) if request else {}
    # An exact persisted request can supply metadata if an older frozen source is
    # absent. Never use a latest request or a different task/session as fallback.
    origin = "frozen_job_request_evidence" if source else "persisted_request_event" if request and not ambiguous else "unrecorded"
    saved_actor = source.get("actor") if source else dispatch.get("actor") if not ambiguous else None
    actor = saved_actor if isinstance(saved_actor, str) and saved_actor in ACTORS else None
    accepted_turn = _number(source.get("turn")) if source else _number(dispatch.get("accepted_turn", dispatch.get("turn")))
    dispatched_turn = _number(dispatch.get("dispatched_turn"))
    turn = dispatched_turn if dispatched_turn is not None else accepted_turn
    observations = _observations(context)
    revision = _number(row["revision"])
    missing = [name for name, value in (("request_id", request_id), ("actor", actor), ("revision", revision), ("turn", turn), ("accepted_turn", accepted_turn)) if value is None]
    if not context:
        missing.insert(0, "context")
    if ambiguous:
        missing.append("ambiguous_request_source")
    if not observations:
        missing.append("observations")
    refs = ["managed_jobs:" + row["id"] + ":record"]
    if request:
        refs.append("managed_events:" + str(request["id"]) + ":record")
    return {
        "id": "runtime-hook:" + row["id"],
        "job_id": row["id"], "request_id": request_id,
        "time": row["created_at"], "generation_status": row["status"],
        "status": "recorded" if request_id is not None and actor is not None and not ambiguous else "unrecorded",
        "trigger": {
            "name": ACTORS.get(actor, "未记录触发来源"),
            "actor": actor, "request_id": request_id, "job_id": row["id"],
            "revision": revision, "turn": turn, "accepted_turn": accepted_turn,
            "observations": observations,
            "observations_status": "recorded" if observations and all(value["status"] == "recorded" for value in observations) else "unrecorded",
            "observations_meaning": "frozen_context_observations; not_each_a_new_trigger",
            "origin": origin,
        },
        "evidence_refs": refs, "missing_fields": missing,
        **FLAGS,
    }


def runtime_hooks(task_id, before=None, limit=50):
    """One row per persisted job/request identity, never one per policy child.

    Distinct jobs referring to the same request remain distinct historical
    assessments. Their identities and request IDs are kept for explicit linking.
    """
    if type(limit) is not int or not 1 <= limit <= 200:
        raise HTTPException(422, "Invalid runtime hook query")
    with db.connect() as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        archive.require_task(con, task_id)
        cursor = archive.cursor_decode(before, task_id, CURSOR_CATEGORY) if before else None
        if "managed_jobs" not in archive.tables(con):
            return {"task_id": task_id, "stage": "runtime", "mechanism": mechanism(), "records": [], "total": 0, "next_cursor": None, "status": "unrecorded", "missing_sources": ["managed_jobs"], **FLAGS}
        total = con.execute("SELECT COUNT(*) FROM managed_jobs WHERE task_id=?", (task_id,)).fetchone()[0]
        predicate = "task_id=?"
        params = [task_id]
        if cursor:
            predicate += " AND (created_at<? OR (created_at=? AND 'runtime-hook:'||id<?))"
            params.extend((cursor[0], cursor[0], cursor[1]))
        rows = con.execute(
            "SELECT id,revision,status,context_json,created_at FROM managed_jobs WHERE " + predicate + " ORDER BY created_at DESC,id DESC LIMIT ?",
            (*params, limit + 1),
        ).fetchall()
        records = [_record(con, task_id, row) for row in rows[:limit]]
        next_cursor = archive.cursor_encode(task_id, CURSOR_CATEGORY, records[-1]) if len(rows) > limit else None
    return archive.safe({
        "task_id": task_id, "stage": "runtime", "mechanism": mechanism(),
        "records": records, "total": total, "next_cursor": next_cursor,
        "status": "recorded" if total else "unrecorded",
        "missing_sources": [] if total else ["runtime_jobs"], **FLAGS,
    })
