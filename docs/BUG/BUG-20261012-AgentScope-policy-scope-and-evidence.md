# BUG / GAP：局部策略范围与验收证据边界

日期：2026-10-12。本文区分已完成的文档纠正、当前实现缺口和上游来源待核实事项，不将所有缺口称为已证实安全漏洞。关联 [RFC](../RFC/RFC-20261012-AgentScope-four-layer-policy.md) 与 [REVIEW](../REVIEW/REVIEW-20261012-AgentScope-four-layer-audit.md)。

## SCOPE-DOC-001：真实会话执行被误解为会话级策略隔离

状态：文档纠正完成；局部隔离能力尚未完成。

复现证据：2026-10-11 在真实原生会话 session-71c5083e-23a1-4963-916b-33c6ebbf8868 执行探针；selected_candidate 固定 scopeType=agent，提案 6ccdbda0250d4cd3acac31a5a96c4d92 走实例 DSL。批准后该实例所有工作区/会话继承，界面显示此真实范围。23 项操作通过没有覆盖第二会话或第二工作区对照。[历史验收](../acceptance/20261011-policy-source-semantics-dsh/README.md)

纠正：保留 Agent 范围只读语义和审批边界结论；明确“运行时会话是执行者/上下文，作用域仍是 Agent”。新的 scene/runtime 默认目标分别是 workspace/session，并要求可信独立绑定。不能仅删掉“全部工作区与会话”，也不能改写历史审批为 session。

验收：RFC、ADR、REVIEW、导读及原验收补记均一致；历史 JSON 未被更改、未添加会话隔离通过字段。本次静态检查完成；执行隔离另按 A03–A12 验收。

## SCOPE-IMPL-001：workspace/session 原生局部写链路缺失

状态：开放，实现待后续任务。

源码证据：dsl_policy.documents_for 只组合 system + instance；dsl_api 没有 workspace/session DSL 写接口；Broker.observe 与 sessions.policies 返回 executor_shared=True。managed 的固定任务域不能直接映射成任意原生 DSH 会话的独立域。

新合同：冻结联合目标、上层版本、真实工作区归属和原生会话；缺少绑定能力时阻止局部应用，不回退至实例范围。新增存储/审批/回执、多 ExecutionBinding、独立 DSH worker 及生命周期，保留已有系统/Agent 合同。

关闭条件：A03 同工作区双会话、A04 同 Agent 双工作区、A05 跨 Agent 共用仓库、A06 子孙进程、A07 未审批不变、A08 上层不可绕过、A09 回收/PID 复用、A10 不支持拒绝、A11 故障恢复和 A12 真实 OS 对照均通过。当前文档设计不关闭该项。

## SOURCE-GAP-001：RQ4/RQ5 生成与运行来源链未闭合

状态：开放的可复现性差距，不作研究不当行为判断。

论文描述 Codex 生成；artifact 的 description-only 首轮脚本使用关键词/正则，manifest 为 311 项、58 no-op，另有 50 个最终策略。已核对所有 361 个 ledger 行均无逐任务 outcome，RQ4 的 21 个 ledger 行均无逐任务 reward。raw backup 的定向代码/README 检查未补齐统一模型生成、最终修订和 110 条增量的可复算对应。

处置：在 [生成器审计](../research/20261012-four-layer-policy/generator-audit.md) 中区分来源组、代码与论文主张；不把 artifact 静态检查通过写成模型或 benchmark 复现。关闭需要可验证的生成输入/模型/版本/修订/产物映射及对应运行回执，且不得提交私有推理或凭证。

## CASE-DOC-001：示例名被外推为完整产品保证

状态：本次案例文档整改完成，原语/产品复现待实施。

核对：文档 13 例；默认 YAML 12 case，E8 合并 E1、另有 E5b、E13 未独立覆盖。E4 只测 unlink，E6 只测 git，E11 夹具为 lineage gate，E5/E13 的 exec gate 不证明测试/检查成功；E12 只测混合标签提交，不是完整非干扰保证。驱动使用替身进程和 NDJSON 断言，不是真实 Agent 会话。

处置和验收：机器清单逐例记录 DSL、夹具、允许/拒绝控制、风险、依赖、许可和复用分类；后续八类矩阵补齐真实执行、范围、可信 gate 与任务效用。没有将未运行的案例计为通过。
