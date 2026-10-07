#!/usr/bin/env python3
"""Independently verify a published export's index, counts, hashes and boundary."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
from export_task_archives import assert_public, sha256


def verify(root, snapshot=None):
    root = root.resolve()
    index = json.loads((root / "index.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())["files"]
    expected_files = {str(p.relative_to(root)) for p in root.rglob("*.json") if p.name != "manifest.json"}
    assert set(manifest) == expected_files
    for name, digest in manifest.items():
        path = (root / name).resolve()
        assert path.is_relative_to(root) and sha256(path) == digest, "Manifest mismatch"
    ids, counts, max_bytes = set(), Counter(), 0
    domains, available_domains, missing_domains = 0, 0, 0
    for row in index["records"]:
        path = (root / row["path"]).resolve()
        assert path.is_relative_to(root) and sha256(path) == row["sha256"]
        record = json.loads(path.read_text())
        assert record["schema"] == "AgentScopeTaskHistory/1"
        assert record["task_id"] == row["task_id"] and record["task_id"] not in ids
        ids.add(record["task_id"])
        assert_public(record)
        events = record["events"]
        assert all(e["task_id"] == record["task_id"] for e in events)
        assert len({e["id"] for e in events}) == len(events) == row["events"]
        event_counts = Counter(e["category"] for e in events)
        assert {k: event_counts[k] for k in record["counts"]} == record["counts"] == row["counts"]
        assert sum(stage["event_count"] for stage in record["stages"]) == len(events)
        assert record["history_only"] is True
        for version in record["domains"]:
            graph = version["graph"]
            assert graph["task_id"] == record["task_id"] and graph["live"] is False
            for detail in version["details"]:
                domains += 1
                assert detail["task_id"] == record["task_id"] and detail["live"] is False
                if detail["available"]:
                    available_domains += 1
                    assert isinstance(detail.get("dsl"), str) and detail["dsl"]
                    assert re.fullmatch(r"[a-f0-9]{64}", detail["policy_hash"])
                else:
                    missing_domains += 1
                    assert not detail.get("dsl")
        counts.update(record["counts"])
        max_bytes = max(max_bytes, path.stat().st_size)
    assert len(ids) == index["task_count"]
    assert sum(counts.values()) == index["event_count"] and dict(counts) == index["category_counts"]
    if snapshot:
        with sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True) as database:
            assert ids == {row[0] for row in database.execute("SELECT id FROM tasks")}, "Omitted or unknown task"
    assert max_bytes < 100_000_000, "Oversized GitHub blob"
    return {"passed": True, "tasks": len(ids), "events": sum(counts.values()), "categories": dict(counts),
            "verified_json_files": len(manifest), "domain_details": domains,
            "available_domain_details": available_domains, "unavailable_domain_details": missing_domains,
            "largest_record_bytes": max_bytes, "source_task_set_equal": bool(snapshot)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.root, args.snapshot)))
