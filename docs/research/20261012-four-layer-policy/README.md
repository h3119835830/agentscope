# AgentScope 四层策略与 ActPlane 调研附件

日期：2026-10-12。交付范围为论文/源码审计、目标架构、案例索引、复现合同和静态验收；没有改运行权限或进行新的 DSH/内核实验。

建议先读 [交付导读](../../AgentScope-四层策略架构与ActPlane调研-20261012.md)，再读 [四层 RFC](../../RFC/RFC-20261012-AgentScope-four-layer-policy.md)。

| 附件 | 内容 |
|---|---|
| [源码审计](source-audit.md) | 论文→代码→测试→当前产品差距、分项成熟度 |
| [生成器审计](generator-audit.md) | ActPlane 来源链、Progent、FIDES、CaMeL、PCAS 采用决定 |
| [案例清单](case-catalog.md) | E1–E13、实际 12 个夹具、四组 benchmark 的复用边界 |
| [复现方案](reproduction-plan.md) | 后续四层/八类案例的真实 DSH 验收步骤、依赖与判据 |
| [版本锁](source-lock.json) / [文件证据](source-evidence.json) | 四个项目的五个源码快照、五个固定版本论文、56 个源文件摘要/符号 |
| [生成来源](generation-provenance.json) | RQ4/RQ5 清单、生成代码和未闭合来源 |
| [上游静态结果](upstream-artifact-check.txt) | 实际执行 frozen artifact 检查，非 benchmark 重跑 |
| [案例 JSON](case-catalog.json) / [基准 JSON](benchmark-catalog.json) | 可验证的索引、依赖、许可、允许/拒绝预期与风险 |
| [文档验收](validation.json) | UTF-8、链接、源版本/摘要、案例、合同、差异及同步结果 |

维护脚本：collect.py 读取固定缓存并复核公开 artifact；render_catalog.py 从审定注释生成案例文档；validate.py 只检查文档、源证据与变更边界。上述脚本均不调用模型、不启动 Agent、不装载 eBPF、不调用策略应用接口。

源码缓存默认位于 `/tmp/agentscope-four-layer-audit-20261012`，不作为交付文件或复现的永久依赖；按 source-lock 指定提交可重新取源。论文 HTML 的获取摘要留存但全文不提交。私有会话、凭证、完整数据库和模型推理不进入仓库。
