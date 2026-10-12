# AgentScope 策略界面与确认链路已复现问题

2026-10-12 范围与证据补充见 [新 BUG/GAP](BUG-20261012-AgentScope-policy-scope-and-evidence.md)：现有实例接口不提供工作区/原生会话局部隔离；此前只读语义修复已通过 Agent 范围真实 DSH 验收，不能据此关闭局部范围缺口。本文其余条目按原现场保留，未重新运行的条目不标记已修复。

日期：2026-10-11。状态：开放，文档记录与设计方案已形成；产品代码未修改，修复验收未完成。

关联 [架构 RFC](../RFC/RFC-20261011-AgentScope-policy-control-architecture.md) 与 [评审 REVIEW](../REVIEW/REVIEW-20261011-AgentScope-architecture-audit.md)。所有复现来自真实页面、只读接口或隔离测试；本记录不包含推测性的可利用漏洞。

## BUG-01 模块标题重复

复现：打开总览，侧栏与面包屑已有模块名，内容区再次显示“总览”；Agent连接、任务历史也有同类重复标题，生成记录有重复标题和内层导航。

预期：模块名仅在导航和面包屑出现，内容区以操作、筛选和记录为主。

整改：按 UI skill 收敛对应页面标题。验收须覆盖上述入口与窄屏；状态：未修复。

## BUG-02 系统生成记录嵌套旧生成工作台并暴露内部诊断

复现路径：系统 → 生成记录 → 查看结果 → 来源/伪代码/DSL。外层“生成记录”内出现旧“策略生成、历史策略记录、生成记录”三个页签，并可以“新建生成”“最终审核通过”。详情直接显示适配条件 JSON、PolicyIR、来源/产物哈希。

根因：`SystemWorkbench.jsx` 将 `HistoryLibrary` 的完整旧模块导航挂在生成记录页；旧 `PolicyArtifactPreview` 等详情沿用研究工作台表达。

预期：生成记录提供只读生成历史和可读候选详情；起草统一进入 Agent 助手，执行授权统一进入审批中心。DSL 可按需查看，内部 JSON/IR/运行标识进入技术验收材料。

证据：[重叠工作台截图](../REVIEW/evidence/architecture-review-20261011/generation-legacy-overlap.jpg)、[内部诊断截图](../REVIEW/evidence/architecture-review-20261011/generation-internal-diagnostics.jpg)。验收须覆盖普通导航、旧深链和候选详情；状态：未修复。

## BUG-03 旧实例权限收紧在提交后自动应用

复现：隔离执行现有 `test_agent_instance_policy.py::test_automatic_restriction_is_instance_local_and_has_quiescence`，仅调用 `controller.proposals(..., actor='agent')`，无需调用 confirm 即得到 applied 并修改实例网络权限。源码 open gate 分支会异步调用 apply。

根因：旧合同按 restrict/expand 分类，restrict 自动应用；新 DSL 合同与当前 UI 要求采用人工确认。审批中心只查询 `instance_dsl_proposals`，不能统一展示或确认旧 `instance_proposals`。

影响：当前“只有你确认后才应用”的产品承诺不能覆盖所有写接口；实例收紧可能重建共享执行器并影响全部会话。该问题是用户确认合同冲突，本轮未证明任意提权或跨实例逃逸。

整改：旧权限提交仅保存候选，统一投影到审批中心；暂停执行门与应用授权分开。验收：收紧和扩权提交均不改授权/代次；拒绝不加载；批准按内容和基线复核；失败保持阻断；原有普通业务可用性不受影响。状态：未修复。

## BUG-04 草案状态与审批状态、侧栏角标不一致

复现：侧栏审批角标为 2，审批页待审批为 1、需处理为 1。连接配置 → 安全配置中两个 DSL 草案都标“校验通过·待应用”，其中一条在审批投影已为 stale。

根因：`approval_views.project()` 会实时计算环境/基线漂移；`pending_count()` 只统计数据库 pending；DSL 详情中的原始 proposal 状态没有统一采用该投影。

