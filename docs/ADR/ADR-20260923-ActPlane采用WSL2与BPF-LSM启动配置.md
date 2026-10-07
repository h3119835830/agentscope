# ADR-20260923：ActPlane 采用 WSL2 与 BPF LSM 启动配置

## 决策

在本机以 WSL2 Ubuntu 26.04 作为 ActPlane 的 Linux 构建和运行环境。通过用户级全局 `%USERPROFILE%\.wslconfig` 设置：

```ini
[wsl2]
kernelCommandLine=lsm=landlock,yama,safesetid,selinux,bpf
```

该列表保留本机原有的活动 LSM，并追加 `bpf`。在 Ubuntu 的 `/etc/wsl.conf` 中保留 `systemd=true`、默认用户 `happy`，并增加启动命令挂载 `securityfs`：

```ini
[boot]
command=mount -t securityfs securityfs /sys/kernel/security
systemd=true
```

CLI 由该 WSL 用户通过 rustup 安装 Rust stable，并从桌面源码构建、安装。

## 原因

ActPlane 是 Linux 内核 eBPF 项目；Windows 用户空间不能代替 Linux 内核提供其运行接口。本机已有 WSL2 Linux 6.6 内核和 BTF。检查发现 WSL 内核虽编译了 `CONFIG_BPF_LSM=y`，默认活动 LSM 列表未包含 `bpf`，因此需要显式启用后才能满足 BPF LSM 策略所需条件。

## 取舍与回退

`.wslconfig` 对本机所有 WSL2 发行版生效，修改后需要重启 WSL。启动参数明确列出当前活动 LSM，因此未来更换 WSL 内核后需要重新核对活动列表。回退时删除 `.wslconfig` 中新增的 `kernelCommandLine` 项，并从 Ubuntu `/etc/wsl.conf` 移除 securityfs 启动命令，再重启对应 WSL 实例。

不采用仅有 Windows 原生工具链的方式，因为它不能提供 ActPlane 所需的 Linux 内核环境。本决策不承诺 WSL 与原生 Linux 在所有 eBPF 驱动、权限和性能行为上完全等价。
