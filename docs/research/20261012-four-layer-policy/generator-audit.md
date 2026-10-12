# 策略生成器与上下文安全机制审计

日期：2026-10-12。本文为源码和论文比较，未调用模型或执行 benchmark。固定源版本、SHA256、符号行号见 [source-lock.json](source-lock.json) 与 [source-evidence.json](source-evidence.json)。

## 1. ActPlane：论文生成链与公开材料不能直接画等号

论文 RQ4 介绍由 Codex 读取任务生成初始策略、运行中提交增量；RQ5 介绍执行前由 Codex 从任务描述生成策略，并排除 evaluator 等评测材料。这个思路适合区分启动约束与运行时建议。[论文 RQ4/RQ5](https://arxiv.org/html/2606.25189v2#S5.SS5)

本次实际核对结果：

| 范围 | 公开证据 | 尚未补齐的来源链 |
|---|---|---|
| RQ1 | 有 translation_prompt、逐条原文、607 项保存编译结果和 study 脚本 | 历史检索与四层治理不是它的实验合同；编译结果不证明语义/安全效果 |
| RQ4 | 21 任务、61 规则、policy_manifest、固定 policy 文件、run_cases 和反馈 hook；保存 110 增量汇总 | runner 从已有 case policy 载入；未在检查入口中取得完整 Codex 生成/110 条逐增量来源、批准和结果链；ledger 无逐任务 reward |
| RQ5 首轮 | 311 条 description-only manifest 对应策略，其中 58 no-op；`infer_rules/extract_paths/render_policy` 按关键词/正则和路径集合生成 | 该脚本无模型 SDK/模型请求入口；不能把它标为 Codex LLM 生成器，不能据“仅 task.md”推导所有策略均由同一模型流程生成 |
| RQ5 final 50 | 50 个最终策略与单独清单，总库存 303 非空 + 58 no-op | 当前 artifact 不保存完整生成/修订记录，无法逐项确认最终策略作者、模型、尝试版本和与论文运行的对应关系 |
| 历史备份 | `cceaee6...` 的 README、脚本目录定向读取；存在同名 description generator 和旧版运行说明 | 未找到检查范围内可闭合上述对应关系的版本化生成入口；旧 README 的 notify-only 说明也不能代表最终策略。原始轨迹未读取、未复制 |

证据汇总在 [generation-provenance.json](generation-provenance.json)：361 个 RQ5 ledger 行均无逐任务 outcome，21 个 RQ4 行均无逐任务 reward。artifact 默认校验只核对清单/汇总，不重新生成或执行。不能据此推断论文结果无效或存在不当行为；能确定的是公开可复现来源链尚不完整。

**可借鉴**：生成前固定任务/仓库材料，分离评测 oracle，以具体 OS 对象和能力生成约束；运行反馈用于新候选。**不直接复制**：关键词推断脚本的场景列表、宽泛路径补全及“匹配到危险词就加入限制”的生成逻辑，这与用户要求的通用语义/上下文修复不同。

## 2. Progent：最值得借鉴的生成与更新编排

固定提交 `5be7b63fa96f70bc19b72fbcee81f1c0bcc1a565`，代码 MIT。论文 v3 用工具名/参数的符号策略、任务初始生成、运行中更新及 SMT 比较组织控制；其窄化自动应用与 AgentScope 全部人工确认的要求不同。[Progent v3](https://arxiv.org/html/2504.11703v3)

实际代码入口：`secagent/tool.py::generate_security_policy` 读取已允许工具 schema 和初始用户任务；`decide_whether_to_update` 判断是否需要更新；`generate_update_security_policy` 加入当前调用、结果和原策略；`check_tool_call` 做确定性工具准入。`policy_analysis.py::security_policy_subset_check` 使用 Z3 对 JSON Schema 约束寻找反例。

需要改造后采用，不能把库函数直接暴露为批准/加载接口：

- 初始生成的 manual_check 默认 False；更新可由调用方传 manual_check；subset 路径受 SECAGENT_ONLY_ALLOW_NARROW 控制且此函数内默认 False。论文保证与实际部署开关必须同时核验，不能只导入包就宣称得到相同保证。
- 比较器仅处理生成优先级 100 的规则，并按每工具首个策略处理参数；不能推导为任意多规则策略等价/包含证明。
- solve_schema 设置超时，异常被捕获；返回接口没有显式区分 unsat、unknown 与不支持。AgentScope 若借鉴，必须使用 proved_narrow/expansion/unknown 三态，超时或无法表示时不能当作“收紧已证明”。本次为静态风险，不冒充已执行的漏洞利用。
- 该比较针对工具参数，不证明 BPF/IFC 中的标签传播、时序 gate、文件别名或跨进程包含关系。需要先定义并验证可比较的规范权限子集，其他情况保持人工审查/阻止提交。
- 上游会将完整调用和结果打印到 stderr；产品只能记录脱敏引用、结构化事实和摘要，不能照搬原始上下文日志。

建议采用其“生成、是否更新判断、候选比较、执行前确定性准入”职责划分。保留 AgentScope 的冻结目标、源动作复核、确定性 lowering、统一审批与 Broker 回执，不采用上游全局可变 security_policy 作为跨 Agent/工作区共享存储。

## 3. FIDES：借鉴材料标签，不当作生成器

固定提交 `669c046c4adbc56ee49c9672fdd30c54937ea062`，代码 MIT。公开仓库主要是 Tutorial.ipynb。只读取代码单元，未读取/导出 notebook 输出中的模型内容。cell 21 定义完整性/保密性格，cell 25 组合标签，cell 29 的 LabeledPlanningLoop 在工具执行前调用策略，cell 33–36 给出非可信内容及 declassification 检查。[FIDES 论文](https://arxiv.org/html/2505.23643v1)

适合把“用户授权、独立 Agent 规范、仓库材料、工具结果”分别标记来源，防止非可信仓库文本成为授权依据。教程中通过邮件域名决定 trusted 是教学选择，不能复制成 AgentScope 的可信认证。标签由服务端已核验来源赋予，模型不得自报 trusted。

FIDES 不是现成的自然语言→ActPlane 四层生成 Agent，也不拦截工具内部隐藏 OS 操作；作为上下文安全机制改造后采用，不替代 Broker/ActPlane。

## 4. CaMeL：借鉴控制流与非可信内容隔离

固定提交 `f083b6b396399d3b3c7f2ddaf613a5945eaf32d8`，代码 Apache-2.0。`privileged_llm.py` 组织可信规划与 quarantined LLM，`security_policy.py::check_policy` 对参数和依赖检查，interpreter 在实际工具执行前调用策略。依赖和值的能力/来源参与授权，而不是把所有工具返回正文放进同一个可信规划上下文。[CaMeL 论文](https://arxiv.org/html/2503.18813v1)

建议将仓库文件理解放在无审批/加载工具的受限阶段，只输出有引用的结构化事实与 unresolved；目标、层级、上层基线、确认内容由可信控制面固定。事实生成仍可能误读，不能因使用双模型就略过源动作复核。

不整体迁移其解释器以改造 DSH/Hermes 内部架构，不把工具参数级能力视为文件、进程、网络的内核边界。仅借鉴隔离方法和确定性授权点。

## 5. PCAS：补充授权解释与因果依赖

锁定论文 2602.16708v2，标题为 Policy Compiler for Secure Agentic Systems；后续版本标题不同，不能混用。其重点是 Datalog 派生规则、依赖图和 reference monitor。文中明确将自然语言自动合成和完整性验证留待后续；案例规则由 LLM 辅助并人工审核。[PCAS v2](https://arxiv.org/html/2602.16708v2)

可借鉴“决策依赖哪些事实/哪些批准”的可追溯解释，但不将其列为成熟自然语言策略生成器或已形式化验证的通用翻译器。在本次检查的论文入口未确认可与该版本绑定的完整官方源码交付，未猜测仓库或许可证，不安排直接代码复用。首版暂不引入第二套 Datalog 执行/审批引擎。

## 6. AgentScope 采用清单

| 机制 | 决定 | 具体落点 |
|---|---|---|
| ActPlane 编译、域、信息流和反馈 | 采用并按本地版本适配 | Broker 执行面；支持矩阵与真实绑定核验 |
| ActPlane RQ1/4/5 场景组织 | 改造后采用 | 冻结源材料、排除 evaluator、形成案例语料；不复刻未闭合生成来源 |
| RQ5 关键词/路径规则生成 | 暂不采用 | 不为特定危险词/文件增加提示词或生成分支 |
| Progent 任务生成/更新职责划分 | 改造后采用，优先 | 统一目标的生成服务；上下文更新后新候选 |
| Progent SMT 比较代码 | 暂不直接采用 | 先规范可支持子集、多规则及 unknown 合同，再独立测试 |
| Progent 自动收紧/直接 apply | 不采用 | 保持统一人工审批 |
| FIDES 来源/完整性/保密性标签 | 改造后采用 | 材料来源与授权事实分离 |
| CaMeL 非可信内容隔离 | 改造后采用 | 受限场景理解→带引用结构化事实；无高权工具 |
| PCAS 因果授权 trace | 作为后续设计参考 | 复用现有证据/审批链，不增加平行权威 |

最终建议不是更换成另一个“更智能”的 Agent，而是把现有 AgentScope 的目标、上下文、安全校验、批准与运行绑定补齐；具体分层合同见 [RFC](../../RFC/RFC-20261012-AgentScope-four-layer-policy.md)。
