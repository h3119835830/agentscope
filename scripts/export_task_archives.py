#!/usr/bin/env python3
"""Export complete, public task archives through the accepted archive projection.

The source checkout must contain agentscope_app.archive. SQLite is copied with
the backup API and every projection connection is query-only. Never publish the
private snapshot. The output is a historical export, not a restorable runtime.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

PRIVATE_KEY = re.compile(r"(?i)(token|credential|secret|password|authorization|reasoning|thinking|chain.of.thought|raw.stream|serialized|native_execution_context)")
RAW_KEYS = {"excerpt", "content", "contents", "file_content", "source_text", "raw_json", "stdout", "stderr", "arguments", "content_base64"}
SECRET_VALUE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b")
ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|credential|authorization|token)\s*[:=]\s*[\"']?[^\s,;\"']+")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scrub(value, counts):
    if isinstance(value, dict):
        if value.get("type") in {"reasoning", "thinking", "reasoning_content", "redacted_thinking"}:
            counts["private_blocks"] += 1
            return {"redacted": True}
        result = {}
        for key, item in value.items():
            if PRIVATE_KEY.search(key) or key in RAW_KEYS:
                counts["omitted_fields"] += 1
            else:
                result[key] = scrub(item, counts)
        return result
    if isinstance(value, list):
        return [scrub(item, counts) for item in value]
    if isinstance(value, str):
        value, n = re.subn(r"(?is)<(?:think|thinking|reasoning)>.*?</(?:think|thinking|reasoning)>", "[PRIVATE CONTENT OMITTED]", value)
        counts["private_blocks"] += n
        value, n = SECRET_VALUE.subn("[REDACTED]", value)
        counts["secret_values"] += n
        value, n = ASSIGNMENT.subn(lambda m: m.group(1) + "=[REDACTED]", value)
        counts["credential_assignments"] += n
        value, n = re.subn(r"(?i)\bbearer\s+[^\s,;]+", "Bearer [REDACTED]", value)
        counts["bearer_values"] += n
        value, n = re.subn(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        counts["url_credentials"] += n
        value, n = re.subn(r"(?s)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", "[PRIVATE KEY OMITTED]", value)
        counts["private_keys"] += n
        return value
    return value


def assert_public(value):
    if isinstance(value, dict):
        for key, item in value.items():
            assert not PRIVATE_KEY.search(key) and key not in RAW_KEYS, "Private field survived filtering"
            assert_public(item)
    elif isinstance(value, list):
        for item in value:
            assert_public(item)
    elif isinstance(value, str):
        assert not SECRET_VALUE.search(value), "Credential-shaped value survived filtering"
        assert not re.search(r"-----BEGIN [^-]*PRIVATE KEY-----|<(?:think|thinking|reasoning)>", value, re.I)


def all_events(projection, connection, task_id, category):
    events, seen, cursors = [], set(), set()
    before, expected = None, None
    while True:
        page = projection.page(connection, task_id, category, before, 200, with_detail=True)
        if expected is None:
            expected = page["total"]
        assert expected == page["total"], "Snapshot count changed"
        for event in page["events"]:
            assert event["task_id"] == task_id, "Cross-task event"
            assert event["category"] == category, "Wrong event category"
            assert event["id"] not in seen, "Duplicate event across pages"
            seen.add(event["id"])
            events.append(event)
        before = page["next_cursor"]
        if not before:
            break
        assert before not in cursors, "Repeated pagination cursor"
        cursors.add(before)
    assert len(events) == expected, "Archive pagination was truncated"
    return events


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_filename(task_id):
    # Legacy acceptance tasks can have non-16-character identifiers. Keep every
    # identity inside the record; only the filesystem name needs normalization.
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", task_id):
        return task_id + ".json"
    return "id-" + hashlib.sha256(task_id.encode()).hexdigest() + ".json"


def git(source, *args):
    return subprocess.check_output(["git", "-c", "safe.directory=" + str(source), "-C", str(source), *args], text=True).strip()


def export(args):
    source, snapshot, output = args.source.resolve(), args.snapshot.resolve(), args.output.resolve()
    assert not snapshot.is_relative_to(output), "Private SQLite snapshot must be outside published output"
    assert not output.exists(), "Refuse to overwrite an existing archive export"
    if snapshot.exists():
        assert args.reuse_snapshot, "Existing private snapshot requires --reuse-snapshot"
    else:
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as original, sqlite3.connect(snapshot) as destination:
            original.backup(destination)
        os.chmod(snapshot, 0o600)
    initial_hash = sha256(snapshot)
    with tempfile.TemporaryDirectory(prefix="agentscope-public-export-") as temporary:
        private = Path(temporary)
        package = source / "backend/agentscope_app"
        files = sorted(package.rglob("*.py"))
        before = {str(p.relative_to(source)): sha256(p) for p in files}
        for path in files:
            target = private / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        assert before == {str(p.relative_to(source)): sha256(p) for p in files}, "Source changed during capture"
        os.environ.update({"AGENTSCOPE_STATE_DIR": str(private / "state"), "AGENTSCOPE_DB": str(snapshot),
                           "AGENTSCOPE_TASK_ROOT": str(private / "state/unused-projects"),
                           "AGENTSCOPE_POLICY_DIR": str(args.policy_root.resolve()),
                           "AGENTSCOPE_CORPUS_ROOT": str(private / "state/unused-import"),
                           "AGENTSCOPE_LOG_DIR": str(private / "state/unused-logs")})
        sys.path.insert(0, str(private / "backend"))
        from agentscope_app import db, broker_client
        from agentscope_app.archive import projection, historical
        from agentscope_app.managed import controller

        @contextmanager
        def connect():
            connection = sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            try:
                yield connection
            finally:
                connection.close()

        def forbidden_broker(*unused, **kwargs):
            raise AssertionError("Archive export must not contact the Broker")

        db.connect = connect
        broker_client.call = controller.broker = forbidden_broker
        timestamp = args.snapshot_at or datetime.now(timezone.utc).isoformat()
        output.mkdir(parents=True)
        rows, all_counts, all_redactions = [], Counter(), Counter()
        with connect() as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            tasks = connection.execute("SELECT id FROM tasks ORDER BY created_at,id").fetchall()
            for number, row in enumerate(tasks, 1):
                task_id = row["id"]
                archive = projection.archive(task_id, limit=1)
                groups = {category: all_events(projection, connection, task_id, category) for category in projection.CATEGORIES}
                assert {k: len(v) for k, v in groups.items()} == archive["counts"]
                combined = [event for group in groups.values() for event in group]
                assert len({event["id"] for event in combined}) == len(combined)
                combined.sort(key=lambda event: (event["time"], event["id"]))
                latest = historical.graph(task_id)
                domains = []
                for version in latest["versions"]:
                    graph = historical.graph(task_id, version["version"])
                    details = [historical.domain_detail(task_id, node["key"]) for node in graph["nodes"] if node["kind"] == "domain"]
                    assert graph["task_id"] == task_id and graph["live"] is False
                    assert all(detail["task_id"] == task_id and detail["live"] is False for detail in details)
                    domains.append({"graph": graph, "details": details})
                redactions = Counter()
                record = scrub({"schema": "AgentScopeTaskHistory/1", "task_id": task_id, "snapshot_at": timestamp,
                                "history_only": True, "header": archive["header"], "stages": archive["stages"],
                                "counts": archive["counts"], "missing": archive["missing"], "coverage": archive["coverage"],
                                "events": combined, "domains": domains,
                                "domain_status": latest["status"], "export_scope": "All persisted public archive events; no raw source bodies or native session replay; no current liveness assertion"}, redactions)
                assert_public(record)
                name = "records/" + record_filename(task_id)
                write_json(output / name, record)
                rows.append({"task_id": task_id, "name": record["header"]["name"], "status": record["header"]["status"],
                             "phase": record["header"]["execution"]["phase"], "events": len(combined), "counts": record["counts"],
                             "missing": record["missing"], "domain_versions": len(domains), "path": name, "sha256": sha256(output / name),
                             "redactions": dict(redactions)})
                all_counts.update(record["counts"])
                all_redactions.update(redactions)
                if number % 25 == 0 or number == len(tasks):
                    print(json.dumps({"exported": number, "total": len(tasks), "events": sum(all_counts.values())}), flush=True)
        assert initial_hash == sha256(snapshot), "Private snapshot was modified"
        source_state = git(source, "status", "--porcelain", "--untracked-files=normal")
        provenance = {"checkout_head": git(source, "rev-parse", "HEAD"), "checkout_had_local_changes": bool(source_state),
                      "python_source_sha256": before, "projection_sha256": before["backend/agentscope_app/archive/projection.py"],
                      "database_snapshot_sha256": initial_hash, "snapshot_at": timestamp,
                      "artifact_observation": "Loaded policy files independently hash-verified against frozen receipts during export; missing or changed files stay unavailable"}
        write_json(output / "provenance.json", provenance)
        write_json(output / "index.json", {"schema": "AgentScopeTaskHistoryIndex/1", "snapshot_at": timestamp, "task_count": len(rows),
                                           "event_count": sum(all_counts.values()), "category_counts": dict(all_counts), "records": rows})
        report = {"schema": "AgentScopeTaskHistoryValidation/1", "passed": True, "task_count": len(rows),
                  "event_count": sum(all_counts.values()), "category_counts": dict(all_counts), "database_integrity": "ok",
                  "snapshot_unchanged": True, "all_pages_exported": True, "unique_task_ids": len(rows) == len({r["task_id"] for r in rows}),
                  "cross_task_events": 0, "duplicate_event_ids_within_task": 0, "public_content_scan": "passed", "redactions": dict(all_redactions),
                  "raw_sources_included": False, "runtime_replay_supported": False, "live_process_checks_performed": False}
        write_json(output / "validation.json", report)
        manifest = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob("*.json"))}
        write_json(output / "manifest.json", {"schema": "AgentScopeHistoryManifest/1", "files": manifest})
        lines = ["# AgentScope task history", "", f"Snapshot: {timestamp}. {len(rows)} tasks; {sum(all_counts.values())} public archive events.", "",
                 "Each linked JSON is one complete task archive containing its goal, workspace provenance, preparation, policy generation and versions, permission changes, execution evidence, closure receipts and available historical domain DSL.", "",
                 "This is a read-only historical export. Recorded running states do not establish current process liveness. Missing evidence remains explicitly missing. Private session streams, source bodies, credentials and the database are excluded. This export cannot restore live sessions, credentials or enforcement.", "",
                 "See [validation](validation.json), [provenance](provenance.json), [index](index.json) and [hash manifest](manifest.json).", "",
                 "| Task | Status at snapshot | Events | Archive |", "|---|---|---:|---|"]
        for row in rows:
            title = str(row["name"]).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {title} | {row['status']} | {row['events']} | [{row['task_id']}]({row['path']}) |")
        (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--reuse-snapshot", action="store_true")
    parser.add_argument("--snapshot-at")
    parser.add_argument("--policy-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    export(parser.parse_args())


if __name__ == "__main__":
    main()
