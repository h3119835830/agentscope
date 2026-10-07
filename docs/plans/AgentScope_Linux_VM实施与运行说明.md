# AgentScope Linux 虚拟机实施与运行说明

> 历史技术规划归档（2026-10-07）：本文保留当时设计、预期接口和目标环境，不能作为已实现或已验收证明。现行实现与未完成事项以 [文档入口](../README.md) 中对应 RFC、REVIEW、BUG 为准。


更新日期：2026-10-02<br>
实施目标：在 Linux 虚拟机中运行 AgentScope、DSH 与 ActPlane；通过宿主机浏览器管理策略。

## 1. 结论与范围

ActPlane 适合作为 AgentScope 的策略执行后端：它负责将已审核策略编译为受支持的内核规则、创建受管进程域、接收运行时限制 Delta，并产生可追溯的命中事件。但 ActPlane 本身不负责 GitHub 语料、任务上下文理解、历史策略筛选、人工审批、策略版本界面或跨任务治理，因此不能单独充当完整管控系统。

AgentScope 控制面与 DSH/ActPlane 均部署在 Lima `ebpf` 虚拟机中。这样 eBPF 程序由目标 Linux 内核加载；macOS 宿主机只访问转发出来的 Web 管理界面。代码位于共享目录，数据库、依赖、缓存与任务工作区放在 VM 磁盘。

## 2. 运行拓扑

```text
macOS 宿主机浏览器
  http://127.0.0.1:8765
          │ SSH 本地端口转发
          ▼
Lima ebpf：Ubuntu 24.04 ARM64 / Linux 6.8 / BTF / BPF-LSM
  AgentScope Web/API :127.0.0.1:8000  ── SQLite
          │ 受 Unix socket 与操作白名单约束
          ▼
  root ActPlane Broker ── ActPlane watch / control / Delta
          │ 受管 child domain
          ▼
  DSH headless ── 任务 GitHub 工作区
```

| 位置 | 用途 |
|---|---|
| `/Users/hezhipeng/Documents/Codex/agentscope` | AgentScope 唯一代码目录；宿主机与 VM 共享 |
| `/var/lib/agentscope/agentscope.sqlite3` | 策略、任务、证据、版本、事件、审批与审计数据库 |
| `/var/lib/agentscope/tasks/<task-id>/repo` | 固定 GitHub commit 的隔离工作区 |
| `/var/lib/agentscope/tasks/<task-id>/output` | 需显式批准后才能写入的任务输出目录 |
| `/var/lib/agentscope/tasks/<task-id>/.runtime-control` | 每个运行策略版本的 ActPlane watch 与事件状态 |
| `/var/lib/agentscope/import/actplane数据集/RQ1` | 导入用 RQ1 manifest 与候选语料 |
| `/var/lib/agentscope/source-snapshots` | 语料来源快照缓存 |
| `/var/lib/agentscope/ui-runtime` | VM 内前端依赖和构建产物 |
| `/var/lib/agentscope-protected/policies` | Broker 管理的策略版本文件 |
| `/run/agentscope/broker.sock` | AgentScope 服务到特权 Broker 的本地 socket |

## 3. 模块与职责

| 模块 | 实现职责 | 关键边界 |
|---|---|---|
| AgentScope API | 任务、证据、策略版本、审核、事件和治理候选的接口 | 普通用户权限运行；不直接加载 eBPF、不执行任意 shell |
| 历史语料服务 | 导入、去重、GitHub 固定 commit 行号匹配、分类、检索、推荐 | 分类是启发式候选；所有导入记录默认待人工审核 |
| GitHub 任务准备器 | 公开仓库浅克隆、解析并固定 commit、采集项目材料与行号 | 当前接受公开 GitHub URL；私有仓库认证尚未接入 |
| PolicyIR / PolicyBundle | 分开呈现历史策略来源、任务证据、适用边界和冲突状态；保存 DSL、Policy YAML、编译状态与版本 | 自然语言策略元数据不写入真实 DSL；未实现的语义映射标为 Agent 参考或待人工审核 |
| ActPlane Provider / Broker | 编译、watch、launch-child、限制 Delta、停止任务 | Broker 只接受白名单操作；当前 Demo 同时只运行一个 ActPlane 任务域 |
| DSH Adapter / Runner | 以 headless profile 在 ActPlane child domain 中启动 DSH；转发已批准的运行时限制请求 | 当前只开放 DSH headless profile；凭证仅保存在 VM 私有目录 |
| Web 界面 | 历史策略库、任务启动审核、运行时 Scope 与事件、持久治理候选 | 展示来源、差异、状态、审批与版本记录 |
| 持久治理 | 登记 memory.md 差异、规则维护 PR 或人工候选，批准后进入历史策略库 | 当前由界面登记候选；尚未实现自动监听 memory.md 或轮询 GitHub PR |

