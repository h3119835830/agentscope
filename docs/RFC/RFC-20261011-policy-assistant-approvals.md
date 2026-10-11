# 策略助手详情与审批入口合同

日期：2026-10-11。范围：真实 AgentScope 18003 的 Agent 策略助手、候选详情和 DSL 策略审批。

## 页面与流程

Agent 页保留简洁对话与单一输入区。用户需求只呈现一次；生成结果以小型策略卡片展示保护对象、触发操作、处置方式，提供查看详情、提交审批。未形成可执行 DSL 的候选仍可查看识别结果并补充需求，不能提交审批。

“选择策略”打开可搜索记录表，分策略模板、当前 Agent 当前会话的已生成策略、已配置候选。模板先配置为本地候选；选择、查看或切换标签不写入策略配置。

侧栏恢复独立“审批”入口，任务历史仍在最后。审批表按待审批、需要处理、已处理筛选；列为策略变更、Agent / PID、生成会话、状态 / 提交时间和操作。支持按策略、产品、PID、原生会话名称与 ID 搜索；Agent 与会话均提供精确定位入口。详情按变更内容、影响范围和校验结果分组，完整 DSL 单独查看。策略范围为当前 Agent 的全部会话；会话仅提供生成上下文，不将其描述为单会话执行隔离。

## 接口与职责

- GET `/api/console/approvals` 与 `/{id}`：读取已有 `instance_dsl_proposals`；过滤产品层隐藏实例。未知或隐藏记录返回 404。不是独立审批数据库。
- GET `/api/console/summary`：增加 `pending_approvals`，用于侧栏提醒。
- 提交：先读取当前 Agent DSL；服务端生成候选按精确 Agent 与原生会话重新核验；使用现有 POST `/api/agent-instances/{id}/dsl/proposals` 创建并校验提案。相同当前版本与相同文档、仍可应用的待审批提案直接复用。
- 确认应用：仅用户点击“批准并应用”后调用现有 scope 对应 `/proposals/{id}/confirm`。沿用 proposal_hash、base revision/hash、目标运行快照和生成上下文复核；不改变现有编译/加载机制。
- 拒绝：新增 scope 对应 `/proposals/{id}/reject`，验证精确 scope/id/hash。只结束 pending/invalid/failed 提案；重复拒绝幂等，已应用或正在应用禁止拒绝。记录审计，不更改当前 DSL、不加载策略、不启停 Agent。

## 边界

审批列表的 pending 不等于运行生效。读取时发现策略基线或 Agent 环境变化，显示需重新校验且隐藏批准操作；确认接口仍作最终复核。生成详情 source 采用生成时冻结的实际 source pattern，此实例为 `**/node`，不能用产品名伪造启动文件。

本入口管理 DSL 策略提案，不合并原生工具调用权限提案。生成记录中的人工 review 与 DSL confirm 仍为不同事实。历史或现有运行保护不能由此页面推断。

## 审批定位投影补充（2026-10-11）

列表与详情增加只读字段 `agents`（id、产品名称、当前核验 PID、进程状态、提交时 PID）、`origin_sessions`（instance_id、session_id、原生名称、记录可用性、生成时 PID）与 `origin_state`。后台 scope/target 快照、proposal_hash 和确认合同均不改变。已知产品名称来自 agent_type 映射，不直接展示内部登记别名。

当前 PID 仅使用 observer 的 connected + verified 当前连接；未知或离线时不展示历史 PID 作为当前 PID。提交时 PID 仅在冻结目标 active 的情况下展示。生成时 PID 从已冻结且通过内容哈希核验的环境绑定读取；不同阶段的 PID 不相互替代，也不用于合并会话。

生成会话按文档 generation_binding → artifact → 已冻结 statement version 的 resolved_context 定位；校验 version 内容哈希、environment_binding 哈希及精确 Agent/session 对应。历史环境变化不删除来源关联；未保存关联的手工或旧模板记录显示“未关联会话”，证据缺失显示不可用，不推测当前会话。名称来自精确 `(instance_id,session_id)` 的原生会话缓存；记录缺失仍保留 ID，但禁用打开。每次列表读取只构建一次运行清单与会话缓存索引，不调用会话激活或生成接口。

一个提案可包含多份已生成配置，列表允许展示多个配置生成会话；这表示候选配置的生成来源，不伪称为唯一提交会话。系统提案保留全部实际影响目标（含收起实例），不因产品筛选隐瞒系统影响范围；Agent 提案仍按可见 scope 过滤。生成会话只是需求/工作区上下文，Agent 共享策略仍影响该连接的全部会话。

桌面采用固定比例五列表，提交时间放状态下方；窄窗口改为带字段名的逐条记录，避免水平滚动隐藏操作。详情的定位摘要保持在 DSL 和配置两个页签上方；打开来源或切换页签均为只读导航。
