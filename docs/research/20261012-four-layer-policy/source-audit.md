# ActPlane 与 AgentScope 源码审计

审计日期：2026-10-12。方法：固定提交源码、论文 HTML、公开 artifact 清单、历史备份代码入口和本地已保存验收记录的只读比对。未运行模型、DSH 任务或 eBPF 探针。所有公开源文件的 SHA256、行号和符号在 [source-evidence.json](source-evidence.json)，完整版本在 [source-lock.json](source-lock.json)。

## 1. 版本与结论等级

| 对象 | 固定版本 | 用途 |
|---|---|---|
| ActPlane 论文 | 2606.25189v2 | 论文的设计与实验主张 |
| ActPlane master | 404542899a2153af0952cbf0dc52aeab0b7c5034 | 当前公开实现和产品文档 |
| ActPlane artifact-ready | 63db86945c9b8618a46aa68c8de214bc4b8343d9 | 保存的策略、清单和实验汇总 |
| ActPlane 历史备份 | cceaee6be878eeff4b42caf9a069d535699ecf69 | 仅定向检查公开代码/README；不读取原始模型轨迹 |
| AgentScope | fc4e9d5368fecc713830738a7ad5896dcfd00fd8 | 本地已提交实现与历史验收 |
| AgentScope vendored ActPlane 基点 | 4c36aa54da2daf2b64de8782a38f77d5b76ec75a | 来源基点，含本地适配；不等同于 master |

下文“源码存在”只表示检查到代码；“测试存在”只表示存在断言；“静态检查通过”表示本次实际执行清单/文档检查；“历史运行证据”有独立时间和对象。不能将这四类事实合并成当前系统已满足所有安全承诺。

