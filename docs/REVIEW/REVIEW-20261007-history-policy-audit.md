# REVIEW：历史策略与审计可发现性修订

状态：实现进行中，未宣称完成。

范围仅AgentScope任务档案接口、界面和文档，不改权限审批合同或普通业务。三方分工：后台只读聚合、前端档案页签、独立安全与浏览器验收；主会话负责入口、集成和WINDOWS/MAIN发布。

真实基线任务bef449047cd24af6包含v1-v4与22条内核拒绝加18条独立效果核验（OS分类共40条）、48条DSH工具事件；4821ac737a1a4f65包含16条内核拒绝加12条独立效果核验（OS分类共28条）、14条DSH工具事件。OS动作来源为independent_probe，展示独立验收探针；不得为了展示效果改称DSH自行触发。两任务已结束，不因查看历史重新执行。

## 真实接口复核

18003已发布index-Y_5x-wWv.js / index-D67YD5dc.css，index SHA256 352ef3d0d77388a4d05c8774cdde46b2abbd58aa5d800545ff1ff14e62320fee。API重启前确认Pi生成和managed作业均无queued/running；原生DSH与Broker未重启。

两任务完整读取新策略list/detail：bef运行前2批、运行时12批，含拒绝、过期及无变化；v3/v4真实已批准/加载且完整delta可查。482运行前2批、运行时4批。各逐条detail不借当前进程身份；历史loaded不变成active。

OS分类bef共40条（22kernel+18operation_verified），DSH工具48、控制19；482分别28、14、7。所有OS源为independent_probe、工具为native_tool、控制为controller。抽样真实事件可读detail，进程域421785620与命中规则域1139067470分别保留。

完整查询前后tasks、managed_tasks、policy_versions、task_credentials、managed_events、managed_jobs、history_jobs计数不变；原生PID870966保持不变。公开回执：[history-audit-live.public.json](evidence/history-policy-audit-20261007/history-audit-live.public.json)。新专项27与独立审查17通过，既有档案组合已回归；前端76通过、构建通过。

## 发布边界

以继承checkpoint deb6431和功能提交9b3a0d4为基础，保留原工作树并行修改。本轮后续修改不涉及普通业务Java、数据库业务迁移或ActPlane源码；checkpoint中的BPF二进制与当前main已一致，不冒充此次重新评审的内核修改。合并保留main已有CI、说明、ActPlane process.c与旧发布/验收材料；冲突按本轮人工审核、真实进程核验与历史语义的新实现处理，不恢复旧自动收紧。用户在本轮明确允许推送WINDOWS并合并MAIN；实际远端回执另记。

工具结果若目标字段为null，仅从同task_id、同call_id的tool_start回执恢复目标，并保存target_evidence_event_id；没有真实回执保持未记录。损坏子项不再返回不同父ID，明确404。完整proposal和公开解释移入已有详情折叠，主权限范围仅显示操作/对象/差异，DSL不重复外露。
