# 安全配置按系统与当前 Agent 分层

日期：2026-10-09。范围：18003 Agent连接配置界面。

## 界面与作用范围

安全配置内分为“系统配置 / 所有 Agent 共用”和“当前 Agent 配置 / 所有工作区共用”两个页签，默认打开当前 Agent。删除原有“基础保护（只读）”折叠字段。

系统页展示控制层固定管理的运行隔离、控制面访问、权限变更流程及控制失联处理。该页只读，适用所有受控连接；仅观测的 Agent 尚未接管执行，不能因此声明已应用。固定设置不显示“已核验”，不依赖当前某个 Agent 的 active 状态生成系统生效结论。

当前 Agent 指当前选择的受控连接（instance_id），不是同一产品名称下的全部实例。此连接内的所有工作区、会话及子进程共享策略；具体文件规则仍按目标路径匹配，不能因“所有工作区共用”把某目录授权扩展到其他目录。实例 A 的规则不得显示成实例 B 或系统规则。

## 数据与执行合同

本次仅调整前端呈现，不新增全局策略写入接口、持久化或热加载功能。系统设置是既有控制层固定配置的只读说明，不是一次新的加载或内核验收回执：

| 配置 | 对应代码事实 |
| --- | --- |
| 运行隔离 | backend/broker/instance_runner.py 的 sandbox：namespace、只读挂载、cap-drop 与非特权 UID/GID |
| 控制面访问 | backend/agentscope_app/instances/controller.py 的 agent_auth；backend/broker/instance_runtime.py 的 gateway 限定本实例 Agent API |
| 权限变更 | controller.proposals/apply：restrict 自动应用、expand 确认、旧代次/hash 拒绝、重新核验 |
| 控制失联处理 | instance_runtime.heartbeat 与 instance_runner.main 的 8 秒失联终止逻辑 |

原有 policy、policy_hash、generation、rules、network 和候选确认接口保持不变。规则详情、编辑表单与扩权确认标明当前连接所有工作区范围。默认资源只读、控制面隔离和权限审批继续由原执行层处理，删除界面字段不删除执行保护。

本次不重启 API、Broker 或 DSH，不修改任何执行策略，不将构建或页面测试作为内核拦截证据。

参见 [ADR](../ADR/ADR-20261009-security-config-scopes.md)、[REVIEW](../REVIEW/REVIEW-20261009-security-config-scopes.md)、[BUG](../BUG/BUG-20261009-security-config-scopes.md)。
