# REVIEW：AgentScope Demo 删除登录验收

日期：2026-10-07。结论：入口专项验收通过，已部署 18003。

## 自动化与在线检查

- 后端：TMPDIR=/tmp/a /opt/agentscope/.venv/bin/python -m pytest backend/tests -q；309 passed、3 skipped、5 项现有弃用警告。
- 前端：Vite 构建成功，37 模块；三个更新后的 UI 验收脚本语法检查通过。本次未重新运行旧 S0-S4 执行驱动，不将语法检查表述成完整运行验收。
- 23 项在线检查：7 个控制 GET 无 Authorization/Cookie 成功且不发 Set-Cookie；确认 POST 无凭据进入 422 业务参数校验；旧浏览器四个路由已移除；DSH/Pi 无任务凭据返回 401；带任务 Bearer 调控制接口返回 401；跨 Origin/端口被拒；API 运行环境不存在管理员凭据。
- 隔离测试验证无管理员配置、无浏览器会话时创建/Scope 审核/受管扩权确认均能到达处理函数，并验证真实 Scope 变更审核仍可生效；任务凭据跨任务请求仍拒绝。
- 真实浏览器原普通地址刷新后直接显示任务工作台，可切换运行时策略，无登录页、口令框和锁定按钮。

## 状态与边界

Broker 未重启。原任务 phase/gate/revision/version/session_id/policy_hash/baseline_hash 不变。原任务仍为 failed/failed、策略 v7，因 Native DSH process/domain binding lost 暂停；本次入口修改没有恢复任务，也没有重新证明 DSH 在线执行或内核新加载。

本机免口令模式信任本机进程，不将 Origin 检查表述为本机进程身份鉴别。未修改普通 ERP 业务。工作区有其他并行未提交变更，本次不打包为混合提交、不推送。

证据：evidence/demo-no-login-20261007/api-acceptance.json 与 browser-direct-entry.jpg。