## 4. 三层策略流程

### 4.1 历史策略层

1. 从已有 RQ1 语料读取 `manifest.jsonl` 与 `candidate_rules.tsv`，根据仓库文件快照把语句回链到仓库、固定 commit、路径和行号。
2. 将原始语句、类别、类别置信度、上下文范围、执行层级、来源 URL、源文件 hash、语句 hash 和解析备注存入 SQLite。上述字段是 AgentScope 元数据，不属于 ActPlane DSL。
3. 用关键词重叠对当前任务描述及项目证据进行候选排序；列表同时显示适用上下文与来源。没有可靠匹配的条目保留“未核验”，不推断来源。
4. 用户审核后，只有 `approved` 条目可被任务策略选择。当前已导入 733 条记录，全部保持待审核；它们不会自动成为有效规则。

### 4.2 任务启动前

1. 用户输入 GitHub 仓库 URL、分支或 tag、任务提示词。系统只克隆公开 GitHub 仓库，并把所解析的 commit SHA 固定为本任务版本。
2. 系统采集 README、AGENTS.md、CLAUDE.md、SECURITY.md、CONTRIBUTING.md 及 `.github` 下的 YAML 工作流，登记来源 commit、路径、行号、内容 hash 和摘录。
3. 系统将任务提示词与项目证据用于历史策略候选排序。用户可查看证据来源、选择已经审核的历史策略；未审核条目不可勾选。
4. AgentScope 生成 PolicyIR：任务仓库和固定 commit、目标仓库证据引用、已选历史策略及其适用范围、基础访问控制配置、后端编译支持状态，以及“自然语言冲突需人工判断”的状态。
5. 已审核的历史策略会作为独立参考段加入 DSH 任务提示词，帮助 Agent 遵守历史行为约束；它们会明确标为 Agent 侧参考，不具有内核强制效力，也不能扩大 DSL 权限。
6. 独立生成最小权限 DSL 与 PolicyBundle。编译状态区分完整支持、部分支持、失败；只有 ActPlane 完整支持并经用户批准的版本才能受管启动 DSH。
7. Broker 负责在任务隔离目录中建立 watch，编译/加载已批准 DSL，再通过 ActPlane child domain 启动 DSH。AgentScope 记录策略版本、策略来源 ID、任务证据 ID 和进程域 ID。

### 4.3 任务运行时与跨任务持久治理

1. 运行时页面订阅/读取 ActPlane 事件日志，将进程、操作、目标路径、命中规则和原因与任务、commit、策略版本关联。
2. 追加限制先写入审批队列；批准后，AgentScope 生成仅含 `block` / `kill` 的 Delta，Broker 校验目标进程域和请求 ID，Runner 通过 ActPlane control API 注入当前 child domain。
3. 权限扩大不使用运行时 Delta。当前受支持的扩权演示是开放独立 `output` 目录：审核后停止旧 DSH，在相同工作区编译并启动新策略版本；同时把此前已审核的运行时限制重新编入新 DSL，避免重启造成限制丢失，并记录新域和新版本。失败时将新版本标记失败并恢复旧版本号；若旧进程已停止，则任务标为停止。
4. 任务中的 memory.md 差异、Agent 指令维护 PR 或人工规则只能登记为待审核候选。审核通过后转成新的历史策略记录，后续任务才可检索；驳回或待审候选不参加任务策略生成。

## 5. DSL 与元数据的边界

实际送给 ActPlane 的 DSL 只表达内核可执行规则。例如：

```text
source AGENT = exec "**"

rule task-workspace-write-boundary:
  block write file "/**" if AGENT unless target "/var/lib/agentscope/tasks/<task-id>/**"
  block unlink file "/**" if AGENT unless target "/var/lib/agentscope/tasks/<task-id>/**"
  because "Writes are limited to this task’s isolated workspace, runtime state, and temporary area."

rule deny-remote-publish:
  kill exec "git" "push" if AGENT
  because "Remote publishing requires a separate user-controlled workflow."
```

