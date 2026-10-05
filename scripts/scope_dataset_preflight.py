#!/usr/bin/env python3
"""Read-only public fixture preflight. Does not run an Agent, oracle or kernel workload."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from agentscope_app.bootstrap.scene import FIXTURES, manifest, mapped_asset
from agentscope_app.bootstrap.evaluation import initial_layout


def run():
    frozen=manifest()  # Verify every source byte before inspecting adapters.
    cases=[]
    for case,files in frozen["cases"].items():
        original,mapped,assets,changes={},{},[],{}
        for entry in files:
            if entry["role"]!="workspace":
                continue
            source=entry["path"].removeprefix("workspace/")
            destination=mapped_asset(case,source)
            sha=hashlib.sha256((FIXTURES/case/entry["path"]).read_bytes()).hexdigest()
            original[source]=sha
            if destination in mapped:
                raise RuntimeError("Dataset adapter path collision")
            mapped[destination]=sha
            assets.append({"relative_path":destination,"sha256":sha})
            if source!=destination:
                changes[source]=destination
        context={"scenario_id":case,"assets":assets,"asset_layout_mapping":changes}
        original_check=initial_layout({**context,"assets":[]} ,original)
        mapped_check=initial_layout(context,mapped)
        if not mapped_check["valid"]:
            raise RuntimeError("Dataset adapter fails initial layout: "+case)
        oracle_paths=[f["path"] for f in files if f["role"]=="oracle"]
        agent_paths=[f["path"] for f in files if f["role"] in ("task","workspace")]
        assert not set(oracle_paths)&set(agent_paths)
        cases.append({"case":case,"source_files_verified":len(files),"workspace_files":len(mapped),
            "original_layout_matches_frozen_oracle":original_check["valid"],
            "original_missing_required":original_check["missing_required"],
            "adapter_layout_valid":mapped_check["valid"],"explicit_layout_mapping":changes,
            "oracle_excluded_from_agent_input":True,
            "file_enforcement_candidate":case!="safety-abusive-apology",
            "dynamic_scope_workbench_ready":False})
    return {"mode":"read_only_fixture_preflight","source_repository":frozen["repository"],"source_commit":frozen["commit"],
        "cases":cases,"passed":True,"agent_execution":"not_run","kernel_execution":"not_run",
        "benchmark_score":"not_computed"}


if __name__=="__main__":
    result=run()
    if len(sys.argv)>1:
        Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
