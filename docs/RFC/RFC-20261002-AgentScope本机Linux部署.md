# RFC：AgentScope 本机 Linux 部署

日期：2026-10-02。范围：AgentScope / ActPlane 受管运行时及本机部署。

源码基线来自 https://github.com/h3119835830/agentscope.git，提交
`f606d43513a1397c92b8a33ba99398e2ed9858a7`；修复位于
`fix/wsl66-managed-runtime`。实际 checkout 是 Ubuntu WSL2 的
`/opt/agentscope`，`/home/happy/projects/agentscope` 为入口链接。

API、静态前端、root Broker、DSH 和 ActPlane 均在客体内运行。实际环境为
Ubuntu 26.04 x86_64、Linux 6.6.114.1-microsoft-standard-WSL2。宿主浏览器通过
http://127.0.0.1:18000 访问；API 只监听客体回环地址。原有宿主 8000 端口保留。

API 使用 agentscope-api 账户，DSH 使用 agentscope-agent 和独立 headless
profile；Broker 经 Unix socket 校验 API UID。管理员凭据和任务凭据分离，任务凭据
仅能访问对应任务；审批由控制端执行。服务环境位于 root-only 的
`/etc/agentscope/agentscope.env`。数据库、语料、任务、受保护策略与日志在 Git
checkout 外。一次性凭据消费后覆盖并清空，完成或失败均撤销凭据。

Linux 6.6 的 path LSM hook 不允许使用 bpf_d_path。现代对象以有界 dentry/mount
遍历生成相对当前进程根目录的完整路径，覆盖 chroot、bind mount 与已打开文件的
permission hook。路径缓冲为 256 字节（包含终止符），最多遍历 32 个目录或挂载层级；任务常规文件写入无法完整解析
时拒绝。受保护控制进程在无法解析其长日志路径时保留控制日志写入能力；任务子域
没有该保护标记。旧内核兼容实现保留，未将本机结果外推到其他内核和架构。

控制端与 BPF 表统一使用加载器 PID 命名空间 ID。相同命名空间使用 namespace
helper；DSH bubblewrap 创建子命名空间时，遍历 task 的 PID 层级解析祖先空间 ID。
fork 继承、退出清理、受保护进程判定和能力请求使用相同身份合同；没有加载器
空间 ID 的外部进程不与受管 PID 混用。pinned 实例保留命名空间标识，拒绝复用
旧格式或其他命名空间的实例。升级对象前须停止对应运行时，再重建该实例的 pins。

API 私有状态根目录保持 0750，只给 Agent 用户单独的穿越 ACL，不授予列目录权限，
不使数据库或私有语料可读。任务控制根目录显式为 root:agentscope-task、2750，
避免 Broker 的 umask 阻断 relay。任务运行目录和一次性凭据使用专用任务组。

执行结果依据 child 的 code/signal：仅 code=0 且无 signal 标记 completed；非零、
信号退出或缺失退出码标记 failed，并写入 task_execution_finished 审计。
API 清理是否确认独立记录。运行期限制追加到当前子域；扩权编译新版本、保留已经
批准的限制、撤销旧凭据并受控重启。加载回执不能代替内核事件和文件最终状态。

初次安装曾因 verifier 返回 HTTP 503；后续修复和实际验收见
[REVIEW](../REVIEW/REVIEW-20261002-AgentScope安装验收.md)、
[BUG](../BUG/BUG-20261002-AgentScope本机运行兼容性.md)、
[ADR](../ADR/ADR-20261002-AgentScope隔离安装决策.md)。


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
