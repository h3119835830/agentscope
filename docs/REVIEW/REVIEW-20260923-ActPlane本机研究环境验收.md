# REVIEW-20260923：ActPlane 本机研究环境验收

## 范围

完成 Windows 11 + WSL2 Ubuntu 26.04 的 ActPlane 用户态构建工具和内核前置条件配置。没有修改 ActPlane 源码，也没有运行测试套件或真实策略拦截场景。

## 环境事实

- WSL2 内核：`6.6.114.1-microsoft-standard-WSL2`，x86_64。
- BTF：`/sys/kernel/btf/vmlinux` 存在。
- 活动 LSM：`capability,landlock,yama,safesetid,selinux,bpf`。
- 工具：Rust/Cargo 1.98.1、Clang/LLVM 21.1.8、libelf、zlib、bpftool 7.7.0、bpftrace 0.25.0。
- ActPlane CLI：从桌面克隆的仓库以 `cargo build --release -p actplane` 成功构建，并通过 `cargo install --path crates/actplane-cli --locked` 安装为 `actplane 0.1.8`。
- 安装后重启 Ubuntu，securityfs 自动挂载，活动 LSM 列表仍包含 `bpf`。

## 验收结果

以 root 在源码目录运行 `actplane doctor`，结果为 `setup looks usable`；PATH、策略配置、BTF、root/eBPF 能力和活动 BPF LSM 检查均通过。源码仓库 `git status` 干净。

## 风险与未覆盖项

- `.wslconfig` 的内核参数适用于所有 WSL2 发行版；更换内核后需重新核对活动 LSM 列表。
- 普通用户加载 eBPF 仍需通过 sudo 获得权限；不要把 root doctor 的能力结果误读为普通用户无需提权。
- 本次验收只完成构建和 doctor 诊断，没有加载 ActPlane 程序、运行策略或验证阻止效果。需要时应在明确的安全演练策略和目标命令下单独验收。
