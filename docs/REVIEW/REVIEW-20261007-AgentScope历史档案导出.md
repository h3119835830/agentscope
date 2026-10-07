# REVIEW：AgentScope 历史档案导出验收

日期：2026-10-07。目标分支：history-records。

## 来源与范围

快照时间：2026-10-07 22:32:36 +08:00。从 Demo 数据库通过 backup API 取得一致性快照，未停止或改变任务。integrity_check=ok，导出前后私有快照 hash 一致。读取实现及实际 Python 文件 hash 见 provenance。

299 个任务：approved 2、completed 97、failed 54、policy_review 6、prepared 81、running 57、stopped 2。这是保存的任务状态，不证明当前 Agent 在线。

27,145 条公开事件：timeline 17,958、tools 7,226、kernel 1,690、audit 271。每条任务 JSON 包含全部四类事件、阶段、关联、缺失说明和可取得的历史域/DSL，未启动与失败记录保留。

## 验收

- 导出工具 4 项用例通过，覆盖分页完整性、跨任务拒绝、旧 ID/路径安全和私有内容排除。
- 全部分页数量与快照统计一致；task_id 唯一，任务内事件 ID 唯一，跨任务事件为 0。
- 299 份档案为有效 JSON，索引逐文件 hash 和清单核对。
- 服务脱敏后再次排除原始正文、未审查摘录与私有字段；额外遮蔽 17 处凭据赋值形态和 2 处 Bearer 形态。没有发布原始数据库、凭据、原生私有会话或未筛选日志。
- 历史 DSL 仅在可信材料及 hash 核验通过时提供；live=false，缺失材料保持缺失。
- 提交范围仅含公开档案、工具、校验和说明，不改普通业务或并行实现代码。

独立校验再次通过：302 个 JSON 文件 hash 正确，索引 task_id 集合与私有快照完全一致；145 份域详情中 142 份可信材料可用、3 份明确不可用。最大单任务文件为 4,935,775 字节。

机器回执：[validation](../../history-records/2026-10-07/validation.json)、[manifest](../../history-records/2026-10-07/manifest.json)、[provenance](../../history-records/2026-10-07/provenance.json)。

这是公开档案快照，不是运行数据库备份或会话迁移。导出成功不证明当前执行域有效，不重跑模型或内核行为验收。远端回执在推送后同步到本机技术文档，以 ls-remote SHA 与本地 HEAD 一致为准。
