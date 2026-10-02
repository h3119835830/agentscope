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
