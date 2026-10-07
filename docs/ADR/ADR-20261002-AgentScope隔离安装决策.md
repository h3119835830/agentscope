# ADR：AgentScope 隔离安装与运行时兼容决策

日期：2026-10-02。状态：采用；验收结论见 REVIEW。

沿用 Ubuntu WSL2、/opt/agentscope、18000 端口、独立 API/Agent 账户及 headless
profile。原始源码基线为 f606d43513a1397c92b8a33ba99398e2ed9858a7，
本次修复在 fix/wsl66-managed-runtime。普通 ERP 和 datafoundry 代码、服务、数据库
均不属于本次改动范围。没有更换全局 WSL 内核。

DSH 固定为 0.2.0-rc.2，并在同一独立 profile 内统一 CLI/base/headless/peer 依赖，
避免不同依赖实例的私有 Symbol 不一致。CLI 入口为
/opt/agentscope/dsh/node_modules/.bin/dsh。已有 DSH Home 保留。

采纳完整路径解析替代现代 path hook 的 bpf_d_path 调用，保留所有要求的 LSM hook。
采用有界内核 dentry/mount 遍历以及 per-CPU 名称缓冲和 bpf_loop 字节复制，
控制 verifier 复杂度与 512 字节调用栈限制；不退回 basename 匹配绝对目录规则。
路径无法完整表示的任务常规文件写入拒绝，受保护控制进程的长日志写入例外单独
保留。代价是受管任务写入路径受 256 字节缓冲限制，详见 REVIEW。

采纳加载器 PID 命名空间作为表键合同。bpf_get_current_pid_tgid 返回初始命名空间
ID，与 WSL systemd 控制端不同；bpf_get_ns_current_pid_tgid 又只能接受当前活动
命名空间，不能直接代表 bubblewrap 子空间中的祖先 ID。因此当前空间走 helper，
子空间走 task PID 层级；fork 使用 raw tracepoint 的两个 task 指针并按同一空间
转换。以 namespace 标识拒绝不兼容的 pinned 实例。规则 IR 和能力授权不放宽。

采用私有状态目录的用户级仅穿越 ACL，以及显式 task 组和控制根目录权限，
避免让 Agent 加入私有控制组或扩大数据库读取权限。已打开描述符继续在 permission
hook 中按完整路径检查，使运行期收紧覆盖后续写入。

采用结构化退出状态作为会话完成依据。非零/信号/未知退出为 failed，而不是看到
进程消失就 completed；清理状态、退出审计和凭据撤销分别保存。

使用 agentscope-bpffs.service 幂等挂载 bpffs，并以 Windows 隐藏 keepalive 保持 WSL
服务可访问。固定 libbpf 与新 glibc 的 const 警告通过
EXTRA_CFLAGS=-Wno-error=discarded-qualifiers 保留警告完成构建。
ACTPLANE_REBUILD_BPF=1 重建现代与兼容对象；本次制品与源码一并保留，不恢复旧对象
覆盖修复。仅在本机 x86_64/WSL 6.6 验证，不宣称 ARM64 或 Linux 5.10 已验证。

验收必须结合真实 DSH 工具、内核拦截事件、文件最终状态、退出码与凭据清空；
静态构建、doctor、编译成功和 delta_applied 均不单独代替执行验收。


bubblewrap 用户命名空间初始化需要写 procfs 的 uid_map、gid_map 和 setgroups。
这三个精确名称且 inode 属于 procfs 的文件作为命名空间初始化元数据处理，
仍由内核执行所有权和一次性映射校验。不是整个 /proc 的豁免；procfs fd 别名解析到
实际数据文件时继续执行文件写入策略。permission hook 与 file_open 统一采用该分类。
实际 bubblewrap 启动及 /proc/self/fd 别名拒绝均纳入验收。

bubblewrap pivot_root 前在 /newroot/ 下构造临时 tmpfs 根目录。只允许该路径下且 inode
superblock 确认为 tmpfs 的临时挂载支架操作；绑定进来的业务/工作区数据仍使用实际
数据文件系统 inode，继续执行原策略。没有解除任务域、关闭沙箱或放行整个 /newroot。

DSH 的 session cwd 设为本任务隔离根目录，使其文件沙箱挂载 repo、output 和任务运行
状态组成的隔离包络。AgentScope 提供工作仓库与输出目录的事实上下文，命令实际 cwd
仍可为 repo；具体 repo/output 权限由批准的 ActPlane DSL 决定，DSH 沙箱没有被关闭。
这修复了“内核扩权已批准但 output 在 DSH 文件沙箱中仍只读”的合同冲突。

Linux file_open 拒绝发生在创建新 inode 之后时，可能留下零字节文件。本次“阻止写入”
以 EPERM、内核 block 事件及内容未写入为准，不承诺新文件 inode 必定不存在。
禁止创建本身需要单独的 create/mknod 合同，未将该能力作为已验收项。

内核事件的 API 读取合同：Broker 保留事件 owner，设置 .actplane 为 task 组可读的
2750、events.jsonl 为 0640，API 无事件写权限；拒绝符号链接并验证事件路径归属。
这项权限只作用于任务内核事件，不开放私有数据库、语料或凭据。
API 从 rule.reason 提取原因；去重导入仅更新原因投影，保留原始 JSON 和事件身份。
