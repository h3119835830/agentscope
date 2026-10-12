# AgentScope Agent 与工作区策略生成架构复核

日期：2026-10-11。结论：按用户确认更新目标架构；本轮验收范围为文档一致性、引用与变更边界。新增生成合同和工作区执行绑定待实现，不代表源码、18003 界面或内核策略已发布。

关联 [RFC](../RFC/RFC-20261011-AgentScope-policy-control-architecture.md)、[ADR](../ADR/ADR-20261011-AgentScope-policy-control-decisions.md)、[问题差距记录](../BUG/BUG-20261011-AgentScope-policy-ui-gaps.md)。此前现场审计保留在 [原评审](REVIEW-20261011-AgentScope-architecture-audit.md)，不以旧状态证明本轮运行结果。

## 1 采纳的设计

策略生成主要集中在两个目标：为真实 Hermes、DSH 等实例生成 Agent 基线；为该实例的真实工作区生成项目约束。Agent 基线不强制选择会话或读取项目；工作区策略需可信身份与实际项目路径，会话仅按需提供补充上下文。会话/任务局部增量保留为补充能力，须有可信执行绑定。系统共同底线继续由有权管理员配置。

默认工作区目标是 `(instance_id, workspace_id)`。共享项目资产可复用，但不能自动向其他 Agent 授权。配置继承可表示系统 → Agent → 工作区 → 会话/任务 → 子 Agent；这是产品映射，ActPlane 的通用单父域通过控制面组合配置落地。平台强制约束须保留不可覆盖绑定，不能把 default 当作 locked。

## 2 源码与论文核对

| 依据 | 核对结果 | 对本设计的约束 |
|---|---|---|
| [ActPlane 论文 §3.4](https://arxiv.org/html/2606.25189v2#S3.SS4) | 域绑定进程树，子域不能削弱上级安全约束；未固定产品对象层名 | 工作区层是 AgentScope 映射，不能宣称论文规定了固定 Agent→工作区→会话顺序 |
| [上游架构计划](https://github.com/eunomia-bpf/ActPlane/blob/master/docs/design/arch_plan.md) | project 位于 session 之前，另有 workspace_scope；文件描述长期目标 | 设计依据与已实现能力分开 |
| [配置解析源码](https://github.com/eunomia-bpf/ActPlane/blob/master/crates/actplane-runtime/src/config.rs) | DomainEntry 有单一 parent；resolve_domain_inner 递归继承，区分 locked/default | 多来源配置先组合为有效策略，不构造多父内核域 |
| [内核域源码](https://github.com/eunomia-bpf/ActPlane/blob/master/bpf/capability.bpf.h) | cap_task 将 PID 关联到 domain，cap_state 包含 parent、scope_id 等 | cwd、目录名称和 scope_id 都不能单独证明工作区隔离 |
| AgentScope `history/agent_context.py::snapshot` | 仍需选定原生会话后形成环境快照 | Agent 基线无会话生成待解耦 |
| 同文件 `selected_candidate` | scopeType=agent，提示影响实例全部会话 | 引用某会话不是会话级应用；工作区候选不能沿用该范围 |
| `instances/dsl_policy.py::documents_for` | 当前仅组合 system 与 instance | workspace 作用域的存储、审批及应用尚需实现 |

本轮读取的本地源码位于 `/opt/agentscope-agent-sources-20261011/backend/agentscope_app/` 及同目录的 `actplane/`。上游 master 文档与源码于 2026-10-11 另行核对，引用不代表本地 vendored 快照或 live 组件已同步更新。未执行源码、策略确认或内核探针。

## 3 风险与整改

| 风险 | 设计处置 | 实现验收 |
|---|---|---|
| 生成上下文被当成应用范围 | 生成前固定 scope/target；会话引用可选；切换范围创建新候选 | RFC A1、A5、A6、A11 |
| 同 Agent 不同项目或不同 Agent 共用路径导致串用 | 原生工作区身份、精确归属、实例与工作区联合目标；按目标查询对话和候选 | A2、A3、A4 |
| 共享执行器无法区分工作区 | 候选保持不支持/待补充；旧 Agent 接口拒绝 workspace 候选；不得扩大到实例 | A6、A8、A9 |
| 审批时环境漂移，未来会话漏继承 | 冻结身份、成员和基线；确认前复核；未来执行前绑定；切换工作区先暂停并复核 | A7、A8、A10、A11 |
| 配置图被误解为内核隔离或底线可覆盖 | 分开记录配置继承和实际 PID/domain；locked 强制约束保留；以真实 allow/block 验证 | A9、A12 |
| Hermes 侧改造越界影响普通业务 | 本轮仅文档；后续仍限 Hermes/隔离集成层，经现有业务接口调用 | A12；普通业务在 AI 不可用时仍可用 |

工作区路径限制与工作区执行主体隔离分别验收。让一个共享实例只能写某目录，可能影响其他工作区，不能作为只作用于所选工作区的证明。能力不足时明确保留缺口；不增加例外提示词掩盖上下文或绑定错误。

## 4 本轮文档验收

已执行 UTF-8/Markdown 结构、相对链接及锚点、作用域字段与继承关系、Agent/工作区两条主线、人工确认与漂移、当前实现边界、全部变更差异和文件范围检查。文档检查通过；结果、检查数量与交付文件 SHA256 记录在 [validation.json](evidence/agent-workspace-policy-20261011/validation.json)。新增 A1–A12 是后续实现的验收合同，本轮不把它们计作已通过的运行测试。

本轮交付文件为总体 RFC、ADR、原 REVIEW 补记、BUG 差距补记、第三步 RFC 后续方向、架构导读、本专项 REVIEW 及文档验收 JSON。保留既有审计证据和源码进展，不覆盖其他工作；普通业务代码、数据库、服务和现有 Agent 权限均无变更。
