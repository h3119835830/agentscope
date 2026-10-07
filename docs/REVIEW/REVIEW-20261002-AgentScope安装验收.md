# REVIEW：AgentScope 本机受管运行验收

日期：2026-10-02。结论：本机 Ubuntu WSL2 x86_64 的受管 DSH 启动、动态 Scope 收紧与扩权、内核事件回传和退出状态验收通过。原 HTTP 503 阻塞已关闭。

## 范围与环境

读取并延续会话“在 Linux 虚拟机运行 AgentScope”（01a0fc42-d8e4-7703-bdd2-31e9c770081a）。
源码基线为 f606d43513a1397c92b8a33ba99398e2ed9858a7，修复分支
fix/wsl66-managed-runtime，checkout 为 /opt/agentscope。
环境为 Ubuntu 26.04、Linux 6.6.114.1-microsoft-standard-WSL2、x86_64；
活动 LSM 含 bpf，bpffs 已挂载。API/UI 使用 http://127.0.0.1:18000。

修改仅涉及 AgentScope/ActPlane 运行时、AI 专用 Broker/API、测试、部署入口和相关文档。
未改动普通 ERP、Hermes 或 datafoundry 的代码、接口、服务、数据库。
重建的现代及兼容 BPF 对象随源码保留；当前部署使用本次构建的 actplane 二进制。

## 已通过的验收

| 检查 | 实际结果与范围 |
| --- | --- |
| 真实内核文件策略 | 71 项通过，覆盖普通、chroot、子 PID 命名空间和 bubblewrap；包括允许操作、拒绝写入/截断/删除/改名、bind mount、符号链接、proc fd 别名、长路径与 fork 继承 |
| Rust 定向测试 | 99 passed、43 ignored；忽略项不计为通过 |
| 后端测试 | 6 passed：现有任务鉴权、四种退出状态、嵌套事件原因投影与去重 |
| C 谓词测试 | 38 passed、0 failed |
| 非受管进程 | 1 项真实 BPF 测试通过，未绑定进程不匹配全局任务策略 |
| 构建与部署 | Rust release/BPF 重建成功，原生 C loader 构建检查通过，部署到 /opt/agentscope/bin/actplane |
| 实际 DSH | 任务 2205861d5b8c4867 最终 child code=0、signal=null；API 标记 completed，execution_exit.succeeded=true |
| 运行期收紧 | v1 收紧回执 applied=true；backend 写入成功，frontend 新文件和收紧前已打开描述符的后续写入被内核拒绝 |
| 扩权与保留限制 | 批准 v2 并受控重启后 output 写入 expanded；backend 保持 allowed，frontend 内容为空，继承的限制仍生效 |
| 事件回传 | API 返回两条实际 write/block 事件，分别对应 frontend 新文件及已打开描述符；原因来自 rule.reason |
| 凭据与生命周期 | 一次性 handoff 文件消费后大小为 0；退出后撤销任务凭据并清理 watch |
| DSH 文件沙箱 | 实际 bubblewrap 挂载的可写包络为单个任务根目录，执行命令 cwd 为 repo；ActPlane 决定 repo/output 的具体权限 |

事件目录显式为 task 组可读的 2750，events.jsonl 为 0640；API 无事件写权限。
Broker 拒绝符号链接事件目录/文件并校验路径。API 私有状态目录仍为 0750，只给
Agent 用户穿越 ACL，数据库及私有语料没有向任务组开放。

## 可复核证据

[最终任务证据](attachments/agentscope-20261002/scope-final-proof.json)仅包含退出状态、
合成测试文件内容、内核事件、版本与凭据文件大小；
[71 项内核检查](attachments/agentscope-20261002/path-e2e.json)列出实际检查项。

Linux 原始测试与诊断文件位于 /var/log/agentscope/acceptance-20261002：
path-e2e.log、rust-tests.log、backend-tests.log、c-predicate.log、
unmanaged-e2e.log、c-build.log、scope-final-proof.json。
失败复现与修复前证据予以保留，不将历史失败覆盖为通过。
凭据、原始模型输出和模型私有推理不纳入文档或附带证据。

## 验收边界

路径解析缓冲为 256 字节（含终止符），最多 32 个目录/挂载遍历步骤；
无法完整解析的任务常规文件写入拒绝。事件显示 ABI 仍使用原有 127 字节文件名字段，
不能把显示截断误判为策略只匹配 basename。

Linux file_open 拒绝可能发生在 inode 创建之后，因此被拒绝的新文件可能留下零字节 inode。
本次证明内容写入被阻止，不证明“目录项完全不会创建”；后者需独立 create/mknod 合同。

本次实际内核验收仅适用于上述本机 x86_64/WSL 6.6 环境。
ARM64、Linux 5.10 兼容分支、被忽略的其他测试矩阵及生产部署没有据此宣称通过。
doctor 的通用 Codex hook 项仍不代表 DSH bundles 的验收结论。

## 启动与交付

服务为 agentscope-bpffs、agentscope-broker、agentscope-api；
Windows 入口为 C:\Users\happy\Desktop\projects\.start-scripts\agentscope\Start-AgentScope.ps1。
脚本检查 health，使用 -Open 打开浏览器。管理员登录仍遵循应用现有鉴权。
源码本地提交：2b48caecb3f9da44f8a1f83b3de8c42dcb1afd61；源码工作树已干净。
本次仅本地提交，不推送远端。

关联：[RFC](../RFC/RFC-20261002-AgentScope本机Linux部署.md)、
[ADR](../ADR/ADR-20261002-AgentScope隔离安装决策.md)、
[BUG](../BUG/BUG-20261002-AgentScope本机运行兼容性.md)。
