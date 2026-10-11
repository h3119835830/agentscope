# AgentScope 策略治理架构与当前实现评审

日期：2026-10-11。适用：本机 18003 AgentScope 与其 ActPlane 受控执行链。

AgentScope 的产品价值是将用户配置和场景建议连接到可审核、可追溯的操作系统执行约束。当前模块已具备工程基础，但场景文件读取、统一运行时审批和会话作用域仍需贯通；当前可展示架构与已有交互，不能宣称完整安全闭环已经验收。

推荐阅读顺序：

1. [架构设计](RFC/RFC-20261011-AgentScope-policy-control-architecture.md)：产品定位、威胁模型、模块边界、策略对象、继承与执行域、接口、四类生成入口及解耦路线。
2. [技术决策](ADR/ADR-20261011-AgentScope-policy-control-decisions.md)：统一策略对象与人工审批，复用场景采集，区分配置关系和真实执行域。
3. [当前实现与 UI 评审](REVIEW/REVIEW-20261011-AgentScope-architecture-audit.md)：现场状态、源码依据、卖点与展示边界、重叠和优先整改、测试及截图。
4. [已复现问题](BUG/BUG-20261011-AgentScope-policy-ui-gaps.md)：六个开放问题及各自修复验收条件。
5. [PR 说明](releases/20261011-architecture-review-pr.md)：本次仅文档的变更范围和验证结果。

本次文档不修改运行代码或应用策略。所有整改保持待实施状态，避免把设计和审查写成已经发布的能力。历史文件按各自时间与范围阅读；本设计不将旧环境的测试结果合并为当前 18003 安全验收。