策略来源、历史记录 ID、GitHub commit、文件行号、上下文、审批人、置信度和 PolicyIR 保存在 AgentScope 数据库及 PolicyBundle 元数据中，不拼进上面的真实策略语法。历史自然语言不会未经结构化确认就伪装成内核规则。

## 6. 当前实施状态

| 验收项 | 结果 |
|---|---|
| Linux 内核、BTF、BPF-LSM | 已确认：Ubuntu 24.04 ARM64，内核 `6.8.0-134-generic`，BTF 与 BPF-LSM 可用 |
| ActPlane 与 DSH | VM 中 CLI 均可调用；DSH headless profile 已启动 |
| 历史策略入库 | 已导入 733 条，默认待人工审核；固定 commit 行号能匹配的条目可直接回链 |
| GitHub 任务准备 | 已完成一次公开仓库固定 commit 与项目材料采集 |
| 启动策略 | 基础最小权限 DSL 完整编译并经审核后加载 |
| 运行时追加限制 | ActPlane Delta 返回成功；随后仓库根目录的越界 write 操作在内核事件中记录为 block，并显示命中原因 |
| 权限扩大 | 受控输出目录的重启路径已实现，既有运行时限制已编入新 DSL；ActPlane 编译检查完整通过，DSH 重启场景仍需单独验收 |
| memory.md / 治理 PR | 候选审核与批准后提升为历史记录的模块已实现；自动发现或 GitHub webhook 尚未实现 |
| 管理界面 | API 与前端运行于 VM；宿主机可通过本地转发访问 |

当前验收任务已经停止，测试用文件已清理；没有遗留运行中的 Agent。桌面 UI 地址为 `http://127.0.0.1:8765/`。

## 7. 操作方式

在宿主机终端启动 VM（若已运行则不必重复）：

```bash
limactl start ebpf
limactl shell ebpf -- sudo systemctl status agentscope-app agentscope-broker
```

桌面浏览器访问：

```text
http://127.0.0.1:8765/
```

如果本地转发端口没有响应，在宿主机终端前台运行以下命令并保持终端打开：

```bash
ssh -F ~/.lima/ebpf/ssh.config -N -L 8765:127.0.0.1:8000 lima-ebpf
```

无任务运行时重启服务：

```bash
limactl shell ebpf -- sudo systemctl restart agentscope-app
limactl shell ebpf -- sudo systemctl restart agentscope-broker
```

结束工作时先在界面停止运行中的任务，再关闭虚拟机：

```bash
limactl stop ebpf
```

AgentScope 代码和构建产物分开：代码在共享目录；Node/Python 依赖、SQLite 和任务状态留在 VM 磁盘。Broker 当前在内存中保存活动进程句柄，因此运行任务时不要重启 Broker；后续应加入 Broker 状态持久化、服务重启恢复和失联任务清理。

## 8. 已知边界与下一步

- RQ1 的分类、上下文和检索目前采用关键词启发式；仍需对不同类别、来源行号和适用场景抽样复核，不能把自动标签当作事实。
- GitHub 证据采集目前限于指定文档与 YAML 工作流，未系统解析 package/构建配置、测试脚本、Agent 工具 allowlist 和所有 Hook 配置；可在下一步增加证据采集器和字段。
- 历史自然语言策略目前以来源可追溯的 DSH 行为参考参与任务；尚未自动转换成细粒度 OS 规则。PolicyIR 会明确标记此边界。语义策略冲突当前要求人工判断，没有自动调和。
- ActPlane 在此 ARM64 Lima 环境使用适配构建；部分旧 syscall tracepoint 被跳过，并对写规则及 rename-exit verifier 做了兼容处理。部署到其他架构或生产内核前，应重新核对 ActPlane 原生支持能力。
- Demo 当前一次只运行一个 ActPlane 任务域、只开放 DSH headless profile、只克隆公开 GitHub 仓库。应先完成扩权重启验收，再扩展多任务、更多 Agent Adapter、完整项目配置采集和 Broker 重启恢复。
- Web 界面面向单机研究演示。多用户身份、细粒度角色权限、并发审批和生产级审计保留策略尚未建设。
