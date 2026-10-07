# BUG：AgentScope 本机运行兼容性与验收闭环

日期：2026-10-02。状态：本机受管启动及动态 Scope 的已复现阻塞已修复并验收。
环境：Ubuntu 26.04 x86_64、WSL2 Linux 6.6.114.1，活动 BPF-LSM、BTF 与 bpffs 均存在。

## 1. HTTP 503：path LSM 对 bpf_d_path 的限制

复现：独立 actplane run 和经批准的 AgentScope launch 均失败；
enforce_path_truncate.load 返回 EINVAL，verifier 报 helper call is not allowed in probe。
预编译对象和原源码重建对象均失败，排除单纯制品过旧。

根因：WSL 6.6 的 helper 允许列表不包含这些 path hook。
依据：[WSL 内核 bpf_trace.c](https://github.com/microsoft/WSL2-Linux-Kernel/blob/linux-msft-wsl-6.6.114.1/kernel/trace/bpf_trace.c)、
[bpf_lsm.c](https://github.com/microsoft/WSL2-Linux-Kernel/blob/linux-msft-wsl-6.6.114.1/kernel/bpf/bpf_lsm.c)。

修复：现代对象以有界 dentry/mount 遍历解析当前进程根目录内的完整路径；
使用 per-CPU 名称缓冲与 bpf_loop 控制 verifier 复杂度，不取消 LSM hook。
permission hook 同样解析完整路径，覆盖收紧前打开的文件描述符。
验收：最终对象加载成功；71 项实际内核检查通过，真实 DSH 正常退出。

## 2. 控制端与内核 PID 不一致，嵌套命名空间绕过策略

复现：WSL systemd 用户空间 PID 与 BPF 初始空间 ID 不一致；
只使用 namespace helper 时，bubblewrap 子空间仍可能未绑定任务域，限制回执已应用但文件内容被写入。

根因：运行域表键和 fork/当前进程身份使用了不同 PID 命名空间；
namespace helper 不能直接给出子空间中的加载器祖先空间 ID。

修复：冻结加载器 PID namespace dev/ino；当前空间走 helper，子空间沿 task PID 层级转换；
fork、退出、保护判定与能力请求统一转换。旧格式或不同空间的 pinned 实例拒绝复用。
未绑定进程不消费受管能力请求。
验收：子 PID namespace、fork、bubblewrap 与 proc fd 别名检查通过；
实际 DSH 收紧后已打开描述符的写入被拒绝。非受管进程检查通过。

## 3. handoff 和 relay 被目录权限阻断

复现：Agent 不能穿越 /var/lib/agentscope，handoff 消费失败，child 返回 78；
Broker umask 使 .runtime-control 父目录为 2700，relay 无法读取 control.json。

修复：私有状态根仅增加 Agent 用户的 --x ACL；
任务使用 agentscope-task，运行控制父目录显式 root:agentscope-task 2750。
不加入私有控制组，不开放数据库/私有语料。一次性凭据仍消费、覆盖并清空。
验收：最终真实任务 exit=0，handoff 文件大小为 0，动态收紧回执实际应用。

## 4. 非零退出被误报 completed

复现：child 返回 78 或信号退出，API 仍标记 completed；修复前针对退出状态的回归测试失败。

修复：仅整数 code=0 且无 signal 才标记 completed；其他退出为 failed。
保存结构化 execution_exit 与审计，撤销凭据，独立记录 watch 清理是否确认。
验收：成功、非零、信号和未知退出四项回归通过；最终真实任务 completed 与 exit=0 一致。

## 5. bubblewrap 初始化与策略分类冲突

复现：命名空间身份和完整路径修复后，bubblewrap 写 uid_map/gid_map/setgroups、
构造 /newroot 挂载支架时被当作工作区数据写入拒绝。

修复：仅 procfs inode 上三个精确映射文件作为内核命名空间初始化元数据处理；
仅 /newroot/ 下且 inode 文件系统为 tmpfs 的临时支架允许构造。
实际 bind-mounted 数据文件与 proc fd 别名仍执行策略，内核原有映射权限校验保留。
验收：真实 bubblewrap 可启动，同时工作区禁止写入和 proc fd 别名拒绝通过。

## 6. Scope 扩权后 output 仍为只读

复现：v2 ActPlane 已批准 output 写入，实际 DSH 报 EROFS。

根因：DSH 文件沙箱只将 session cwd 仓库挂为可写，output 是其兄弟目录，
外层文件沙箱合同与 ActPlane 扩权合同不一致。

修复：session cwd 为单个任务隔离根，包络覆盖 repo/output/runtime；
提示中补充实际仓库和输出目录的事实，命令工作目录仍使用 repo。
具体写权限由 ActPlane 控制，未关闭 DSH 沙箱或增加逐条规则的模型补丁。
验收：真实 mountinfo 显示任务根可写、bash cwd 为 repo；
v2 output 写入 expanded，frontend 的继承限制仍拒绝。

## 7. 内核事件对 API 不可读，原因显示原始 JSON

复现：事件已落盘，但 Agent 所有的 .actplane 2700/events.jsonl 0600 阻断 API 读取；
事件原因位于 rule.reason，API 原投影未解析。

修复：Broker 保留 owner，仅赋 task 组读取权限（目录 2750、文件 0640），
拒绝符号链接并验证目录归属。API 解析嵌套原因，重复导入仅更新 reason 投影，
保留原始事件 JSON 与已有事件身份。
验收：事件回归通过；最终 API 返回两条真实 write/block 事件及可读的批准限制原因。

## 已处理的安装问题与保留边界

bpffs 通过 agentscope-bpffs.service 幂等准备；固定 libbpf 的 const 警告通过构建参数保留。
DSH headless profile 统一 CLI/base/headless/peer 依赖，解决 prepare 私有依赖实例不一致。
隐藏 keepalive 与启动脚本保持 WSL 服务入口可用，API/Broker 使用 systemd。

路径缓冲 256 字节、最多 32 遍历步骤；任务无法表示的常规文件写入拒绝。
file_open 拒绝可能留下零字节 inode，本次验收内容写入被阻止，未声称禁止目录项创建。
ARM64 与 Linux 5.10 尚未实际内核验收。

最终任务 2205861d5b8c4867、v2、domain 1776740297：
exit=0、API completed、backend=allowed、output=expanded、frontend 内容为空，
两条 write/block 事件、handoff 大小 0。详见
[REVIEW](../REVIEW/REVIEW-20261002-AgentScope安装验收.md)及其合成测试证据。
