# AgentScope 四层第一步验收

日期：2026-10-12。代码基点：`9968d083e4545ee507883777aa60583f3ddf181a`；实施分支：`codex/policy-targets-step1-20261012`。实际 API/UI 发布目录：`/opt/agentscope-policy-targets-20261012-202018`，入口 18003；18115 合成只读预览未修改。

## 结论

本步完成服务端固定目标、独立局部候选审批及能力不足拒绝应用。仓库场景默认 workspace，运行时需求默认来源 session。局部候选不再导入 Agent DSL；服务端确认请求拒绝，未发生权限扩大。共享原生 DSH 的独立工作区／会话加载器仍不存在，故本轮没有局部策略成功加载、内核会话隔离或新一轮“可读不可改”执行验收。

## 自动测试

| 检查 | 结果 |
|---|---|
| 后端广泛回归，排除已知 outbox 顺序污染用例 | 1,138 passed、11 skipped、1 deselected |
| outbox 用例独立执行 | 1 passed；不计作单次完整全套通过 |
| 最终审批、目标、客户可见性及位置回归 | 49 passed；包含并发读取共享、后续读取新鲜性和失败重试 |
| 前端所有 Node 测试 | 256 passed |
| Vite 生产构建 | 通过；既有 >500 kB bundle 提示保留 |
| Python 发布脚本编译、Git diff 空白检查 | 通过 |

关键断言包括来源会话精确目标、同工作区不同会话指纹不同、伪造 target/binding/documents 被拒、认证和跨 Agent 归属、幂等与重复拒绝、环境漂移不能应用、旧运行时提案不能全实例确认、局部文档不能转入系统／Agent，以及既有人工配置和 managed task 审批保留。局部测试若触达 Broker／适配器立即失败，同时比较权限表快照。

## 真实连接与接口验收

使用已连接 DeepSeek Harness 的原生会话 `session-f1aaccc8-ab10-4719-9499-0c1f2af76996`，实例 `instance-1f4469579e8947f4`，真实模型生成独立需求“禁止修改 README.md 文件。”。运行时和读取仓库场景后的生成分别得到下列目标；没有新启动 DSH 执行任务或加载候选。

| 入口 | 审批记录 | 冻结目标 | 确认结果 |
|---|---|---|---|
| 无场景的当前会话需求 | `local:3ebb3113ec664e08ba2e680db2134afe` | session + 指定实例／原生会话，workspace_id 为空 | blocked，can_apply=false，HTTP 409 |
| 读取仓库场景后的需求 | `local:65bc2389725a4cfb87b1d4180e65178a` | workspace + 指定实例；workspace_id 未取得，session_id 为空 | blocked，can_apply=false，HTTP 409 |

运行时生成作业为 `cac939d8214647328baf048af79b6668`，仓库读取作业为 `c4a07a20f2a04ae1ab919d088df1d8ae`，场景生成作业为 `49bee2bf7c684ddf874ae35308352388`。生成 DSL 约束 write，未生成 read 禁止。重复提交返回相同审批，确认两类局部目标均拒绝，整个范围验收期间各实例的 policy_hash、运行代次、PID、domain_id、active 和所有 DSL revision/document_hash 均未变化。

最终发布后再次检查统一目录、两种详情及 HTTP 409，目录读取 **4.607 秒**，在页面 10 秒上限内；这是当前真实负载下的一次测量，不是吞吐量保证。经审查的证据：[真实接口](../evidence/policy-targets-step1-20261012/live-api.json)、[发布与恢复](../evidence/policy-targets-step1-20261012/release.json)。证据只保留目标、状态、运行身份和摘要，不含凭证、数据库原件或模型私有推理。

## 真实界面

Chrome 打开 18003，审批 → 需要处理 → 搜索 README，实际显示工作区／仓库场景和会话／运行时提案两条记录。工作区显示“工作区身份待核验”，会话显示“当前会话及其子进程”；均为“暂不能应用”。两种详情只提供拒绝，没有“批准并应用”按钮，显示“未应用，权限保持不变”。

- [审批目录截图](../evidence/policy-targets-step1-20261012/approvals-local-targets.jpg)
- [会话审批截图](../evidence/policy-targets-step1-20261012/session-approval-blocked.jpg)
- [工作区审批截图](../evidence/policy-targets-step1-20261012/workspace-approval-blocked.jpg)
- [策略助手截图](../evidence/policy-targets-step1-20261012/assistant-local-targets.jpg)：同一来源会话的运行时／仓库场景候选分别显示冻结范围；读场景后的输入标为工作区候选

历史 Agent 范围记录仍可显示“全部工作区与会话”，并保持其历史范围；不能将它们改名为局部已授权策略。当前范围验收记录均未扩大。

## 发布事件与未通过项

第一次 API 发布优雅停止超出 Broker 8 秒存活检查，导致三个受控原生实例退出。已回滚并按原批准配置恢复三实例，运行代次更新，策略哈希及 DSL 配置保持原值。后续发布增加空闲检查、API 3 秒停止上限，并比较前后权限及运行身份；最终发布快照完全相同，Broker 和 18000／18004 保持原进程。没有降低 Broker 存活保护。

真实“只读 sales.csv”额外生成任务 `d39ee18e61494f6db06638be2345819e` 返回 needs_clarification，错误澄清 read-only open 与内容读取；不能写成只读生成通过，也未加特例提示词。另一个只读实例的场景扫描遇到历史 root-owned 文件访问失败，未放宽权限。均见 [BUG](../BUG/BUG-20261012-AgentScope-policy-targets-step1.md)。工作区／会话内核隔离、上层约束与后代生命周期的下一阶段验收仍未执行。

关联：[RFC](../RFC/RFC-20261012-AgentScope-policy-targets-step1.md)、[ADR](../ADR/ADR-20261012-AgentScope-local-policy-fail-closed.md)、[REVIEW](../REVIEW/REVIEW-20261012-AgentScope-policy-targets-step1.md)。本轮仅本地提交，未推送远端。
