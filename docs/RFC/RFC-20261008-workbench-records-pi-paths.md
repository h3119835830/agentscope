# RFC：原工作台记录展示复用与 Pi 短路径合同

状态：已实施，真实验收见同名 REVIEW。替代 RFC-20261008-task-replay 中的独立六主栏目与表格式记录展示合同。

## 展示与读取合同

历史回放与当前工作台复用 WorkbenchRecordViews 的纯展示记录行、状态标签、四项详情抽屉和监控分段控件；不挂载 ManagedWorkbench 的轮询、执行或审批逻辑。主栏目为运行前、运行时、执行监控、执行审计，任务概况及结束结果保留次级入口。标题与任务选择紧凑同排，来源、目录等元数据折叠。

archive/policies 新增 view=statements_only，仅返回已保存的真实子语句，total 与 cursor 按 task/stage/view 隔离。原 jobs 与混合 statements 读取合同保留。没有语句的生成批次在独立生成记录内懒加载和分页，失败、拒绝、无变化、仅指导等结果不丢失。没有独立指导语句的旧 guidance_only 作业不能把 explanation 或用户整段改写为 Pi 语句。

每条详情仍以精确 child ID 读取，逐句 DSL、完整候选包及加载回执分别表达；保留所有哈希、跨任务与旧响应隔离。历史域/PID 仍是保存事实，不显示为在线。OS 拒绝与效果核验、DSH 工具结果、控制面记录继续分开。

## 路径与工作流合同

ActPlane pattern 的公共 ABI 为最多 64 UTF-8 字节；控制字符及未绑定绝对路径继续拒绝。能力工具公开同一 policy_ir 常量。超限校验返回 diagnostic_details={code:engine_pattern_limit_exceeded,max_utf8_bytes,targets:[{path,utf8_bytes}],read_tool:get_task_context}，不能扩大目标、缩名叶文件或绕过校验。

新建来源工作区任务在固定上下文前识别独立项目根（setup.py、pyproject.toml、package.json 等 marker），仅在超长且别名确实更短时将整个项目根映射至无冲突 pN。父项目 marker 下的嵌套包不搬移。原文件名、项目内相对结构和全部字节保留，manifest 仍基于来源；每个资产保留 source_relative_path、mapped relative_path、mapped_path，上下文固定 asset_layout_mapping、prefix mapping 和 hash。已有任务上下文不可静默改写。无法表达的长叶名保持原状并报告 unresolved，不伪装成已支持。

Pi status 从服务器业务工具回执读取最近校验诊断和剩余预算，rpc_lifecycle 不覆盖业务错误。预算耗尽且没有已验证候选时终止并给出真实诊断；已有服务器验证候选仍允许按精确哈希提交。Pi 不审批、不加载、不执行任务；人工审核和核验边界不变。
