# RFC：历史策略输入、转换与独立采集审计

日期：2026-10-04。状态：实现并验收。范围：AgentScope 历史策略库；原 721 条 RQ1 记录保持状态，不涉及普通业务。

## 页面职责

历史策略库新增第五个二级模块“采集与审计”，集中展示持久化后台作业、输入、结果引用、起止时间、失败重试和操作审计；其他四个模块不再附带后台作业列表。作业与操作审计分别分页和筛选。

策略记录将“执行层级”“上下文范围”直接展开。指令来源层、仓库及归档保留附加筛选；后端在分页前联合筛选，使用最新语句版本的标签。执行层级对应 semantic/content/per-event/cross-event，指令来源层对应 repository_instruction/manual_instruction/llm_candidate，两者不混用。

转换页明确提供“选择已审语句”和“输入新策略”。原句是输入；伪代码是结构化记录的确定性展示；DSL 为模型生成并经编译、审批后加载的执行产物。缺失路径或能力缺口阻止执行产物，语义和内容要求不会强行生成 OS 规则。

## 接口合同

- `POST /api/history/inputs`：自然语言原句、执行层级、上下文范围、可选翻译和任务 ID。保存原文快照及待审语句版本。关联任务的 repository/commit 仅表示适用绑定，手工输入不是该仓库原文件；authority 为 user_input_candidate。
- `POST /api/history/records/{id}/statement-input`：将原目录记录准备为转换输入。RQ1 必须重新核验固定源文件 hash 和精确原文行；不继承目录审批。手工目录记录登记输入快照。已有版本只能修订确切语句版本。
- `POST /api/history/statements/{id}/revisions`：`resolved_context` 增加 `target_paths`。核验路径存在、在当前 workspace 和嵌套指令 scope 内，拒绝路径穿越及符号链接逃逸；保存 `verified_targets` 的 relative_path、absolute_path、kind。允许修改子树与操作对象分开表达。
- `GET /api/history/activity`：section=jobs/events、kind、status、q、limit、offset。投影公开作业/策略审计字段，排除凭据与模型私有推理。
- `GET /api/history/records`：保留 category/context_scope，增加 execution_layer 来源层过滤；详情返回 metadata_preview，executable=false。

手工与 RQ1 输入只需原句；另一语言译文可补充。文档模型抽取仍保留原双语审核合同。语句审核绑定内容 hash，候选及整包审批、编译、Provider/Broker 加载沿用原合同。

## RQ1 数据与模型上下文

本机 721 条来自 candidate_rules.tsv 的原句目录，原导入没有逐条转换产物。新增 metadata_preview 仅渲染当前原句、来源、标签、状态，candidate effect=none、state=not_generated；不是原研究伪代码，也不是已审 DSL。不自动导入或映射研究产物到这些记录。

翻译输入增加通用 `ENFORCEMENT_CAPABILITIES`：批准进程域、子进程继承、OS 文件事件覆盖、域外进程边界、语义检查不支持及已有文件元数据限制。模型得到 verified_targets 和该能力合同，不新增场景特定修复提示词。翻译版本更新为 history-translate-v5；未清除模型报告的未解决缺口。

## 验收

92 项后端测试通过；真实 DeepSeek + ActPlane 编译及 RQ1 隔离副本转换通过；实际浏览器审计、组合筛选、伪代码、输入框和弹窗键盘关闭验证通过。原库 721 状态及原句摘要未变。详细证据见同日 REVIEW。