论文描述的关键抽象包括 DSL、跨事件信息流、进程树域、运行时权限增量和反馈，而非单一加载器；产品层级映射与治理 UI 仍需控制面实现。[论文 §3–4](https://arxiv.org/html/2606.25189v2#S3)

## 2. 论文、代码、测试与当前产品对应

下表路径均相对于其锁定仓库，符号和上游固定提交链接由 source-evidence.json 给出。AgentScope fc4e9d5 是本地已提交快照，尚未推送；其证据以本地 Git 路径、commit 和摘要定位，不伪造可公开访问的 GitHub 链接。

| 能力 | 上游源码/测试依据 | AgentScope 当前事实 | 结论 |
|---|---|---|---|
| DSL 与确定性编译 | `crates/actplane-ifc-compiler/src/dsl/lower.rs`；语法/访问组 lowering | `history/intent.py::extract/normalize/lower/validate` 将源动作独立复核后映射；支持原文权限校验 | 有可复用编译和语义工程基础；编译不证明原文语义正确 |
| OS 主体和标签传播 | `bpf/taint_engine.bpf.h`；fork/exec/file/network 状态；E1/E7 夹具 | 真实 DSH 测试已有 PID、域、来源及 OS 效果记录 | 属于执行引擎能力，不等于工具消息级精确数据流或所有网络发送覆盖 |
| 域与 PID 绑定 | `bpf/capability.bpf.h::cap_domain_for_pid/cap_fork`；`bpf/src/lib.rs::child_domain_state` | `backend/broker/instance_runtime.py::start/observe` 每实例建立一个运行域；`executor_shared=True` | 上游有域机制，当前原生会话未独立绑定 |
| 配置继承 | `config.rs::resolve_domain_inner` 递归单 parent；测试 `domain_can_disable_default_but_not_locked` | `instances/dsl_policy.py::documents_for` 仅 system + instance | 四层目标需要新存储/组合；不能把 default 叫不可移除底线 |
| 运行时 authority | `cap_check_fields/cap_append_rule_admit` 检查目标、能力、标签；Rust `admit_delta` | managed 评估/审批/完整域重建是另一条编排；原生助手未接成会话 delta | 不应把上游接受增量与产品人工审批等同 |
| 子域和生命周期 | `runtime.rs::bind_child_domain`；`mcp.rs` 的 launch/restart/terminate/reconcile；BPF root smoke 被 `#[ignore]` 标注 | 当前 DSH 子进程继承实例域；没有原生每会话 worker 生命周期 | 测试代码存在，本次未执行 root smoke；需要专门适配和验收 |
| 范围收窄 | `cap_scope_subset` 和 Rust `scope_subset` 比较整数 scope_id；cap_state 单 parent | `/w/0` 映射和真实进程域分别处理 | 数字关系不证明路径集合包含、workspace 归属或会话隔离 |
| 域深度 | `CAP_DOMAIN_DEPTH` 普通路径 8、legacy 1；`cap_domain_matches_pid` 有界遍历 | 未实现无限层级产品执行合同 | 不能把长期架构的无限配置层级写成无限内核域 |
| 反馈 | `feedback.rs` 与 hooks/MCP 资源；block/kill/notify 区分 | because/Pi Skill、managed 反馈与原生 DSH 执行已有工程基础 | 内核命中、反馈格式化、送达和模型恢复需分开证明 |
| 审计与会话归因 | 根拥有事件文件读取、source_ref/clause_hash、域和加载 receipt | `sessions.py::project_kernel` 无可信 tag 时输出 shared_executor_unattributed | 2026-10-11 的 7 条事件不能补造会话或工具关联 |
| 自保护和权限主体 | 论文可信加载者与不可信执行者分离；上游 control/MCP 含变更接口 | API/统一审批/Broker 是权威；Pi 仅提出候选 | 不照搬高权 MCP auto-attach/变更工具给生成 Agent |
| 工作区/会话产品接口 | 上游 arch_plan 描述愿景、runtime 有通用域能力 | 现有 DSL 写接口只有 system/instance；生成候选固定 scopeType=agent | 不能靠改标签交付工作区或会话隔离 |

source-evidence.json 同时记录这些本地模块的固定提交摘要。审计前的只读现场比对表明 agent_context、dsl_policy、dsl_api、sessions 与 18003 当前发布目录一致；该结论不覆盖前端未提交工作，也不证明实际隔离。

## 3. 为什么上一轮显示全部工作区和会话

`history/agent_context.py::selected_candidate` 返回 scopeType=agent，sessionId 仅作为生成上下文引用。`instances/dsl_api.py` 的 agent_propose 将候选送入实例 scope；`documents_for` 组合系统与实例文档，确认应用重建实例执行器。`sessions.policies` 又把这套实例规则展示在该会话的继承视图中。因而从会话入口进入、在会话中执行探针和在会话页看到规则，都不能把实例策略改成会话局部。

保存的验收提案为 `6ccdbda0250d4cd3acac31a5a96c4d92`，目标为 `instance-cc444fe38c094cbb`。6 项基线、6 项待审批及 11 项批准后操作真实通过，原文只读映射正确；没有建立第二个并发会话/工作区对照。结论应为“Agent 范围规则在真实 DSH 会话中验证了只读效果与审批边界”，而非“会话策略隔离通过”。[原始记录](../../acceptance/20261011-policy-source-semantics-dsh/README.md)

## 4. 配置继承与运行权限须分别解释

ActPlane YAML 的 locked/default 是配置装配合同：后代可以 disable 继承的 default，不能 disable locked。运行时 mask/标签/目标权限检查又是另一层合同。人工审批是 AgentScope 额外引入的治理授权，不由这些机制自动提供。

AgentScope 采纳的安全底线应锁定到后代；本层所有者修改本层约束仍需新的审批版本。不能声称所有规则均永不可删，也不能把一个 default 参考项当已部署的强制底线。作用域证据需要实际资源/身份与执行绑定，scope_id 或 DSL 目录匹配只覆盖其中一部分。

上游代码已有 domain-local declassification、authority 限制及父域相关测试；它不意味着任意可执行名称是可信 gate。核对人的审批、内容清洗正确性和批准适用范围属于控制面/可信工具合同。本次没有对其完整安全性进行形式化证明。

## 5. 实际执行的静态检查

已在干净、固定提交的 artifact 缓存中执行 `python docs/artifact/verify_results.py all`，退出码 0。输出保存在 [upstream-artifact-check.txt](upstream-artifact-check.txt)。它复算 607 条 RQ1 编译记录、RQ2 保存结果、RQ3 汇总、RQ4 的 21 任务/61 规则，以及 RQ5 的 361 任务/303 非空策略/58 no-op 清单。没有重新编译这 607 条规则，没有重跑模型、任务、性能或内核效果。

RQ4 ledger 的 21 条记录均无逐任务 reward；RQ5 ledger 的 361 条记录均标注 aggregate_summary_only 且无逐任务 outcome。110 条 runtime delta 是保存汇总中的主张，本次未取得逐 delta 可复算链。验证清单与算术不能补足缺失的运行或生成来源。

## 6. 分项成熟度判断

| 部分 | 当前可支持的判断 | 尚不能支持的判断 |
|---|---|---|
| 执行引擎 | 有 DSL/compiler、BPF-LSM、IFC、域和反馈实现及测试基础；AgentScope 对特定原生 DSH 文件操作有历史真实证据 | 任意自然语言、无限层级、全 OS 动作、任意共享执行器均可靠隔离 |
| 策略生成 | 有论文实验、RQ1 流程、RQ5 描述型脚本和策略库存；需按来源区分模型、规则及人工修订 | 公开仓库已提供可直接接入的成熟、自主、持续四层生成服务 |
| 治理控制面 | AgentScope 已有统一审批、失效复核、版本/回执与受控重建基础 | 无会话 Agent 生成、workspace/session 全链路与精确内核归因均已完成 |
| 复现材料 | artifact 静态清单可验证；RQ2 有选定保存结果；raw backup 可定向恢复历史代码 | RQ4/RQ5 全量原始运行、生成版本和每条增量来源已完整可复算 |

判断为“具备可复用研究和工程基础，四层治理与完整复现仍需补齐”，不采用单一成熟/不成熟标签。完整生成器差距见 [生成方案审计](generator-audit.md)，可复用范围见 [案例清单](case-catalog.md)。
