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
