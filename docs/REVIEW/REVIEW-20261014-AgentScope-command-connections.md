# REVIEW：命令连接、PTY 与原生工作区

状态：已发布至 18003，连接、原生工作区投影与终端模块验收通过；四层独立隔离仍不完整。

修改仅限 AgentScope 控制台、受控运行适配层及技术文档，不修改 DSH 安装包/原生前端/工作区与会话 API，不修改普通 ERP 业务，不推送远端。

隔离环境：18190，独立 API/Broker、数据库、cgroup、BPF pins 与合成项目。已证明终端进程及子进程真实读取被系统策略阻断，Agent 策略仅影响目标连接，reports 写入正常；停用 Agent deny 后旧域撤销并重建，旧终端代次拒绝，系统 deny 保留。原生 DSH UI 添加工作区、发起日报任务，产物为 3 单/540.00，输入未变化；实际 cat 两个受限文件退出 1，内核事件域/PID 指向对应子进程。

最终代码回归、命令表单与终端浏览器验收、18003 发布身份/资源/审批保全及实际启动复核已完成。工作区、单会话独立策略仍不支持，通用命令的原生工具/会话适配不支持；不将 UI、编译或模型回复当作 OS enforcement。

## 最终隔离验收

后端全量 1,237 项通过；后续启动校验、并发观察与终端授权修改的 75 项定向回归通过。前端 281 项与原生文件边界 2 项通过，Vite 131 模块构建成功。隔离最终代次再次由原生 DSH Bash 实测两个敏感文件读取失败，有非 canary 子进程的当前域内核事件；工作区原生 ID 与文件清单匹配。浏览器真实填写命令、保存连接、点击打开自动启动并输入回显通过，同时 24 次受控读取与 24 次连接检查并发无断开。Node 网页命令、Python PTY、原生 Hermes CLI 均实际启动并核验。全部隔离验收期间 18003 API/Broker 身份、授权状态及其他控制台端口未变化。

证据：[隔离进程与内核](evidence/command-connections-20261014/isolated-acceptance.json)、[终端浏览器并发](evidence/command-connections-20261014/terminal-browser-acceptance.json)。共享域事件不强行归因到独立会话，工作区/会话局部策略仍明确不支持。

## 18003 发布与最终复核

API 源码提交 `76d13a5`，运行目录 `/opt/agentscope-session-security-20261014-180615`；Broker 源码 `4721508`，目录 `/opt/agentscope-command-connections-20261014-175212`；界面紧凑布局来自 `f3908f7`，静态资源与当前源树一致。API PID 1710189、Broker PID 1666990；原 DSH PID 1667542、代次 `6efd182057e64eae8266c181c6fdfd69`，保护核验有效。API 终端地址补丁和静态界面发布均未重启 Broker/DSH。

在真实 18003 使用 Windows 桌面项目路径创建临时命令连接，规范化为 `/mnt/c/Users/happy/Desktop/订单日报与敏感资料隔离`，以普通用户启动 Python PTY。正常订单读取可用，父/子进程未授权写入被拒（实际父进程 EROFS=30）；启动探针单独绕过只读挂载验证 ActPlane，留下当前域内核 write 阻断事件。终端入口规范化为 127.0.0.1 并返回准确 PID/代次。桌面全部原始项目文件指纹不变；临时登记已停止并清理，运行审计保留，原有资源/策略/审批配置哈希一致。系统与 Agent 自定义 read deny、停用恢复及真实 DSH 日报在隔离实例验证，未在发布端修改用户系统策略。

全部引用静态资源 HTTP 200 且字节哈希匹配，18000/18004 未变化，隔离 API/Broker 与截图辅助服务已停止。单元全量 1,237 项、最终相关回归 64 项、终端地址合同回归 39 项、前端 281 项、原生目录边界 2 项通过；131 模块构建通过。宽屏实页连接表单的命令、目录、入口和保存按钮同屏可见，真实工作区/文件及终端回显截图已保留。

[发布事实与桌面运行验收](evidence/command-connections-20261014/deployment.json) · [18003 连接界面](evidence/command-connections-20261014/command-connections-live.jpg) · [真实工作区文件](evidence/command-connections-20261014/command-workspaces-live.jpg) · [真实终端回显](evidence/command-connections-20261014/command-terminal-live.jpg)

仍不支持：工作区/单会话独立应用、DSH 受控 TUI、Windows 原生执行、通用命令的原生工具/工作区/会话适配。通用命令当前网络预设为 DeepSeek。资源映射目前仅稳定末尾追加，替换/移除或重排目录需要新建连接，不能静默重绑定既有原生工作区。此模块通过不等于完整四层链路通过。桌面已新增 `连接与启动说明.html`，在线入口 `/reference/command-connections-manual.html`。
