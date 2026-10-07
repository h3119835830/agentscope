# RFC：AgentScope Demo 删除登录流程

日期：2026-10-07。范围：本机 18003 Scope Demo。状态：已部署并验收。

## 使用方式与实现

直接打开 http://127.0.0.1:18003/?view=scope-demo 即进入工作台。无需管理员口令、启动票据、浏览器会话或续期。前端删除登录页、认证预检、Token 存储、锁定按钮、自动连接与 401 续接模块；控制请求直接 fetch，credentials 为 omit。

复用既有 development.passwordless：scope-demo profile 设置 AGENTSCOPE_DEV_NO_AUTH=1，去除 Scope 控制接口必须额外提供管理员口令的例外，启动环境不再传入 AGENTSCOPE_ADMIN_TOKEN。启动器直接打开普通地址；managed_control、scope_acceptance 在本机免口令配置下不再附带 Authorization。

删除 local_browser 模块及路由、配置、数据库建表代码、浏览器启动票据脚本和对应会话测试。旧数据库中已存在的历史会话表不再被读写或用于授权，未执行破坏性数据清理。旧自动会话和票据设计已废弃，不存在兼容续接分支。

## 保留的执行合同

本机控制入口依赖 loopback peer、loopback Host；请求带 Origin 时必须与完整服务地址同源，包括协议和端口。控制入口不接受任务 Bearer。DSH/Pi 的 plugin/generator/agent 接口继续自行验证绑定任务的凭据；Scope 候选、确认、版本、编译和 ActPlane 加载合同未变。

此模式信任本机调用者；不声称能够阻止恶意本机程序去掉 Authorization 后调用控制接口。任务凭据检查和内核执行隔离是不同边界。

## 部署与证据

仅部署 18003 私有 UI 并重启 API；Broker PID 未变。原任务 d5e21e674b464d16 的 phase/gate/revision/version/session_id/policy_hash/baseline_hash 与修改前一致。该任务原已因 Native DSH process/domain binding lost 暂停，本次没有恢复或执行任务。

相关代码位于 /opt/agentscope-history-v1；其他实例现有 UI 快照未替换。详见同日 ADR、BUG、REVIEW《AgentScopeDemo删除登录》。