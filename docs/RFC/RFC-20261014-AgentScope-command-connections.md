# AgentScope 可配置执行连接与原生工作区

状态：隔离验收通过，待 18003 发布。用户要求：连接登记 Agent 的启动命令，点击打开即启动网页或终端；保留 DSH 原生工作区与会话流程。

## 职责与合同

连接保存命令、启动目录、入口类型和本机网页地址。命令解析为 argv，不交给 root shell；普通用户在受控 cgroup / ActPlane 域及文件命名空间内执行。启动前组合已确认系统与 Agent 策略，加载并执行实际文件/网络探针，成功后才开放入口。已运行的打开操作复用进程身份。命令变更使用 policy_hash 与 launch_hash 双重并发校验，仅停止后修改；审批快照冻结 launch_hash，变更后须重新审批。

`instance_launch_configs` 是独立的追加兼容配置表。旧连接没有此记录，仍使用原有启动配置及资源映射，升级不重新绑定资源或改变已有策略。新连接默认只读启动目录；安全配置单独管理可访问项目目录、文件写入授权、系统/Agent 规则及审批。访问目录不是 DSH 原生工作区登记。Windows 桌面项目路径可转换为 WSL `/mnt/c/...`；当前执行宿主仍为 WSL。

## 原生工作区与文件

DSH 通过原生 UI 添加目录、创建和执行会话；AgentScope 插件只投影原生 registry 的准确 workspace ID、目录和 session IDs，包含尚无会话的工作区。API `/api/agent-instances/{id}/workspaces` 与 `/workspaces/{workspace_id}/files?path=...` 绑定准确实例。文件清单在该 Agent 的命名空间、非特权身份内读取，不由 root 控制台绕过 Agent 文件策略。目录遍历锚定 directory FD，逐段 O_NOFOLLOW，拒绝越界、跨实例与符号链接；最多返回 500 项，不提供文件内容读取或编辑。

为了现有 ActPlane 精确路径 ABI，受控文件仍绑定短路径 `/w/N`。新连接额外提供原宿主目录入口的符号映射，用户可以在 DSH 原生目录框输入原路径；原生 canonicalization 可能显示短路径。AgentScope 用真实宿主目录呈现文件夹，原生登记和原始名称保留。

## 终端

`/terminal/{id}` 提供本机浏览器 PTY。`POST /api/agent-instances/{id}/terminal` 使用准确 generation/policy_hash，继承控制 API 身份与 Origin 校验，不允许原生任务凭据访问；输入/缓冲/窗口大小有上限。PTY 属于同一个受控执行域，关闭浏览器不停止 Agent。无原生工具适配的命令在策略变更时冻结整个 cgroup，再撤销旧域、终止所有进程并重新核验新代次，旧终端请求拒绝。

## 能力边界

支持已安装的 Node、Python、原生 DSH web 和独立原生 Hermes 入口；不支持 shell 管道/后台符号，不将命令作为 root 执行。其他 Node/Python 命令有真实进程、子进程文件/网络管控，但没有通用原生工具/工作区/会话适配器，工具规则不得宣称执行。当前安装的 DSH 受控适配为 web；DSH TUI 及 Windows 原生执行暂不支持。工作区/单会话独立策略仍无独立执行绑定，禁止降级到 Agent 全局。

资源映射稳定性：当前 `/w/N` 是排序别名，现有目录的替换/移除或插入排序前部会让持久化原生工作区指向错误文件夹。因此已有连接仅允许在排序末尾追加目录；重排/替换/移除须新建连接，禁止静默重新绑定原生工作区。访问权限可通过目录级 deny 审批收紧，或停止整个 Agent 撤销运行。已有 DSL 配置时先停用并应用相关 DSL，再追加资源。未来须以持久化别名表取代排序 ABI，不能靠改原生工作区或用户提示词掩盖。
