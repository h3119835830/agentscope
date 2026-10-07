# RFC-20260923：ActPlane 本机 eBPF 研究环境

状态：已部署的个人研究环境基线（2026-09-23）

## 目标与范围

为阅读 ActPlane 论文、源码并构建其 Linux CLI/eBPF 组件，在 Windows 11 工作站上建立可复现的 WSL2 开发环境。本 RFC 仅描述本机研究配置，不改变 Hermes 产品架构、服务接口或 ActPlane 上游源码。

## 环境组成与职责

- Windows 11 x64：承载桌面论文和源码目录，并启动 WSL2。
- WSL2 Ubuntu 26.04：提供 Linux 用户空间、Rust/Clang/LLVM 构建工具和 ActPlane CLI。
- WSL2 Linux 6.6.114.1 内核：提供 BTF、BPF syscall 和 BPF LSM。当前启动参数将 `bpf` 加入活动 LSM 列表。
- ActPlane：从策略配置编译规则，由用户态 CLI 加载预编译 CO-RE eBPF 程序；内核侧按规则处理进程、文件和网络相关事件。

## 运行与接口边界

命令入口为 WSL 中的 `actplane`。用户策略由 CLI 解析并传给 eBPF engine；运行时加载内核程序并将匹配结果交回用户态。加载 eBPF 需要 root 或相应能力。需要在操作提交前拒绝行为的策略依赖 BPF LSM 已启用；不同效果仍按项目规则语义处理。

上游 README 要求 Linux 5.10+ 和 `/sys/kernel/btf/vmlinux`；完整运行时要求 6.1+。本机内核版本为 6.6，BTF 文件存在，BPF LSM 已在活动 LSM 列表中。

## 本机位置

- 论文：`C:\Users\happy\Desktop\actplane\ActPlane-2606.25189.pdf`
- 源码：`C:\Users\happy\Desktop\actplane\ActPlane`
- WSL 中源码路径：`/mnt/c/Users/happy/Desktop/actplane/ActPlane`
- CLI：`/home/happy/.cargo/bin/actplane`，并由 `/usr/local/bin/actplane` 提供 sudo 可查找的入口。

## 参考

- [ActPlane 上游仓库](https://github.com/eunomia-bpf/ActPlane)
- [Microsoft WSL 配置文档](https://learn.microsoft.com/windows/wsl/wsl-config)
