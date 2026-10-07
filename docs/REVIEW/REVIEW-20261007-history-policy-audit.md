# REVIEW：历史策略与审计可发现性修订

状态：实现、真实档案接口和最终浏览器验收通过。

范围仅AgentScope任务档案接口、界面和文档，不改权限审批合同或普通业务。三方分工：后台只读聚合、前端档案页签、独立安全与浏览器验收；主会话负责入口、集成和WINDOWS/MAIN发布。

真实基线任务bef449047cd24af6包含v1-v4与22条内核拒绝加18条独立效果核验（OS分类共40条）、48条DSH工具事件；4821ac737a1a4f65包含16条内核拒绝加12条独立效果核验（OS分类共28条）、14条DSH工具事件。OS动作来源为independent_probe，展示独立验收探针；不得为了展示效果改称DSH自行触发。两任务已结束，不因查看历史重新执行。

## 真实接口复核

结构验收版18003发布index-Y_5x-wWv.js / index-D67YD5dc.css，index SHA256 352ef3d0d77388a4d05c8774cdde46b2abbd58aa5d800545ff1ff14e62320fee。API重启前确认Pi生成和managed作业均无queued/running；原生DSH与Broker未重启。

两任务完整读取新策略list/detail：bef运行前2批、运行时12批，含拒绝、过期及无变化；v3/v4真实已批准/加载且完整delta可查。482运行前2批、运行时4批。各逐条detail不借当前进程身份；历史loaded不变成active。

OS分类bef共40条（22kernel+18operation_verified），DSH工具48、控制19；482分别28、14、7。所有OS源为independent_probe、工具为native_tool、控制为controller。抽样真实事件可读detail，进程域421785620与命中规则域1139067470分别保留。

完整查询前后tasks、managed_tasks、policy_versions、task_credentials、managed_events、managed_jobs、history_jobs计数不变；原生PID870966保持不变。公开回执：[history-audit-live.public.json](evidence/history-policy-audit-20261007/history-audit-live.public.json)。新专项27与独立审查17通过，既有档案组合已回归；前端76通过、构建通过。

## 发布边界

以继承checkpoint deb6431和功能提交9b3a0d4为基础，保留原工作树并行修改。本轮后续修改不涉及普通业务Java、数据库业务迁移或ActPlane源码；checkpoint中的BPF二进制与当前main已一致，不冒充此次重新评审的内核修改。合并保留main已有CI、说明、ActPlane process.c与旧发布/验收材料；冲突按本轮人工审核、真实进程核验与历史语义的新实现处理，不恢复旧自动收紧。用户在本轮明确允许推送WINDOWS并合并MAIN；实际远端回执另记。

工具结果若目标字段为null，仅从同task_id、同call_id的tool_start回执恢复目标，并保存target_evidence_event_id；没有真实回执保持未记录。损坏子项不再返回不同父ID，明确404。完整proposal和公开解释移入已有详情折叠，主权限范围仅显示操作/对象/差异，DSL不重复外露。

## 最终验收与合并

完整后端499 passed、52 skipped、5 warnings，13.67秒，日志/tmp/a/history-audit-release-backend.log；跳过不计通过。前端76/76，Vite构建成功，原生实例bridge7/7。独立审查专项17覆盖只读authorizer、拒绝live调用、跨任务/游标、状态/凭据/完整性、子项身份及工具目标同call回执。

最终实屏通过：空工作台显式历史入口、历史默认运行前策略、五页签；生成、人工审核、编译、加载与DSL可分别查看；运行时v3/v4及完整差异；OS40/工具48/控制19，PID/domain/rule/source如实。423×900 body423/scroll423、dialog422/422、tabs422/422，表在内部横向滚动，详情可查；ArrowRight/Home、刷新、浏览器后退均保持对应档案页签。长proposal移入折叠、DSL单份显示。

本地功能提交3b01f1e；整合现有main提交ee0f8f6。合并前逐段检查五个冲突文件，保留新版人工审核、来源校验、真实进程及历史回执语义；合并后backend/frontend/integrations与已测试3b01f1e源码完全一致，ActPlane相对origin/main差异为零。main已有发布文档、CI及验收记录全部保留，原并行工作树未覆盖。远端分支回执会独立保存。

最后仅补主权限差异的中文字段与操作值，DSL及数据不变；前端76/76再次通过。最终JS index-KgXGan-t.js，CSS index-D67YD5dc.css，index SHA256 476106af9ce1b444ddec3fb41717cff1988c7e8ce8ed0bf163908dfecc668a12；对应单页补验见UI回执labels_only_final_asset。此前全套实屏属于相同结构版本，保留真实hash时点，不改造旧截图。
