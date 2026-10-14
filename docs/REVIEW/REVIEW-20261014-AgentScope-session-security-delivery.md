# AgentScope 会话安全面板实现与发布验收

日期：2026-10-14。状态：第一阶段实现、真实隔离、浏览器与 18003 发布验收通过；独立 session 执行和完整模型任务闭环仍开放。

## 实现范围

真实会话页改为会话目录侧栏和当前会话安全面板；当前已接入约束默认完整展示，规则详情保留 DSL 与执行证据。结构化文件、网络、工具和行为约定可通过表单起草所属系统/Agent 层候选，支持停用明确的规则或 DSL 文档。批准与应用仍在统一审批中心分别进行。

新增 security 只读视图和请求来源/幂等元数据，不改 Broker、引擎、普通 Java 业务或其数据库。workspace/session 独立应用暂不支持，界面和服务端均明确拒绝，不扩大为 Agent 级。未接入外部约束不计为保护，行为指导不作强制执行声明。

## 基线与并发发布

工作树 `/home/happy/projects/agentscope-session-security-20261014` 初始基线为 c7ddc59。第一次真实隔离验收完成读取限制与停用的功能检查，但结束时 18003 API 被另一项工作从 policy-lifecycle 发布为 approval-recovery；生产身份不变断言因此失败，原记录保留。

对比显示变化仅在 API PID、start_ticks、运行目录；Broker、三个运行 Agent 的 PID/代次/策略/域/active、系统/DSL 配置及其他控制台监听均未变。按已发布目录逐文件摘要保留审批重新校验功能；前端也保留对应入口和测试。另一工作树的未提交文件不被改写。第二次独立验收使用新批次和端口，不能把首次记录直接改成通过。

## 验收记录

初始基线下后端 1198 passed、11 skipped；前端 276 passed。保留并发发布的新功能后前端 278 passed，生产构建通过（118 modules，仍有现存 bundle 体积提示）。后端全量先后通过 1206、1207 项；浏览器复现不存在文件被误报为控制连接异常，修复为明确路径冲突后定向回归 23 passed。发布前最终全量为 1208 passed、11 skipped、5 条既有弃用提示。

第一次隔离环境为 18188，正式环境完全不试改策略。第二批使用 18189。真实原生会话来自 DSH 登记；读取测试文件的禁止与允许分别由独立 Broker 探针及内核匹配记录判断，不能用只读挂载或普通 PermissionError 代替 ActPlane 证据。

第二批真实隔离验收通过：两个独立 Agent 与 A 内两个原生会话；候选及批准不改变进程；显式应用后 A 读取受阻，内核事件匹配实际 read clause 与当前 domain/generation，B 保持可读；面板 API 停用该 Agent 规则，经新批准和应用后恢复读取，B 的运行身份保持原样。两个 A 会话继承同一 Agent 配置，不宣称会话隔离。生产 API/Broker、Agent 身份及系统/DSL 配置、18000/18004 监听前后相等。

浏览器在真实 18189 验证 5 项约束、继承启动 DSL 详情、网络范围配置、局部作用域禁用、缺失路径可恢复错误。结构化候选提交后刷新仍可见，切换另一会话不串入；完整审批差异可读，验收候选已拒绝，未应用。390px 窄屏页面宽 375px，卡片无页面横向溢出；已恢复桌面视口。安全检查只读取配置，不主动进行危险操作。

公开证据位于源码 `docs/REVIEW/evidence/session-security-20261014/`，仅含摘要、合成测试事件、测试日志与哈希基线；完整运行报告、数据库/UI 备份保留在私有部署目录。独立原生 session 应用和完整模型业务任务闭环尚未实现/验收，本次交付关闭的是第一阶段界面与现有所属层配置入口缺口。

## 18003 发布结果

API 版本为本地提交 `6f8397726f28a74cb1905c1f9774c44654d7b679`，运行目录 `/opt/agentscope-session-security-20261014-145845`，API PID 1277322。发布脚本通过健康检查、逐文件摘要、完整权威快照和静态入口检查。Broker PID 1881389 及三个正式运行 Agent PID 1881572/1881769/1881965、代次、策略摘要、执行域、active 和系统/DSL 配置保持原样，18000/18004 监听不变。

正式窗口复查补齐了窄面板的容器自适应：不足 600px 时按卡片读出归属、执行方式与状态。UI 单独发布本地提交 `b845fb5e222a04119fb4631f63e6d5182a20f9f9`，静态快照 `/opt/agentscope-session-security-ui-20261014-150114`；未再次重启 API。新资源为 `index-COnLgoRx.css` 和 `index-zMCLJcW6.js`，HTTP 200 与内容 SHA-256 均匹配构建产物；保留旧哈希资源以兼容缓存。CSS 补齐后构建及 6 项面板定向验证通过，正式 911px 视口、452px 面板已经实际呈现卡片，页面无横向溢出。

真实入口 `/?view=sessions&sessionInstance=instance-1f4469579e8947f4&sessionId=session-1e38fe17-5015-494b-92f4-a164b650bdf4&sessionTab=policies`。原会话显示 17 项已接入约束、8 条启动规则详情记录，读取检查明确显示局部应用与外部约束边界。生产未提交、批准或应用验收策略。本次两个隔离批次均已停止，报告保留；本地截图在会话工作区 `session-security-live.jpg`。公开发布证据另见 [deployment.json](evidence/session-security-20261014/deployment.json)。所有提交均为本地，未推送远端。

## 会话目录折叠补充验收

用户要求截图中的会话目录可折叠。新增独立收起/展开按钮及本机布局记忆，关闭后保留窄入口；窄屏入口横排。前端 278 项回归与生产构建通过。只读预览验证展开后目录仍能按产品筛选和按精确身份切换会话、键盘 Enter 可操作、刷新记忆，收起后主面板从 783px 增至 945px 且 17 项约束不丢失。390px 视口页面宽 375px，测试视口已恢复。

UI 版本为本地提交 fee18b745ca21bc2b7c1b017c7ab343e257ea960，静态目录 `/opt/agentscope-session-directory-ui-20261014-151344`，资源 `index-D5bsGL8N.css` / `index-CI8zJ7Wo.js` 已按 HTTP 200 和 SHA-256 验证。仅替换 UI，无 API/Broker 重启，权威策略、Agent 运行身份和其他端口保持一致。正式原会话已经验证收起与刷新记忆。公开证据：[directory-collapse-deployment.json](evidence/session-security-20261014/directory-collapse-deployment.json)。

合同：[RFC](../RFC/RFC-20261014-AgentScope-session-security-workbench.md)、[ADR](../ADR/ADR-20261014-AgentScope-session-security-entry.md)、[BUG](../BUG/BUG-20261014-AgentScope-session-security-ui-gap.md)。
