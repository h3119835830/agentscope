# BUG：RFC 提前假定原生会话独占执行与回收

2026-10-14 后续收敛决定：本文记录 ad39d60 时的设计与检查；之后固定四层目标已取代，未实现的工作区/会话固定层退出当前要求，不能把需求退出记为代码修复。 见 [当前合同](../RFC/RFC-20261014-AgentScope-agent-baseline-runtime-policy.md)。历史验收及既有批准范围不变，本轮仅文档修订。

日期：2026-10-14。类型：已复现文档设计缺陷及实现缺口跟踪。状态：文档条款已修订并通过静态检查；四层局部运行能力仍开放，未认定修复完成。

## 复现与影响

修订前四层 RFC §4 和 ADR 第 4 项指定“一原生受控会话一个 DSH worker”，其生命周期条款要求结束会话终止所属 cgroup/后代、局部应用失败不影响其他会话。会话面板 RFC 的结束与第二阶段条款沿用该前提。对原生共享进程/池，这些要求无法从现有会话身份推导，可能导致侵入原生工具、误杀其他会话或把 Agent 域规则显示成单会话生效。

文档复现证据为修订前短摘录、文件摘要和 ActPlane/AgentScope 源码锚点，见[审计 JSON](../REVIEW/evidence/rfc-execution-binding-audit-20261014/audit.json)。未通过杀进程或应用冲突策略重现线上故障；不能把风险推演记为发生过的生产事故。

## 本轮修订闭环

| 项目 | 状态 | 验证 |
|---|---|---|
| 默认每会话 DSH worker 的既定决策 | 文档已撤销 | 主 RFC/ADR 和会话面板的规范条款同步改写 |
| 无条件会话 cgroup 回收、共享失败不影响其他会话 | 文档已修订 | 独占条件、共享可用性影响、原生取消和严格撤销分别定义 |
| 目标/实际策略混淆，域数字作为独立身份 | 文档已修订 | 引入 engine_ref、ExecutionUnit/Binding、目标与加载包、覆盖机制 |
| 四层配置、人工审批、无可信绑定拒绝 | 保留 | 原文正确条款未被撤销，未扩大历史验收范围 |
| 工作区/会话完整独立加载与撤销 | 开放 | 当前 shared executor 不能由本次文档变化变成局部能力 |
| 原生 DSH/Hermes 各入口的完整拓扑与生命周期证据 | 开放 | 后续只按原生能力验证；不新加专用工具 worker |
| 当前源码到部署 ActPlane 的构建溯源及新内核验收 | 开放 | 本轮只读源码/进程摘要，不宣称完整运行等价 |

静态回执见[validation.json](../REVIEW/evidence/rfc-execution-binding-audit-20261014/validation.json)。后续运行修复须通过新 RFC A13–A20 与原 A01–A12 中适用的正向场景；尤其是同 PID 同路径并发冲突、工作区交叉访问、旧资源/后台执行撤销和不误杀共享服务。能力不足拒绝通过，不代表局部功能通过。

## 对应合同

[新 RFC](../RFC/RFC-20261014-AgentScope-execution-binding-rederivation.md)、[部分取代 ADR](../ADR/ADR-20261014-AgentScope-execution-binding-rederivation.md)、[评审](../REVIEW/REVIEW-20261014-AgentScope-rfc-execution-binding-audit.md)。本次无应用代码修改、Agent/服务重启或部署；不对既有保护作隐式卸载。
