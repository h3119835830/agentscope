# 会话工作区与连接界面简化验收

日期：2026-10-10。结论：已更新正在运行的 18003 控制台，DSH 会话工作区展示及连接历史入口移除通过验收。

## 最终行为

会话表逐行展示 DSH 原生工作区对应的目录标签与完整 resource 路径，保留名称、完整会话 ID、状态与真实执行 PID。Hermes 隐藏项目工作区列；其他提供会话目录的 Agent 可显示。没有目录不猜测，没有 process_ids 不借用实例 PID。工作区仅为展示字段，不会创建目录、激活会话或扩大权限。

Agent连接、旧工作区关联界面和任务详情中的连接历史页签/内容/跳转撤下。旧连接历史 URL 回到当前连接，导航自动清理废弃参数。任务历史、运行记录、后台 append-only 历史存储及只读接口保留。

## 验收结果

|检查|结果|
|---|---|
|前端单元测试|165 passed；包含逐会话目录保持、隔离路径不替代主路径、缺失目录不推断及旧历史 URL 回退|
|生产构建|Vite 成功；83 modules|
|DSH 实际页面|7 条会话；second-dsh 3 条、rq5-dsh 4 条；逐会话 ID/路径与接口一致|
|DSH 进程显示|仅当前空闲会话显示 PID1343；其余已保存会话显示未运行|
|Hermes 实际页面|当前处于执行暂停；4 列，工作区列隐藏；未启动 Hermes|
|旧历史 URL|回到当前连接列表，可发现/添加连接，无连接历史入口|
|默认视口布局|1007px，文档无横向溢出；949px 表格容器 overflow-x:auto，最小表宽 880px|
|发布隔离|只更新 18003 静态资源；旧哈希资源保留；API496、Broker407、DSH1343 均保持|
|策略与执行域|generation、policy_hash、domain_id 前后相同；当前 connected/active=true|

结构化证据：[浏览器](../acceptance/session-workspaces-20261010/browser-checks.json)、[静态部署](../acceptance/session-workspaces-20261010/deployment.json)。截图：[DSH 会话](../acceptance/session-workspaces-20261010/dsh-session-workspaces-desktop.png)、[Hermes 会话](../acceptance/session-workspaces-20261010/hermes-sessions.png)、[当前连接](../acceptance/session-workspaces-20261010/connections-no-history.png)。

## 范围与限制

只修改 AgentScope 前端，不改变后端/原生插件、认证、策略、内核或普通 ERP 业务。不重启受管进程，不修改 18000/18004。布局实测使用浏览器默认视口，未改变视口尺寸；未宣称 423px 等窄屏实际截图通过。Hermes 只验证当前暂停状态的列隐藏，不代表重新验收 Hermes 执行能力。既有启动保护核验仍属于连接恢复验收，不将此次 UI 检查称为新增内核安全实验。

本轮技术文档已同步桌面归纳目录。本地提交后未推送远端。
