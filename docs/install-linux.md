# Ubuntu 24.04 ARM64 安装与验收

## 运行环境

在 Linux 虚拟机中运行 AgentScope、DSH 和 ActPlane。目标内核需要提供
`/sys/kernel/btf/vmlinux` 与 BPF-LSM；ActPlane 运行期需要内核加载权限。
不要在 macOS 宿主机上运行 ActPlane 的 eBPF 执行面。

## 从 GitHub 克隆

```bash
git clone --recurse-submodules https://github.com/hezhipeng/agentscope.git
cd agentscope
```

递归克隆会拉取固定提交的 `libbpf` 和 `bpftool`。ActPlane 的
`docs/papers` 资料仓库不属于构建依赖，因此没有纳入此仓库。

## 构建 ActPlane

安装系统依赖及 Rust 工具链后，在仓库根目录执行：

```bash
sudo apt-get update
sudo apt-get install -y build-essential clang llvm libelf-dev zlib1g-dev pkg-config
make -C actplane build
sudo install -m 0755 actplane/target/release/actplane /usr/local/bin/actplane
actplane doctor
```

先确认 `actplane doctor` 报告 BTF、BPF-LSM 和加载权限可用，再继续受控任务验收。

## 配置 AgentScope

复制 `.env.example` 为本机服务环境文件 `/etc/agentscope/agentscope.env`，生成独立的
`AGENTSCOPE_ADMIN_TOKEN`，并按虚拟机里的 ActPlane、DSH、服务账户与 Broker 安装位置调整路径。
将该文件权限设为仅 root 和服务管理员可读。`.env`、SQLite 数据库、历史语料、任务工作区和
运行日志必须保留在 Git 仓库之外。

安装 Python 与前端依赖，并构建静态界面：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
```

将 `deploy/systemd/agentscope-broker.service` 与 `deploy/systemd/agentscope-api.service` 安装到
`/etc/systemd/system/`，并按实际部署路径调整 `WorkingDirectory`、`EnvironmentFile` 和
`ExecStart`。两个服务都读取同一份 root-only 环境文件。API 以普通服务账户运行；ActPlane
Broker 独立以 root 运行，并通过 Unix socket 验证调用方 UID。不要把 AgentScope API 直接暴露到公网。

## 安装两个 DSH bundles

先确保 DSH CLI 在 `PATH` 中，然后从仓库根目录运行：

```bash
./scripts/install-dsh-plugins.sh headless
```

脚本会依次安装 AgentScope 策略 bundle 与 ActPlane 反馈 bundle，随后列出 profile 插件并检查
最终配置是否包含 `agentscope-policy-tools` 和 `actplane-feedback-native`。安装使用本地
checkout 路径，因此保留克隆目录，直到从 GitHub 更新插件为止。需要其他 DSH profile 时把
`headless` 替换成目标 profile 名称。

AgentScope 受管启动的 DSH 进程会自动收到服务 URL、任务 ID 和该任务专用凭据。单独手动启动
的 DSH 没有任务凭据，不能调用 AgentScope 任务工具。

## 验收清单

1. `git submodule status --recursive` 显示 `libbpf` 与 `bpftool` 固定版本；ActPlane 构建和
   `actplane doctor` 成功。
2. AgentScope 状态页报告 DSH CLI、ActPlane CLI、Broker、BTF 与 BPF-LSM 实际状态。
3. DSH profile 列出两个 bundle，`dsh --profile headless --dump-config` 展示两个注册项。
4. 经 AgentScope 启动的 Agent 能读取当前已批准策略，并把 Scope 申请提交到运行时审核队列。
   申请待审或被拒绝时，内核策略不变。
5. 批准一项限制后，ActPlane 事件显示其在运行域生效；批准扩权后，界面显示新版本及受控重启。
6. 对任务工作区执行一项允许操作和一项越界写入：前者完成，后者被内核拦截，事件原因回传 DSH。
7. 不带管理员口令或任务凭据时不能审批；一个任务的任务凭据不能读取或更改另一个任务。

只有看到 ActPlane 事件中的实际内核决策，才能记为“内核已拦截”；插件加载、DSL 编译和策略
配置成功均不单独代表内核执行成功。


## WSL 6.6 与受管任务兼容性

本机 x86_64 验收环境为 Ubuntu 26.04、WSL2 Linux 6.6.114.1，活动 LSM 包含
`bpf`。Linux 6.6 的 path LSM hook 不允许调用 `bpf_d_path`；现代 ActPlane 对象
使用有界的 dentry/mount 遍历解析完整路径，覆盖 bind mount、chroot 与路径权限检查。
任务进程无法完整表示的常规文件写入会拒绝，路径缓冲上限为 256 字节（包含终止符），最多遍历 32 个目录或挂载层级。
已受保护的控制进程在无法解析长日志路径时保留日志写入能力；这项例外不授予任务子域。

控制与内核进程表统一使用加载器 PID 命名空间的 ID。DSH 的 bubblewrap 工具会创建
子 PID 命名空间，必须解析它在加载器祖先命名空间中的 ID，不能因 helper 返回
命名空间不匹配而跳过策略。fork 继承也使用同一套 ID。旧 pinned 引擎缺少命名空间
标识或属于不同命名空间时会拒绝复用；升级 BPF 对象后须先停止使用该引擎的任务，
再清理该实例的 pinned 对象并重新加载，不能在活动任务中更换对象。

API 私有状态目录可以保持 0750。Agent 需要穿越该目录以访问自己任务的一次性凭据，
但不需要列出私有目录或读取数据库。对于默认路径，可由管理员配置最小 ACL：

```bash
sudo apt-get install -y acl
sudo setfacl -m u:agentscope-agent:--x /var/lib/agentscope
```

数据库保持仅 API 可读，私有语料保持控制组权限；任务账户不加入控制组。
Broker 创建运行控制目录时显式设为 root:agentscope-task、2750，避免服务 umask
导致 relay 不能读取本任务的控制状态。一次性任务凭据消费后覆盖并清空文件。

任务执行结果依据 ActPlane child 的退出码：仅 code=0 且无 signal 记为 completed；
非零退出、信号退出或缺失退出码均记为 failed，并审计和撤销任务凭据。
进程退出成功仍不代替具体任务结果的验收。

相关验证（从仓库根目录执行）：

```bash
sudo python3 actplane/test/path_lsm_e2e.py --actplane actplane/target/release/actplane
.venv/bin/python -m pytest backend/tests -q
cd actplane
cargo test -p actplane-ifc-compiler -p actplane-runtime -p ebpf-ifc-engine
```

第一项是实际内核测试，会创建并清理自己的临时目录、bind mount 和独立 bpffs
实例；需在其他 ActPlane runtime 停止时运行。它覆盖普通、chroot 和嵌套 PID
命名空间中的允许与拒绝操作。动态 Scope 还需要通过 AgentScope + DSH 实际验收：
批准收紧后检查新文件与已打开描述符写入被拒绝，批准扩权后检查版本重启、输出写入
和既有限制保留。使用内核事件与文件最终状态判定，不能只看 delta_applied。
本次 x86_64 结果不代表 ARM64 或 Linux 5.10 兼容分支已经在实际内核上验收。


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
