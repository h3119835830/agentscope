"""Build a reviewed design catalogue; never load rules or contact a runtime.

python build_research_catalogue.py --corpus <607-rules.jsonl> --artifact-repo <ActPlane>
"""
import argparse
import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path

PIN = "63db86945c9b8618a46aa68c8de214bc4b8343d9"
BASE = "docs/eval_runs/rq1-expressiveness/full-607-subagents"
PAPER = "https://arxiv.org/html/2606.25189v2"

# A template is a reviewed synthesis, not an endorsement of the original YAML.
TEMPLATES = [
    ("P01", "秘密配置文件", "文件与凭据", "baseline", "file", "/workspace/.env", "read", "block", "配置文件可能含有凭据。请使用 .env.example 或申请受控凭据接口。", ["abhigyanpatwari__GitNexus::2", "ruvnet__ruflo::30"], "RQ1 提炼", "精确路径应由可信侧解析；.env.example 单独列为非秘密模板。禁止读取与禁止写入是不同权限。"),
    ("P02", "SSH 私钥", "文件与凭据", "baseline", "file", "/home/agent/.ssh/id_ed25519", "read", "block", "此会话不能直接读取 SSH 私钥。请使用获准的凭据代理。", [], "用户需求扩展", "607 份策略原文没有 .ssh 字面命中。私钥读取与 config/authorized_keys 修改应分开；不能把整个 .ssh 无差别禁读当成可用的 SSH 集成。"),
    ("P03", "云与集群凭据", "文件与凭据", "baseline", "file", "/home/agent/.aws/credentials", "read", "block", "云凭据由平台托管。请申请限定用途的访问能力。", ["abhigyanpatwari__GitNexus::2"], "从凭据保护扩展", ".aws、.kube、.npmrc、.pypirc 等为模板扩展；按实际凭据位置与操作分别实例化，不能声称这些路径均直接来自 RQ1。"),
    ("P04", "平台策略与审批记录", "文件与凭据", "baseline", "file", "/platform/policy/**", "write", "block", "会话不能修改平台安全底线和审批记录。请通过平台配置入口提交变更。", ["zeroclaw-labs__zeroclaw::34"], "RQ1 提炼与平台扩展", "原例保护开发契约文件删除。平台策略、批准记录需存于 Agent 写权限之外；规则本身不能作为唯一的自保护措施。还需覆盖创建、删除、重命名和权限改变等路径。"),
    ("P05", "重要数据禁止删除", "文件与凭据", "baseline", "file", "/data/protected/**", "unlink", "block", "此目录保存重要数据，禁止删除。请在任务临时目录中操作。", ["openclaw__openclaw::123", "zeroclaw-labs__zeroclaw::34"], "RQ1 提炼；论文图 9", "unlink 保护不等于防止覆盖、truncate、rename 替换或 rmdir；完整数据完整性策略需合并相应事件并做绕过验收。"),
    ("P06", "任务写入范围", "任务范围", "scene", "file", "/workspace/**", "write", "block", "写入超出了当前任务范围。请修改已分配目录或申请范围调整。", ["abhigyanpatwari__GitNexus::2"], "RQ1 提炼", "策略实际形式是 block write any unless target allowlist；目标目录由场景实例化，子 Agent 可再缩小，不能扩张父域许可。"),
    ("P07", "其他会话与业务数据隔离", "任务范围", "scene", "file", "/sessions/other/**", "open", "block", "此资源属于其他会话或受保护业务。请通过授权接口访问。", [], "架构扩展", "需要可信 session/domain 与资源归属映射；绝不能仅靠当前目录或 PID 展示推断隔离已生效。"),
    ("P08", "危险 Git 操作", "代码与发布", "workflow", "argv", "git --force / reset / clean", "exec", "kill", "此操作可能覆盖历史或删除其他工作。请提交变更说明并走受控流程。", ["earendil-works__pi::36", "earendil-works__pi::39", "OthmanAdi__planning-with-files::5"], "RQ1 提炼", "当前单 argv token 匹配只支持事后 kill/notify；reset、-f、. 等粗粒度匹配会误伤，且不能覆盖 libgit2 或自制客户端。需规范命令解析与底层资源保护。"),
    ("P09", "发布与远端推送", "代码与发布", "workflow", "argv", "git push / npm publish", "exec", "kill", "发布会改变共享状态。请准备发布内容并申请批准。", ["colbymchenry__codegraph::51"], "RQ1 提炼", "当前 kill 不承诺共享状态未改变。可靠发布审批需要可信执行器、不可伪造且绑定对象/版本/有效期的授权、外部系统权限与底层事件控制。"),
    ("P10", "按分支限制提交", "代码与发布", "workflow", "branch", "main / other branches", "commit", "kill", "main 分支禁止直接提交，请使用工作分支和受控合并。", ["OthmanAdi__planning-with-files::5"], "用户需求；RQ1 相关动机", "原例是禁止 force-push master，不能据此声称支持 main commit 分类。git commit argv 不提供当前分支。需要可信仓库/HEAD/ref 解析及对原子 ref 更新的强制中介；当前不生成可执行 DSL。"),
    ("P11", "提交前测试通过且结果新鲜", "代码与发布", "workflow", "gate", "git commit ← tests passed", "exec", "kill", "最新代码修改之后尚无成功测试记录。请运行项目测试并通过后再提交。", ["chenhg5__cc-connect::29", "chenhg5__cc-connect::38"], "RQ1 提炼；论文图 9", "after gate exits 0 since write；测试命令/覆盖路径由场景确定。不能把任何 go 进程当作测试，更不能把任意成功退出当成可信测试验收。argv commit 仍为事后处置；事前阻断要配可信提交中介。"),
    ("P12", "生成文件走规定生成器", "代码与发布", "scene", "file", "/workspace/data/hf_models.json", "write", "block", "此文件由生成器维护。请运行规定生成器后检查结果。", ["AlexsJones__llmfit::17"], "RQ1 提炼", "原 YAML 的 python* 祖先只证明某 Python 进程参与，不证明执行了指定脚本。生产模板需可信生成器身份和固定输入/产物凭据。"),
    ("P13", "网络目的地范围", "网络与数据流", "scene", "network", "10.0.0.", "connect", "block", "目标地址不在当前会话允许范围内。请使用已批准服务。", ["earendil-works__pi::22"], "RQ1 相关例；研究扩展", "优先明确数值 IPv4 支持；域名、DNS、IPv6、代理、现有连接与 UDP 需要单独验证。必须预留 Agent/模型正常工作所需连接。"),
    ("P14", "读取秘密后禁止外联", "网络与数据流", "scene", "flow", "/workspace/.env → external endpoint", "connect", "block", "当前进程处理过秘密数据，不能向未批准目的地发送。请使用脱敏流程。", [], "论文 §3.3 的 IFC 示例", "基于来源标签而非文件内容扫描；会保守传播且可能过度污染。已建立连接、send/recv、IPC、继承环境和启动前历史都需要覆盖证据。"),
    ("P15", "输出、隐私与业务承诺", "通用约束", "semantic", "semantic", "报告 / 消息 / 业务行为", "review", "notify", "请隐去隐私信息；结论注明证据；对外承诺前请求确认。", ["nearai__ironclaw::28"], "通用语义约束", "可统一展示，但由内容检查、Agent 或业务授权接口执行。文件名命中与 notify 不能证明没有泄露或没有削弱鉴权。"),
]


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--artifact-repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    raw = args.corpus.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    assert len(rows) == len({r["uid"] for r in rows}) == 607
    assert collections.Counter(r["enforceability"] for r in rows) == {"per_event": 392, "cross_event": 215}
    assert all(r["compile_status"] == "compiled" for r in rows)

    def show(path):
        return subprocess.run(["git", "-C", str(args.artifact_repo), "show", f"{PIN}:{path}"], check=True, capture_output=True).stdout

    manifest = {r["repo"]: r for r in map(json.loads, show("docs/corpus/manifest.jsonl").decode("utf-8").splitlines())}
    batch_records = {}
    for batch in range(1, 8):
        data = show(f"{BASE}/batches/batch{batch:02d}/batch.jsonl")
        for record in map(json.loads, data.decode("utf-8").splitlines()):
            batch_records[record["uid"]] = (batch, record)
    for row in rows:
        original = batch_records[row["uid"]][1]
        assert row["directive"] == original["directive"], row["uid"]
        assert row["source_file"] == original["source_file"], row["uid"]
        assert row["source_lines"] == "-".join(str(n) for n in original["lines"]), row["uid"]
    # Verify every exported policy body against the frozen Git blob in one batch.
    paths = [f"{BASE}/batches/batch{batch_records[r['uid']][0]:02d}/policies/{r['policy_file'].rsplit('/', 1)[-1]}" for r in rows]
    proc = subprocess.run(["git", "-C", str(args.artifact_repo), "cat-file", "--batch"], input="".join(f"{PIN}:{p}\n" for p in paths).encode(), check=True, capture_output=True)
    import io
    stream = io.BytesIO(proc.stdout)
    for record in rows:
        header = stream.readline().split()
        assert len(header) == 3 and header[1] == b"blob"
        body = stream.read(int(header[2]))
        assert body.decode("utf-8").strip() == record["policy_yaml"].strip(), record["uid"]
        assert stream.read(1) == b"\n"
    assert not stream.read()

    selected = {uid for t in TEMPLATES for uid in t[9]}
    evidence = []
    for row, policy_path in zip(rows, paths):
        if row["uid"] not in selected:
            continue
        item = {k: row[k] for k in ["uid", "repo", "source_file", "source_lines", "directive", "policy_yaml", "enforceability"]}
        source_path = row["source_file"].removeprefix(row["repo"] + "/")
        file = next(f for f in manifest[row["repo"]]["files"] if f["path"] == source_path)
        lo, hi = row["source_lines"].split("-")
        item["source_url"] = f"https://github.com/{row['repo']}/blob/{file['last_commit_sha']}/{source_path}#L{lo}-L{hi}"
        item["artifact_url"] = f"https://github.com/eunomia-bpf/ActPlane/blob/{PIN}/{policy_path}"
        evidence.append(item)
    assert selected == {e["uid"] for e in evidence}
    keys = ["id", "name", "category", "scope", "kind", "target", "operation", "effect", "reason", "evidence_uids", "origin", "limitations"]
    clauses = collections.Counter(re.findall(r"^\s+(notify|block|kill)\s", "\n".join(r["policy_yaml"] for r in rows), re.M))
    result = {
        "schema": "agentscope.safety-catalogue.proposal.v1", "status": "research_design_only",
        "paper": PAPER, "artifact_commit": PIN, "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "verified_policy_bodies": 607, "verified_directive_records": 607, "independent_policies": 607,
        "policy_types": {"per_event": 392, "cross_event": 215},
        "local_effect_clause_counts": dict(clauses),
        "count_note": "Local regex count is 1277 effect clauses; the paper says 1283 rule lines. Counting units/version alignment are not established; do not substitute either for policy count.",
        "ssh_literal_directive_hits": sum(".ssh" in r["directive"] for r in rows),
        "templates": [dict(zip(keys, t)) for t in TEMPLATES], "evidence": evidence,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "policy-catalogue.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    template = (Path(__file__).parent / "prototype.template.html").read_text(encoding="utf-8")
    embedded = json.dumps(result, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    assert template.count("__CATALOGUE_JSON__") == 1
    html = template.replace("__CATALOGUE_JSON__", embedded)
    output = args.out.parent / "prototype" / "AgentScope-平台底线与会话安全配置.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(json.dumps({"templates": len(TEMPLATES), "evidence": len(evidence), "verified_policy_bodies": 607, "corpus_sha256": result["corpus_sha256"], "clauses": dict(clauses)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
