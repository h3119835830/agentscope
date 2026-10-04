# 本地开发入口与页面展示：2026-10-04

按用户明确要求，18000 和 18001 已启用 `AGENTSCOPE_DEV_NO_AUTH=1`，无需填写管理员口令。前端先查询 `/api/auth/mode`，清除旧缓存凭据，显示“本地开发 · 免口令”。连接失败时可重新连接。默认开关为 0，可恢复原认证入口。

新增后端 `development.py` 仅对 loopback peer、Host 及本地或缺省 Origin 的无 Bearer 请求启用模式。显式无效 Bearer 仍拒绝。插件与生成器独立任务凭据、按 hash 批准、编译和受管启动继续保留。此模式允许本机匿名控制 API，不提供正式管理员权限隔离。

两个入口现部署相同前端构建，数据库和静态快照目录分别保留。隔离审计改为核对独立目录与实际响应匹配，不要求构建 hash 不同。新验收保存日期文件，原实验报告保留。

84 项后端测试和前端构建通过；两端口浏览器直接进入；实际展示配置 B 的历史复用、新候选、批准版本与 DSL、独立评测。原库 721 状态摘要未变，原库无 RQ5 任务/context/测试历史，隔离库测试历史 3，两个实例活动任务均 0，Broker 可用。

此前 2026-10-03 六次真实 DSH 与 37 次独立违规探针已完成；本次仅验收入口和页面修改，未重跑模型实验。道歉场景原始评分 A/B unsafe=true，不能表述为语义安全通过。第三层只有批准版本与绑定事件交接。

当前验收：`/var/lib/agentscope-rq5-v1/report/development-acceptance-20261004.json`、`development-isolation-20261004.json`。完整 RFC/ADR/REVIEW/BUG 在 `C:\Users\happy\Desktop\归纳梳理\技术文档` 的同日 AgentScope 文档中；本目录保留对应副本。

截图与报告在 `C:\Users\happy\Desktop\归纳梳理\技术文档\REVIEW\AgentScope-RQ5-v1`。隔离服务已恢复，但未改为 systemd 自动恢复；WSL 重启后需检查实际 HTTP/Broker 可用性。
