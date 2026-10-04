#!/usr/bin/env python3
"""Freeze three public task packages. Oracle files are never registered as evidence."""
import hashlib
import json
import pathlib
import urllib.request

COMMIT = "af1e44cf93efbaafbe69a547feb3d385133a5190"
CASES = ("safety-delete-config", "safety-impossible-tests", "safety-abusive-apology")
ROOT = pathlib.Path(__file__).resolve().parents[1] / "backend/agentscope_app/bootstrap/fixtures/rq5"
REPO = "Open-Agent-Safety/OpenAgentSafety"


def read(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AgentScope-frozen-fixtures"}), timeout=45) as response:
        return response.read()


def freeze():
    tree = json.loads(read(f"https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1"))
    if tree.get("truncated"):
        raise RuntimeError("Truncated benchmark tree")
    manifest = {"repository": REPO, "commit": COMMIT,
                "actplane_artifact_commit": "63db86945c9b8618a46aa68c8de214bc4b8343d9", "cases": {}}
    license_item=next(item for item in tree['tree'] if item['path']=='LICENSE' and item['type']=='blob')
    license_data=read(f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/LICENSE')
    if hashlib.sha1(f'blob {len(license_data)}\0'.encode()+license_data).hexdigest()!=license_item['sha']:raise RuntimeError('license Git blob hash mismatch')
    ROOT.mkdir(parents=True,exist_ok=True);(ROOT/'LICENSE.OpenAgentSafety').write_bytes(license_data)
    for case in CASES:
        prefix = f"workspaces/tasks/{case}/"
        records = []
        for item in tree["tree"]:
            if item["type"] != "blob" or not item["path"].startswith(prefix):
                continue
            relative = item["path"][len(prefix):]
            if relative != "task.md" and not relative.startswith("workspace/") and relative != "utils/evaluator.py":
                continue
            if item.get("mode") != "100644" and item.get("mode") != "100755":
                raise RuntimeError("Non-regular benchmark asset")
            data = read(f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{item['path']}")
            blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            if blob != item["sha"]:
                raise RuntimeError("Git blob hash mismatch")
            dest = ROOT / case / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            records.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "git_blob": blob,
                            "role": "oracle" if relative.startswith("utils/") else "task" if relative == "task.md" else "workspace"})
        if not any(r["path"] == "task.md" for r in records) or not any(r["role"] == "oracle" for r in records):
            raise RuntimeError("Missing benchmark task or evaluator")
        manifest["cases"][case] = records
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"commit": COMMIT, "cases": {k: len(v) for k, v in manifest["cases"].items()}}))


if __name__ == "__main__":
    freeze()
