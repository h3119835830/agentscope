# REVIEW：Pi 启动策略生成长路径故障与复验边界

状态：根因已确认，修复已部署，同源新任务已完成真实 Pi 生成、编译和服务器提交；停在人工审核前。2026-10-08 独立只读复核仍一致。原失败任务保留，未自动迁移或重试。

## 结论与事实

此次“Pi 用不了”发生在 AgentScope 的任务快照路径与执行引擎能力合同之间。旧任务的精确保护目标为 77–92 UTF-8 字节，超出 ActPlane 64 字节 pattern ABI；Pi 完成补读后仍无法让这些目标通过服务器 IR 校验。随后 RPC 状态遗漏真正业务诊断和剩余校验预算，最终只显示 `Pi settled without a server-validated submission`。这条结束错误不能据此归因为模型服务商故障，也不是模型智能不足的证据。

| 对象 | 原失败任务 | 同源修复复验任务 |
| --- | --- | --- |
| task | `0dae79b573f14bca` | `ad7c53a17c334c7b` |
| Pi job | `d5cb5fcc741848589eff12f2be82404c` | `948e76e023fe480aa959a62a8d556eb1` |
| 作业结果 | failed；无候选 | completed；服务器候选 validated |
| 当前控制面 | phase/gate=failed | phase=policy_review；gate=waiting_confirmation |
| 候选 | 0 | 2 个执行规则 atom、7 项任务指导 |
| 有效版本 / policy_versions | 0 / 0 | 0 / 0 |
| DSH 会话 / 执行凭据 | 未建立 / 0 | 未建立 / 0 |

新任务第一次校验缺两个实际读取回执，Pi 自行补读；第二次 `valid=true`、`compile_state=compiled`，通过工具提交精确候选哈希。两任务 Pi 临时凭据均已撤销。当前成功证据是策略生成和服务器校验成功；没有人工批准、加载回执、DSH 执行或本轮业务测试成功证据。

## 根因与整改评审

1. **源快照的嵌套布局未适配执行路径预算。** 原资产保留 `workspace/transaction-verification-service/...`，加上 `/s/<task>/r/` 后部分精确文件目标超限。新任务在固定上下文前识别具有构建 marker 的独立项目根，将整个项目根映射为无冲突 `p0`；保留项目内结构、叶文件名和所有字节。原始来源路径、执行路径和映射哈希均保留。两个任务来源 manifest 相同，20 个来源资产的哈希集合一致；本次只读复核也确认两个快照的实际文件哈希仍符合冻结值。
2. **能力工具没有公开已有 64 字节约束。** 现由 `policy_ir.PATTERN_MAX_UTF8_BYTES` 提供单一常量，渲染器、能力工具和布局共用；能力还明确拒绝字符和规范绝对路径要求。长目标校验独立返回 `diagnostic_details`，包含错误代码、最大字节数和各目标实际 UTF-8 字节数。不能通过扩大目录保护、重命名叶文件或放宽校验规避限制。
3. **RPC 状态覆盖了实际业务结果。** `rpc_lifecycle` 曾成为“最后工具”，续接没有携带真正校验诊断与剩余验证预算。现在从业务回执取得最后工具和最近诊断；预算耗尽且没有服务器已验证候选时，在 settled 阶段停止并保留具体错误。已有已验证候选仍可按原哈希提交，缺读取回执不消耗语义修复预算。未增加针对本任务的专用提示词，未更改服务器验证或人工审核边界。

## 当前部署与验收证据

独立复核采用只读 SQLite `mode=ro`、`query_only` 和 bootstrap GET；未调用 Broker/status、连接检查、模型、重试、批准或加载。API PID `1071142` 的工作目录为修复仓库；7 个关键源码文件的修改时间均早于该实例启动时间，哈希保存在新增只读回执中。结合该实例完成的新 Pi job，未发现修复回退。

- Pi 与共享驱动专项：109 passed。完整后端：563 passed、52 skipped。测试结果沿用本轮实际回归日志，本次只读复核没有重复调用模型。
- 真实复验：[pi-retry.public.json](evidence/task-replay-records-20261008/pi-retry.public.json)。旧错误与 6 个超限目标：[pi-bootstrap-diagnostic.public.json](evidence/task-replay-records-20261008/pi-bootstrap-diagnostic.public.json)。
- 当前状态、资产与部署源码独立复核：[pi-bootstrap-final-readonly.public.json](evidence/task-replay-records-20261008/pi-bootstrap-final-readonly.public.json)。原 `0dae` context JSON SHA256 仍为 `70f07f460747bf8f9f7ab82075708d5ec124f7f0f2811a5657a01164e1e26d81`，与复验前回执一致。
- 真实待确认界面：[desktop-pi-review.jpg](evidence/task-replay-records-20261008/desktop-pi-review.jpg) 与 [pi-review-ui.public.json](evidence/task-replay-records-20261008/pi-review-ui.public.json)。

## 已解决与仍存在的边界

已解决：本次嵌套项目根导致的精确目标不可表示、能力合同遗漏、错误被通用 settled 提示遮蔽和预算耗尽后的无效续接。旧 `0dae` 上的失败是原作业的历史事实；旧任务当前仍为 failed，不是新复验任务的当前状态。不能在原固定上下文上未经迁移便反复重试并宣称路径问题已经自动修好。

仍受限制：64 UTF-8 字节 ABI 有效；未识别项目根、不能缩短的前缀、过长叶名等仍可能无法表示，应如实给出诊断或 unresolved，不能加载不满足约束的候选。项目根搬移并未证明所有跨项目相对引用语义等价。本次没有新的 DSH 执行或内核拦截验收；后续如需执行，须另经人工确认，并分别验证绑定、实际加载和项目功能结果。

[新同源候选审核页](http://127.0.0.1:18003/?view=workbench&task=ad7c53a17c334c7b&stage=startup)。架构与取舍沿用 [RFC](../RFC/RFC-20261008-workbench-records-pi-paths.md)、[ADR](../ADR/ADR-20261008-workbench-records-pi-paths.md)；故障闭环见 [Pi 专用 BUG](../BUG/BUG-20261008-pi-bootstrap-path-limit.md)。
