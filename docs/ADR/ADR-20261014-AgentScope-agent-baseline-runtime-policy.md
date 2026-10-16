# ADR：固定配置到 Agent，后续采用真实域运行时增量

日期：2026-10-14，执行绑定复核之后的用户收敛决定。状态：采纳为当前目标；实现迁移和运行验收另行完成。

## 决定

1. 固定配置只保留系统策略与 Agent 基线。工作区、会话是原生主体、场景来源和运行视图，不要求拥有独立策略库、独立应用接口或独立 ActPlane 域。
2. 后续需求通过 RuntimeChange 提出，初始候选即固定真实 ActPlane 域及全体受影响执行；origin_session/workspace 不决定授权范围或期限。共享 Agent 域是合法明确的增量目标，不能从局部旧候选偷偷扩大为域策略。
3. 系统/Agent 强制规则继承保留；收紧、扩权、停用和推广均需相应人工权限、批准及显式应用。Agent 提案不等于自动加载。
4. 域身份和进程绑定、共享执行/可用性影响、机制覆盖、原生取消与停止边界继续采用[执行绑定合同](../RFC/RFC-20261014-AgentScope-execution-binding-rederivation.md)。ActPlane 使用通用进程域，不把 Agent 产品名当作内核身份。
5. 默认运行时规则绑定当前真实域的运行代次；来源会话结束不自动删除，下一代次不自动成为长期基线。长期保留须重新起草 Agent 基线并审批。
6. 原生可信子域是可选增强；不强制拆 DSH worker，不修改原生工作区/会话/工具流程。静态两层不等于禁止实际父子域或多执行单元。
7. 会话页面继续显示可视化安全与 DSL，但展示其实际执行域继承和运行时规则，共享范围明确可见。无绑定或机制不足显示未知/不支持。

8. 共享域为默认产品运行模型；各会话读取同一已核验活动版本，增量经域版本协调器串行应用。完整快照、前置版本和可信单写入是目标合同，不因此采纳未实现的原子热更新或无损交接。

## 部分取代与保留

取代[四层 ADR](ADR-20261012-AgentScope-four-layer-policy.md)关于工作区/会话固定所有权层的决定，以及[执行绑定重推 ADR](ADR-20261014-AgentScope-execution-binding-rederivation.md)保留四层固定配置的部分。已有系统/Agent、人工确认、材料不等于权限、精确绑定和共享门禁保留；历史验收和未应用候选不改写。

退出当前目标的局部独立加载器不能标为“实现修复”。遗留候选和接口按原语义读取或拒绝，新的真实域范围重新起草、确认，不批量迁移已批准权限。

## 取舍和验证

两层基线与 ActPlane 进程域模型及当前 system/instance 主组合一致，减少原生 Agent 流程侵入和虚构局部生效；代价是共享域内会话共同受增量约束，无法承诺任意会话独享权限。规则内容可包含具体路径等对象范围，但这不等于工作区主体隔离。

ActPlane 当前 Add 原语不代表通用热更新/删除已实现；[热更新提案](../RFC/RFC-20261014-AgentScope-hot-policy-lifecycle-proposal.md)仍为未实施备选。本轮仅文档静态验证，见[REVIEW](../REVIEW/REVIEW-20261014-AgentScope-agent-baseline-runtime-policy.md)；运行缺口见[BUG](../BUG/BUG-20261014-AgentScope-agent-baseline-runtime-policy.md)。完整合同见[新 RFC](../RFC/RFC-20261014-AgentScope-agent-baseline-runtime-policy.md)。

默认共享架构的模块、最小数据关系、启动/增量/取消链路及订单日报示例已补入 RFC §4.5/§5.1–5.4；静态检查见[回执](../REVIEW/evidence/agent-shared-runtime-design-20261014/validation.json)。
