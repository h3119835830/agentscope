# AgentScope 策略界面与确认链路已复现问题

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
