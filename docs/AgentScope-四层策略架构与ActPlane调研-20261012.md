# AgentScope 四层策略架构与 ActPlane 调研交付

2026-10-14 后续收敛决定：本文为四层历史导读，固定四层目标现已由系统/Agent 基线与真实域运行时增量取代。 见 [当前合同](RFC/RFC-20261014-AgentScope-agent-baseline-runtime-policy.md)。历史验收及既有批准范围不变，本轮仅文档修订。

2026-10-14 修订：四层归属保留，默认独立 DSH worker 的选型已撤销；当前规范以 [执行绑定重推 RFC](RFC/RFC-20261014-AgentScope-execution-binding-rederivation.md) 和修订后的四层 RFC 为准。历史文档验收不变，本次无应用代码/运行发布。

2026-10-12。已完成论文、固定提交源码、公开 artifact 与现有实现的审计，并完成文档静态验收。此次交付的是架构和研究结论，工作区/原生会话局部策略尚未实现或发布。

四层设计合理：系统提供共同底线，Agent 提供实例基线，工作区提供仓库场景约束，会话提供当前运行时局部约束，任务/子 Agent 继续委托。两类 MD 都可引用，但材料不决定授权范围。四层配置和实际执行域必须分别建模；按原生能力解析真实执行单元和共享关系，在批准后核验相应机制的实际加载包；不默认拆分原生工具或新建会话 worker。

上一轮 DSH 测试证明了 Agent 级只读规则在真实会话中的效果和审批边界，未证明会话/工作区隔离。显示“全部工作区与会话”源于实际实例级接口，不能仅改文案消除。现有 Agent 规则保留原范围；将局部建议推广为 Agent 策略必须重新审批。

ActPlane 已有 DSL、编译、信息流、域、运行时增量和反馈工程基础。公开材料尚不能直接提供完整四层治理产品：RQ4/RQ5 的生成和逐运行来源链未闭合；13 个文档示例与 12 个测试夹具存在语义/覆盖差异。Progent 最适合借鉴生成/更新的职责分解，FIDES/CaMeL 适合借鉴上下文信任与隔离，PCAS 作为因果授权解释参考；均不直接替代 AgentScope 的人工审批和 OS 执行权威。

推荐阅读顺序：

1. [四层架构 RFC](RFC/RFC-20261012-AgentScope-four-layer-policy.md)：范围、目标、继承、worker、存储/接口、UI 和 A01–A12。
2. [架构 ADR](ADR/ADR-20261012-AgentScope-four-layer-policy.md)：采纳、未采纳及取舍。
3. [源码与成熟度审计](research/20261012-four-layer-policy/source-audit.md)：当前事实与不能外推的能力。
4. [策略生成器比较](research/20261012-four-layer-policy/generator-audit.md)：具体入口、风险和采用决定。
5. [案例与复现](research/20261012-four-layer-policy/case-catalog.md)：13 例、其他 benchmark 与八类后续步骤。
6. [评审](REVIEW/REVIEW-20261012-AgentScope-four-layer-audit.md) 与 [问题闭环](BUG/BUG-20261012-AgentScope-policy-scope-and-evidence.md)：已完成的文档整改和仍开放的实现缺口。

验收证据在 [研究附件](research/20261012-four-layer-policy/README.md)。本次只有文档/审计附件变更，不修改普通业务、应用后端、前端、已有策略或运行服务；本地提交不代表远端发布。远端推送和文档 PR 仍需新的明确推送许可。
