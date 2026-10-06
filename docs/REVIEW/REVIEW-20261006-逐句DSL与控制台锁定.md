# REVIEW：逐句 DSL 与浏览会话复验

日期：2026-10-06。结论：本次记录及会话展示专项通过。

| 检查 | 结果 |
|---|---|
| 后端 backend/tests 全量 | 261 通过，5 条既有弃用警告 |
| 最终前端构建 | Vite 通过，index-ClERrAiG.js |
| 单文件规则映射 | 同一原规则包含两个目标，只输出当前目标子句；无其他底线 |
| 逐句隔离 | 两个识别语句分成两条记录，上下文证据各自过滤 |
| 语义指导 | 无 DSL、无 OS 加载回执、无其他语句的权限增量 |
| 分页 | 同作业 20 条语句按 12/8 分页，无丢失、重复，详情正确 |
| 无识别语句 | 普通评估不进入策略列表，也不导出整包 DSL |
| 本地会话 | 显式锁定拒绝后续访问并记审计；DB 初始化不清会话 |
| 真实浏览器 | 用户现有 tab 恢复；刷新及 API 重启保持登录；锁按钮明确文字 |

## 现场对象

沿用 d5e21e674b464d16 的既有真实 Pi 作业 1761cfbeed424e9eb9ca93dadc060db8，本次没有新增模型对话或 OS 探针，不重记上次计数。文件保护语句与只读指导已分成 statement:0 / statement:1。

前者只显示 runtime-file-protection 中 acceptance.txt 的 write/unlink 两子句，片段 SHA256=1b8ae450762c2121425844436c701a961f132311de4132b198ef912deb0017c8，不含 .bashrc/.gitconfig/project_a、远端发布或整体工作区底线。后者显示“语义指导，无 OS DSL”，已加载该变更=否，没有 OS 权限变化。startup 记录仍按各 atom 对应规则展示。

后台曾成功处理一次 local-browser-close，DB 最晚会话在 2026-10-06 22:25:25（Asia/Shanghai）被撤销，不是八小时过期。可信本机票据恢复当前浏览入口后，未再索取管理员口令。真实 API 进程重启后通过同一 cookie 刷新页面保持登录，未重新签发票据。

同一 DSH Session、策略 v7、启动底线及 acceptance.txt 文件 hash 保持，实际域仍核验。Broker 690080 保持；本次仅更新隔离 18003 API 与 UI。个人 3000/共享 18000 保持，父 checkout 干净。普通 ERP/Java 没有改动。

浏览器验收仅用 CUA。截图及结构化摘要见 [statement-records.json](Pi-DSH-验收证据-20261006/statement-records.json) 与同目录 DSH-逐句DSL、DSH-语义指导无DSL、DSH-逐句记录图片。不导出票据、口令、cookie 或模型私有流。

这次不覆盖此前支付完整任务 8 通过/5 失败，也不增加内核保护通过计数。自动绑定范围、沙箱及 Pi/Broker 权威边界沿用前合同。
