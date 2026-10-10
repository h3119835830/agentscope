# Scope Demo 服务托管与恢复

日期：2026-10-07。范围：本机 WSL 内已准备的独立 18003 Scope Demo。

## 运行合同

原 scripts/scope_service.py 准备实例并派生后台进程，未配置随 WSL 启动恢复。新增 scripts/scope_systemd_exec.py 和 scripts/systemd/agentscope-scope-demo-{api,broker}.service，分别托管原 API 与 Broker，沿用原环境函数、数据库、UI、DSH profile、端口及接口。

适配器只接受 /var/lib/agentscope-scope-demo 与 18003。API 执行前降权为原 agentscope-api 用户；Broker 保持原身份与调用者校验。就绪检查等待 API health，并以原 API 服务身份读取 Broker health。PID 回执使用文件锁及原子替换。凭据不写入 unit、文档或浏览器 URL。

API 配置 on-failure 自动恢复，Broker 配置 Restart=no。API 与 Broker 绑定生命周期，服务恢复不表示接管旧 DSH 任务。Broker 维护前须经现有控制接口结束受管任务并核验 active 为空。

## 本机入口

scripts/Open-ScopeDemo.cmd 及桌面文档目录的 打开ScopeDemo.cmd 先启动本实例 API unit，再沿用原本机一次性票据流程。日常启动使用 systemctl start agentscope-scope-demo-api.service；API 单独维护可使用 systemctl restart agentscope-scope-demo-api.service。安装托管后不再用原实例准备脚本直接替换正在运行的进程。

两个 unit 已 enabled，在 WSL multi-user.target 启动时启动。此配置不保证 Windows 登录时 WSL 已启动，也不阻止系统停机；桌面入口调用 WSL，可触发其正常启动。完整 WSL 重启尚未验收。

## 证据边界

本次恢复页面、API 与服务生命周期。旧任务 eada0606a5014c9d 仍 completed、effective=false，仅为历史记录。服务健康、本机登录及 API 自动恢复均不代表 DSH 当前在线，也不替代此前未完成的内核机制验收。

## 2026-10-10：WSL 驻留与当前 Agent 恢复边界

systemd 的 enabled 配置仅在 WSL 启动后托管服务，不能保持 WSL 实例存活，见 [Microsoft WSL systemd 文档](https://learn.microsoft.com/en-us/windows/wsl/systemd)。本机此前仅有工具管理的临时前台驻留会话，桌面入口也只执行 systemctl start；两者都不保证后续长期可达。

本轮恢复采用独立隐藏的 Windows wsl.exe 进程执行 /bin/sleep infinity，不依赖诊断终端。尚未安装 Windows 登录启动项或计划任务；注销、主动终止驻留进程或关闭 WSL 后仍须重新启动。API/Broker 托管、Agent 启动与策略授权合同保持原定义：通过现有实例 start 接口恢复当前 DSH，并重新验证 generation、PID、安全域及启动核验，不能把持久化 gate/runtime 字段当作当前在线证据。

当前 API/Broker 执行脚本来自 /opt/agentscope-task-archive-20261007/scripts/scope_systemd_exec.py，UI 来自 /var/lib/agentscope-scope-demo/ui。本轮具体证据及限制见 [连接恢复验收](../REVIEW/REVIEW-20261010-18003与DSH连接恢复.md)。
