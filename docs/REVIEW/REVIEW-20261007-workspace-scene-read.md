# 工作区场景识别集成评审

状态：场景读取、采用、真实 Pi 生成及界面验收通过；后续历史策略/审计入口修订见对应评审。

分工：本会话拥有后台接口、任务来源与采用事务、统一部署及本地提交；“搭建 Agent Scope 演示”会话拥有 TaskHub 场景读取入口、结果与澄清界面、独立前端文档及浏览器验收。读取核心、安全审查分工有独立文件归属，避免覆盖并行改动。

必须核验：只有 README 无目标时澄清；RQ5 task.md 实际读取后生成名称目标；补充目标后 ready；评测器和参考策略不进入模型或执行输入；读取不产生执行任务/策略版本/凭据/工具执行；精确引用与片段回执；跨工作区、重复、hash/清单变化、过期实例代次拒绝；非空约束兼容启动策略；任务档案关联；刷新/切换/晚响应/423px/键盘；全部后端与前端回归。

当前代码决定：强制来源新探测、已读字节复用、原子采用、候选与平台权威区分。源目录不是原子事务快照。既有完整闭环验收属于 9b3a0d4 基线，不能替代本次新识别入口的真实 Pi 验收。

## 已完成验收

全后端455 passed、52 skipped、5 warnings；前端65/65通过，Vite构建通过。日志为/tmp/a/scene-final-backend.log、scene-final-frontend.log、scene-final-build.log；跳过项不计通过。

真实Pi读取RQ5 task.md后识别修复目标，实际读取7次，20份过滤后来源没有评测器；文本统计场景实际读取6次，自动名称与目标。攻击README只有一份可读来源，返回needs_clarification，不执行其嵌入命令。只有说明性README的场景先澄清，补充一句目标后ready。引用仅来自实际返回字节，来源角色保持区分。

三个独立只读作业前后tasks299/managed120/policies120/task_credentials299/deployments18/managed_events19383/managed_jobs669均未增加，原生DSH PID870966未变。文本统计草稿采用后唯一创建745565075d3e41c6，同read再次采用409；错误hash、跨工作区、清单变化、未澄清均被拒绝。后续真实启动Pi候选已validated/compiled，仍停留人工确认前、版本0、无执行会话/绑定；随后关闭，effective=false。这些事实不能作为新内核执行证据，先前DSH v3/v4闭环另有独立证据。

公开回执：[readonly-pi-and-adoption.public.json](evidence/workspace-scene-read-20261007/readonly-pi-and-adoption.public.json)。工作区双向切换、刷新只GET、来源两项无重复、Enter/Space折叠、423px页面无溢出通过，见[独立界面评审](REVIEW-20261007-workspace-scene-entry-ui.md)。最终历史入口修订会单独重新构建和验收，不沿用旧静态hash作为最新发布凭据。