预期：所有入口对同一候选使用同一可应用性和失效原因。角标明确定义为“待审批”或“待处理”，并按同一投影统计。

证据：[连接草案截图](../REVIEW/evidence/architecture-review-20261011/connection-policy-duplicate-and-stale.jpg)、[现场 API 状态](../REVIEW/evidence/architecture-review-20261011/architecture-evidence.json)。验收：目标/环境变化后，编辑器、草案列表、审批详情和角标一致；不能只依赖 apply 最终拒绝。状态：未修复。

## BUG-05 策略域产品投影缺少共享执行器说明

复现：会话 → 策略域显示“系统策略 → Agent 策略 → 会话策略”三个节点。诊断接口明确返回 executor_shared=true 及“配置继承不代表三个独立内核域”的 notice；`console.session_read(...,'domains')` 没有保留 notice，前端也没有呈现共享执行器说明。

预期：配置关系清楚标注；原生会话共享实例执行器时明确说明，只有可信域绑定才显示实际独立域。

证据：[域图截图](../REVIEW/evidence/architecture-review-20261011/session-domain-configuration-chain.jpg)。验收：共享原生会话和有可信 managed-task 绑定的会话分别展示，不能用相同图形暗示相同隔离等级。状态：未修复。

## BUG-06 策略空态无法解释已核验保护

复现：被查看会话顶部显示“继承的 Agent 保护已核验”，策略详情只显示两个配置按钮，域图三类策略均为 0。客户投影过滤 legacy-generated 记录，而同一会话诊断接口有 8 条既有约束。

预期：用户配置表可以为空，但应说明当前保护来自平台约束，并提供可读的只读摘要。不能把“不展示底层自动生成规则”变成“没有有效策略”的误导。

证据：[会话空态截图](../REVIEW/evidence/architecture-review-20261011/session-policy-empty.jpg)、[客户与诊断计数](../REVIEW/evidence/architecture-review-20261011/architecture-evidence.json)。验收：零用户策略、有用户策略、未运行及绑定失效四种状态均能解释保护来源。状态：未修复。

## 不作为新 BUG 的事项

助手未读项目正文、统一会话策略写链路未完成是功能缺口，列于 REVIEW，不伪造已有功能回归。原诊断接口保留实例/共享事件，而产品投影已正确筛选可信会话归属；两项合成复核确认客户投影没有泄漏其他会话命中，因此不把该诊断差异记成客户界面事件串用。


2026-10-11 第三步进展：场景读取、人工采用、生成候选和统一审批接入已完成源码及隔离验收，未发布 18003；详见 ../RFC/RFC-20261011-AgentScope-agent-scene-step3.md。既有只读需求生成语义扩大另记 GEN-SEMANTICS-001，尚未整改；不宣称完整安全闭环。

## Agent/工作区生成合同差距（2026-10-11 补记）

只读核对 `history/agent_context.py::snapshot/selected_candidate` 与 `instances/dsl_policy.py::documents_for`：无可选定原生会话时 snapshot 返回需选择会话，生成候选固定 scopeType=agent，DSL 组合范围为 system + instance。现有代码不能据此提供无会话 Agent 基线生成或独立工作区策略应用。

用户已采纳以 Agent 和工作区为主要生成目标的 [新架构](../RFC/RFC-20261011-AgentScope-policy-control-architecture.md)。以上属于新合同与既有实现的功能差距，未将缺失能力伪造为已实现功能的回归或新安全漏洞；BUG-05 的配置图误导问题仍保留原证据。整改包括生成上下文解耦、可信工作区身份、workspace 作用域存储及审批、局部执行绑定。共享执行器无法区分工作区时必须拒绝应用，禁止自动扩大到整个实例。

闭环验收使用 RFC A1–A12，重点覆盖无会话生成、跨 Agent/工作区隔离、审批漂移、未来会话继承与真实内核 allow/block。状态：架构和文档已更新，实现及运行验收待完成；本补记不将既有 BUG 标记为已修复。
