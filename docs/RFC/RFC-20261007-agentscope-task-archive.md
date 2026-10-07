# RFC：AgentScope统一任务档案

日期：2026-10-07。状态：实现与两任务真实闭环、最终字段记录界面及历史图验收完成。

## 身份与职责

每个逻辑task_id一份档案；启动生成、人工审核、恢复代次与权限版本均为子记录。同工作区的新任务不合并。来源实例使用任务创建时不可变workspace_source.instance快照，受管执行身份独立为managed:<task_id>。

档案是现有tasks/bootstrap/managed/policy/history/scope/runtime/audit表的只读投影，不建立第二套策略状态、不调用Broker。历史PID、phase/gate、加载收据不代表当前有效；缺失证据标记not_recorded。native独立观察不能证明某受管任务正在执行。

当前选择器只提供可操作任务。连接DB fallback仅web且phase=running/recovering/generating；paused是gate。failed可恢复不等于活动，仅本轮Broker connected证据允许处理DB竞争，失联即移除。native offline登记保留供重新检查。

## 读取合同

- GET /api/task-archives?q=&status=ended|active|all&page=0&limit=12：数据库搜索、筛选、计数和分页，limit最大50，返回records/total/page/pages/limit/history_only。每任务一行，含id/name/status/phase/created_at/ended_at/updated_at/version/source与workspace={name,path}。active只表示已登记未结束，当前可操作性由执行入口另行筛选。
- GET /api/tasks/{task_id}/archive：header、三阶段摘要、counts、events、missing、next_cursor及stage_previews。
- stage_previews[stage]={events,highlights,highlight_total,highlight_limit}：events为原阶段最新3条；highlights独立查询同任务全索引，最多20条完整安全关键事件。真实policy_active/deployment/closed/cleanup优先，再收录审核/恢复/失败；候选、runtime_job、高频pause/probe不进入关键摘要。该查询不改变主events的total/cursor/时序。
- GET /api/tasks/{task_id}/archive/events：category=timeline|tools|kernel|audit，可选stage=preparation|execution|closure；limit默认50、最大200。游标绑定任务/分类/阶段，误用422。
- GET /api/tasks/{task_id}/archive/events/{event_id}：安全详情；外任务事件404。

事件保留稳定id/source_id/time/task/job/version/evidence引用。source/storage_source是原表；action_source才表达登记的independent_probe/native_tool/kernel/controller/user_request/agent_report/not_recorded，不按PID相同推测。

审计行呈现动作、路径、PID和来源。operation_verified保留安全probe/probe_binding/kernel_events及classification/expected/effect_verified/before_hash/after_hash；kernel保留verification_probe/native_sdk_verification显式真假标志。未知引用不猜测，原始文件内容不导出。

## 档案内历史域图与DSL

GET /api/tasks/{task_id}/archive/domains?version=N返回task_id/version/versions/nodes/edges/available/status/missing_sources/recorded_at，始终live:false、historical:true、history_only:true、checked_at:null。版本只来自同任务policy_active收据；未登记版本404，无收据旧任务返回空图和not_recorded。

GET /api/tasks/{task_id}/archive/domains/{key}接受vN:task|baseline；非法key或不属于任务的版本404。合法版本缺材料返回200、available:false、missing_reason，不输出DSL；不能将材料缺失混作跨任务拒绝。

复用managed.topology.receipt/domain_sources/domain_detail读取root-owned策略材料；任务域须匹配历史policy_hash，底线须匹配原baseline_binding.bundle_hash。底线缺expected hash仅保留已登记元数据，available:false，不导出DSL/labels/合成hash核验。图响应不含DSL，节点详情才导出安全DSL/hash/source/labels。missing_sources列出原因，任何缺失均保留notice。

进程只来自该版本加载收据明示runner_pid/watch_pid/executor_pid。runner/executor只画历史收据关联；watch是控制面加载监控关联，不是任务域成员。不补画全局D0、不推断父子进程或当前同域，不调用workbench/graph/Broker。管理员middleware沿用，在当前档案内展开查看，不跳离任务。

## 权限与公开证据边界

Pi提交候选，restrict/expand均须匹配job/hash/revision/version/binding的人工审核。no_change/guidance_only不产生权限。拒绝/澄清可离线；approve须冻结来源、编译器和当前绑定核验，并在quiesce后、launch前重验来源。旧审核尾部不能覆盖新代次暂停或候选，恢复保留未审意图。

工具结果、Agent报告、控制暂停、内核拒绝和独立effects分别表达。工具成功不能证明OS allow；当前审计覆盖已收集的file denial与独立影响，不是全部syscalls。

公开档案/验收证据不输出凭据值或哈希、私有推理、原始模型流、raw runtime context、serialized工具参数/结果或wholeDB。运行验收与测试结果见REVIEW，缺陷因果见BUG。

## 最终页面组织

三个主模块为Agent连接、策略工作台、任务历史。档案内部使用概览/准备与授权/执行与权限/结束与结果页签，默认字段和关键权限记录，全部事件另行分页；详情和历史域DSL就地展开，不切一级模块。来源Agent与实际受管执行实例分列，历史身份不作当前连接依据。接口不完整只影响局部历史图，刷新/后退/焦点恢复保持同任务档案。最新验证与发布资源以REVIEW为准。
