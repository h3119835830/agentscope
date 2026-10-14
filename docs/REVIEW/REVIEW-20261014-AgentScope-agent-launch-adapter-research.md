# REVIEW：多 Agent 启动方式与局部策略边界

- 日期：2026-10-14
- 状态：只读研究完成；架构草案已记录；运行实现未验收、未发布。
- 关联：[RFC](../RFC/RFC-20261014-AgentScope-agent-launch-adapter-research.md)、[ADR](../ADR/ADR-20261014-AgentScope-agent-launch-adapter-research.md)、[BUG](../BUG/BUG-20261014-AgentScope-agent-launch-adapter-research.md)。

## 已确认事实

| 证据 | 结论 |
|---|---|
| 已安装 DSH launcher `--help`，退出 0 | 有 Web/headless/profile 等入口；帮助示例不是所有入口的本机就绪证明 |
| 已安装 dsh-agent-loop createAgent；SDK sessions Map；ACP newSession 和 sessions.set | 同一运行时可管理多个逻辑会话；协议化不自动产生独立 PID |
| Hermes dashboard/serve 参数和 profile routing | `--isolated` 是 profile/server 语义，不是会话隔离保证 |
| Hermes compute host sessions Map + ThreadPoolExecutor；ACP run_in_executor | 多会话可在同一 Python 进程/线程池执行 |
| Hermes 原生 PTY spawn 与 registry | 存在真实子进程入口；尚未验证其与具体数据库会话的一一绑定 |
| AgentScope launch.py | 虽有命令配置，仍固定 Node/Python/Hermes 入口、DSH Web 限制和产品分支；还不是通用多 Agent 适配层 |
| AgentScope prepare_home 与 DSH plugin | 现有受控接入会准备私有 profile、注入插件并覆盖 sandboxPolicy；没有改安装源码，但确实影响原生运行配置 |
| AgentScope policy_targets / executor_shared | 局部应用仍拒绝；当前实例共享边界没有变成真实四层执行 |

详细路径、行锚和 SHA-256 见 [证据 JSON](../REVIEW/evidence/agent-launch-adapter-research-20261014/research-evidence.json)。可读 DSH 源码快照与安装包不完全一致；已对关键共享会话实现读取安装 JS 确认。本轮未用旧快照代替当前安装事实。

## 风险与整改方向

1. **目标与执行域混淆**：维持四层逻辑归属，另建共享执行单元及真实绑定。局部候选缺少边界时拒绝应用，不扩为 Agent。
2. **对 DSH 耦合过深**：把现有 profile 注入、沙箱覆盖、固定安装路径和命令重写纳入 AgentScope 的后续整改计划。不能在研究阶段静默卸载已有保护。
3. **启动命令不等于执行连接**：必须识别程序可能只是附着既有服务、再执行、派生后台 host 或迅速退出；不能把 Popen 的返回 PID直接作为会话 executor。
4. **会话 ID 会轮换**：Hermes ACP 客户端 handle 与内部 DB head 可能因压缩不同。适配器要保存来自原生的可信映射与版本，不能从环境变量推断并发归属。
5. **停止范围过宽**：Hermes 原生 `dashboard --stop` 可停止同产品多个服务，不得用来实现停止某一个连接/会话。按所有权和精确身份停止或使用原生 session cancel。
6. **协议能力被过度解释**：本机包存在尚无握手证明；权限询问不等于所有 I/O 都经过客户端。MCP、子 Agent、主进程内文件 I/O、后台进程必须逐项核查。
7. **跨入口历史兼容未验证**：SDK/ACP 新会话不是原生 Web 既有会话的同义替换；不同入口共享状态目录还涉及并发写入/锁。
8. **文件选择器误判**：18020 的 HOME 和文件视图由现有 AgentScope namespace/资源映射决定。仅显示 tmp 不代表 Linux 不能使用桌面目录；仍需核对宿主机路径、授权范围和原生目录入口。

## 本轮研究验收

- 通过：launcher help 退出码；已安装包/原生源码锚点与 hashes；关键事实与文档一致性；四份文档互链；canonical 镜像一致性；本轮未发布应用代码；未发布工具进程草稿已撤回。
- 停止：asfour14-api / asfour14-broker 隔离服务；18190 和最小工具原型 18195 未监听；隔离 cgroup 无活动进程。
- 线上只读快照：18003 健康页与 API 可读；读取时 18020 未监听，当前 DSH active=false。没有为本研究重启 DSH，也不能把已有 gate=open 当成当前运行核验。
- 未进行：新的模型任务、协议 handshake、原生并发会话、四层策略加载和 OS 拦截测试。以上均列为下一阶段，不能宣称完成。

本轮未发布草稿仅做过最小原生工具组合启动与隔离父实例启动，不构成工作区或单会话强制执行验收。草稿在 Git 外私有保留，不包含在本轮提交中。

## 进入实现前的最小研究实验

对 DSH Web、DSH headless/SDK/ACP、Hermes dashboard/serve/CLI/ACP 和通用命令入口分别形成启动进程树与会话绑定图。用户保持原生工作区/会话创建流程；实验环境另建合成数据。检查双会话同时运行、取消其中一个、服务是否共享、重连/恢复、子进程继承与旧句柄撤销。结果决定能否无修改接入局部边界，不能先给能力开关置为 true。
