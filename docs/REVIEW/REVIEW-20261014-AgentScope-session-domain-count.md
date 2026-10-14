# 会话策略域计数修复评审

日期：2026-10-14。状态：修复、全量回归、真实页面与 18003 发布验收通过。

本次修正遗漏同步的读模型：安全配置有 17 项约束，而域页沿用旧 DSL records 统计为零。正式运行核验未停用。security.domain_view 成为公开和原始域接口的共同投影，区分配置记录数量、执行核验与独立应用能力，避免把零额外配置解释为没有保护。

变更仅涉及 AgentScope 读接口、前端、回归及技术文档；无 Broker/ActPlane、普通业务、策略写入或应用行为修改。workspace/session 仍缺少独立原生执行绑定。平台底线不提供停用能力。未知信息不计为零。

定向后端 25 passed；前端 279 passed；Vite 119 modules 构建通过，保留既有 bundle 体积提示。后端最终全量 1210 passed、11 skipped、5 条既有弃用提示；只读预览和正式页面均验证通过。

发布版本 06c0a8a53fcbb9dfa59a93590a567e5c680fd6f2，运行目录 `/opt/agentscope-session-security-20261014-152316`，API PID 1343653；新资源 `index-sl4onWQ_.css` / `index-KsOntYIV.js` 的 HTTP 200 与 SHA-256 均匹配产物。发布前后完整权威快照一致，Broker 及正式 Agent 运行身份未改变，未提交/批准/应用任何验收策略。公开和原始域接口节点相同，平台 2 项 + Agent 15 项 = 安全配置 17 项。原会话实际浏览器已展示新数量、空范围语义及能力提示；390px 预览页面宽 375px，无横向溢出。

证据：[复现](evidence/session-security-20261014/domain-count-reproduction.json)、[发布](evidence/session-security-20261014/domain-count-deployment.json)及同目录测试日志、session-domains-fixed.jpg。仅本地提交，未推送远端。
