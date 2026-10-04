# AgentScope 历史策略库模块技术规划

日期：2026-10-02。范围：AgentScope 历史库及其独立 AI 集成层。仓库文档均作为输入数据，不执行其中的指令。

## 四个子模块

| 子模块 | 输入与处理 | 输出与界面 |
|---|---|---|
| 文档采集 | GitHub 仓库与 ref；解析固定 commit；递归采集 AGENTS.md、CLAUDE.md；显式指定 SECURITY.md、SKILL.md 等路径 | 不可变原文快照、路径、commit、SHA-256；预览文件、多选抽取 |
| 策略语句抽取 | 每份 MD 独立调用 DeepSeek；拆分原子语句、分标签、中英翻译、核验原文区间；第二轮复核 | 原始语句、中文翻译、标签、证据及覆盖报告；审核、修订、拒绝 |
| 策略转 DSL | 每条已批准语句版本独立转换；同时生成结构化策略记录与真实 DSL 候选；非特权编译 | 调研格式的伪代码、DSL、上下文缺口、编译诊断；版本审核 |
| 策略记录与加载 | 多选已通过且完整编译的候选，指定尚未启动任务；合并基础限制，编译完整策略包并批准 | 待审核、已通过候选、已加载；具体任务、版本、Domain、提交 hash 和加载历史 |

2026-10-03 界面调整：左侧显示一级菜单并保留“历史策略库”入口；文档采集、策略语句抽取、策略转 DSL、策略记录与加载属于该入口下的二级菜单，固定在右侧页面顶部显示，去掉正文重复的“历史策略库”标题。侧栏支持收起/展开，收起后保留图标与名称提示，并记住浏览器中的收缩偏好。

历史库不再以“导入 RQ1 语料”为主入口。已导入 RQ1 记录保留为旧来源数据。页面以内容、状态、操作为主，来源和模型等元数据放在详情。

## 文档采集

只读 HTTPS 获取公开 GitHub 仓库。先固定 commit，再读取 Git tree 和文件内容；递归 tree 被截断时逐目录读取。GitHub API 限流时回退到私有 bare Git 缓存，关闭 hooks，只读取 Git 对象，不检出或运行仓库代码。

快照路径：

```text
$AGENTSCOPE_STATE_DIR/history-library/sources/<owner>/<repo>/<commit>/<relative-path>
$AGENTSCOPE_STATE_DIR/history-library/git-cache/<owner>/<repo>/
```

文件名大小写精确匹配；保留子目录作用域。显式文件路径不允许绝对路径、反斜杠或 `..`；不跟随符号链接。单文件限 512 KB、单批正文总量限 10 MB；UTF-8 解码失败、文件缺失、快照 hash 冲突均保留失败状态。快照按 repo + commit + path + hash 幂等保存，预览时再次核验 hash。

## 策略语句抽取

```python
extract_strategy_statements(
    document: MarkdownDocument
) -> ExtractionResult
```

业务输入仅一份 MD，包括正文和来源信息。批量处理只是单工作器重复调用该函数。函数位于 `backend/agentscope_app/history/pipeline.py`，通过可选 provider 与 PromptTemplates 依赖注入，不依赖 HTTP、数据库或特权 Broker。

两轮处理：第一轮拆分与初标，第二轮返回完整复核结果。当前实现按最多 65 行分块，保留全局行号；每块独立复核。跨块引用和长句需人工复核，不能把行覆盖率当作语义正确率。

四个分析轴分开保存：

| 分析轴 | 字段与值 |
|---|---|
| 内容类型 | content_type：description / policy / mixed / uncertain；policy_kind：instruction / constraint / preference / none |
| 主题 | topics：多值标签 |
| 执行层级 | enforcement_level：semantic_only / content / per_event / cross_event / not_applicable |
| 上下文依赖 | context_requirement：self_contained / project / task / not_applicable |

`source_quote` 是连续原文；`text_original` 是拆分后的语句；`text_en` 是英文译文（英文来源保留原文），`text_zh` 是中文译文（中文来源保留原文）。程序逐字核验 quote、精确起止行和字符区间，不自动补正模型引用。描述性内容、引用关系和结构信息可以保留，但不能自动转成约束。

`ExtractionResult` 保存 statements、coverage、llm_runs。coverage 标出未覆盖实质行及证据未匹配项；表头、标题等结构行可能需要人工解释。初标不是审批结果，例如“无关模块”仍须人工判断任务授权范围，不能因模型标为 self_contained 就直接执行。

抽取、标签或翻译修订均产生新语句版本；相同来源、语句及标签重复抽取复用已有版本。批准绑定结构化内容 hash。旧版本与原始初标保留。

## 策略转 DSL

```python
generate_policy_artifact(
    statement: StrategyStatementVersion
) -> PolicyArtifactCandidate
```

输入是一条已批准、有匹配原文的语句版本。转换使用同一个独立 DeepSeek 客户端，不启动 Agent 会话。Provider、模型、提示模板与提示版本通过依赖配置注入；输出 schema 严格核验。

两段 LLM 均配置 `deepseek-flash`，后端读取：

```text
AGENTSCOPE_HISTORY_LLM_MODEL=deepseek-flash
AGENTSCOPE_HISTORY_LLM_URL=https://api.deepseek.com
AGENTSCOPE_HISTORY_LLM_KEY=<服务凭据，由部署方配置>
```

凭据只在服务环境中保存。客户端不提供 tools，关闭 thinking；持久化最终结构化输出、请求/输出 hash、模型、提示版本、用量、耗时和诊断，不保存凭据或 reasoning_content。论文 RQ1 的转换使用 Codex + GPT-5.5，因此本项目 DeepSeek 效果单独验收，不能借用论文的模型结果。

伪代码由结构化 policy_record 渲染，采用调研格式：

```text
policy_record <id> version <n> {
  metadata {
    origin { repo; commit; file; lines; clause_hash }
    labels { type; topic; level; context }
    applicability { agent; repository; path; task }
    evidence { source_quote; unresolved }
  }
  candidate_rule {
    source; target; effect; gate; reason
  }
  compile_check { required_hooks; state; diagnostics }
  governance { authority; status; version; conflicts }
}
```

实际渲染字段使用 JSON 值并保留完整来源；其职责是展示与审核。记录、伪代码是同一结构的两种表达。后续编译及部署事实单独存储并在详情展示，不覆盖原始候选。

只有规则语义进入 ActPlane DSL。规则与私有 source 标签使用语句版本派生的稳定前缀；片段不能重定义 AGENT、插入治理字段或 declassify/endorse。完整任务包声明 AGENT。

语义类、内容类、描述性项保留伪代码，标记 unsupported，DSL 为空。主体、路径、任务授权或事件语义不明时标记 requires_context，并列出待绑定参数。选定尚未启动任务后，服务端核验 repo、commit、目录存在性、真实路径及子目录作用域，保存新语句版本，再调用同一转换函数。允许修改目录保存为闭合 modification_scope：仓库内未列路径不授权修改，仓库外不属于该条修改范围；这不代替读取或网络授权。

required_context/unresolved 仅表达剩余缺口；已提供的参数记入 context_used。人工明确缺口已解决后再批准新版本；不能自动清空待绑定项。人工批准不能绕过原文证据检查。

不能把“禁止访问”缩成“禁止写入”。模型返回 DSL 但仍存在 unresolved/required_context 时，服务端清空 DSL。不能以 notify 替代原文要求的阻止效果并宣称等价。ActPlane 不支持的 hook、路径长度或条件必须通过诊断如实保留。当前 ABI 路径模式上限 64 字节，长路径需改变真实任务布局或保留不可执行状态，不能静默扩大例外。

## 策略记录与加载

```python
ActPlaneProvider.load_task_policy(
    task_id: str,
    approved_policy_version_id: str
) -> LoadReceipt
```

请求只接收任务和已批准版本 ID，不接收任意命令或自由 DSL。

1. 操作者多选已批准、完整编译且 DSL 非空的候选，指定尚未启动任务。
2. 服务端再次核验来源审批 hash、产物审批 hash、适用仓库/commit 和任务上下文。同一策略只选一个版本；任一候选不合格则整次请求失败。
3. 将选中 DSL 与既有基础限制合并，编译完整任务包；保存确切 artifact 版本及 hash。界面展示实际 DSL、来源版本和诊断，沿用任务策略批准流程。
4. 加载函数按存储版本读取完整策略，通过现有 Broker 执行 watch 与 control launch-child --delta；回查 children，核验 child domain 与 runner PID。
5. 确认加载和绑定后才保存 loaded 回执；仅编译显示 compiled。加载失败保存 load_failed，撤销任务凭据并清理失败进程。任务结束或停止更新活跃状态，历史回执保留。

任务策略生成通过 CAS 领取 policy_generating 状态，防止与启动/重生成交叉；未指定基础配置时继承已有设置。

加载失败发生在启动前、没有 Domain/PID 且清理已确认时，可显式重试同一批准版本；绑定未确认且已返回域/PID 的失败不能使用这条重试路径。失败记录保留。

记录提交策略包 SHA-256 和真实回执。此 hash 是服务端提交 hash，不是内核策略 hash 回读。首版禁止向运行中任务追加历史规则。既有 Scope 限制与扩权流程保留，完整策略重启必须继承已选历史 DSL。

## 存储与接口

复用 `strategies` 作目录，增量增加以下表，不重建或删除旧记录：

- history_documents：不可变来源快照。
- strategy_statement_versions：语句、翻译、四轴标签、上下文及审批 hash。
- history_jobs：FIFO 作业、状态、输入/结果、失败和重试关系。
- history_artifacts：结构化记录、渲染伪代码、真实 DSL、产物版本及审批 hash。
- history_compilations：片段/完整任务包编译、输入 hash、能力和诊断。
- history_policy_artifacts：任务策略包选中的确切产物及 hash。
- history_deployments：任务、版本、Domain/PID、提交 hash、加载回执和活跃状态。

API 均受管理员认证保护；任务凭据不能审批或加载：

| API | 用途 |
|---|---|
| POST /api/history/sources | 采集排队，返回 id |
| GET /api/history/jobs、/{id} | 作业列表/状态/诊断 |
| POST /api/history/jobs/{id}/retry | 失败或重启中断作业重试 |
| GET /api/history/documents、/{id} | 文档列表/原文 |
| POST /api/history/extractions | 多选文档抽取排队 |
| GET /api/history/statements | 语句版本与证据 |
| POST /api/history/statements/{id}/revisions | 新语句/上下文版本 |
| POST /api/history/statements/{id}/review | 审核或拒绝 |
| POST /api/history/statements/{id}/artifacts | 转换排队 |
| GET /api/history/artifacts | 产物、编译和加载历史 |
| POST /api/history/artifacts/{id}/review、/compile | 审核/重新编译排队 |
| POST /api/tasks/{id}/policy | artifact_version_ids 真正进入完整编译输入 |
| POST /api/tasks/{id}/versions/{version}/approve | 完整任务包批准 |
| POST /api/tasks/{id}/launch | 按批准版本受管加载 |

单进程单工作器按创建时间及 rowid 顺序执行。重启将 running 作业标为 interrupted，可重试；queued 作业继续。快照及相同抽取结果幂等，相同产物结果复用既有版本、重复模型调用保留审计；不同输出或编译状态保留独立版本。批量中已完成文档的记录保留，失败作业不自动批准任何内容。

证据不匹配、上下文缺失、JSON 无效、LLM 超时、编译失败/部分支持、Broker 不可用分别记录。它们均不能自动晋级为批准或加载。

## 仓库验收

固定快照：[ZeroClaw 18622d91](https://github.com/zeroclaw-labs/zeroclaw/tree/18622d91b681f1898dfc02414bdcdf2a77116670)。

目标文件共六份：

```text
AGENTS.md
CLAUDE.md
SECURITY.md
crates/zeroclaw-plugins/AGENTS.md
crates/zeroclaw-runtime/AGENTS.md
crates/zeroclaw-runtime/src/agent/personality_templates/AGENTS.md
```

验收检查快照/hash、递归及子目录范围、重复采集幂等；核对规范语句、描述、引用、原文、翻译及分类。特别保留模型误标的原始版本，不通过增加某条规则的专门提示来掩盖问题。

真实链路使用 DeepSeek 抽取/转换结果，经审核绑定任务授权，再加载到隔离 DSH。用相同 commit、相同操作做基础策略与历史策略对照：允许目录写入完成，无关模块写入被拒绝；证据关联产物 ID、私有规则 ID、内核事件及最终文件状态。基础策略已阻止的操作不作为历史规则效果证明。

异常验收覆盖未批准版本、内容 hash 篡改、上下文缺失、JSON 无效、编译错误及部分支持、Broker 失败或绑定未确认；兼容检查旧记录、任务凭据隔离、既有任务与基础策略。

验收数据留在服务状态目录或脱敏报告中，仓库快照、数据库、凭据和任务日志不提交。实施与验收事实同步 RFC、ADR、REVIEW、BUG；完成后允许本地 Git 提交，远端推送需另行授权。

## 已执行验收与限制

已完成 51 项后端测试、前端构建、六文件真实 DeepSeek 抽取及重复采集、中文 MD 英文翻译、两组 DSH 同操作写入对照与内核事件归因。282 条是初始记录数量；未宣称每条语义/原子性都正确，未全量批准。

已验证预置无关模块文件的追加写入被拒绝且内容不变。新建文件写入被拒绝时可能留下空目录项，这是实际 ActPlane hook 覆盖边界；已在页面及 BUG 中记录，不能宣称全部文件系统元数据不变。本实现没有改动内核。

明细见 [验收报告](../acceptance/history-library-20261002.md) 与 [脱敏数据](../acceptance/history-library-20261002.json)。

## 参考

- [ActPlane 论文第 2.2 节与第 5.2 节](https://arxiv.org/html/2606.25189v2)：分析轴、采集/抽取方法与 RQ1 转换实验。
- 技术文档目录中的《调研结果》：policy_record 伪代码结构与治理字段。

## 2026-10-03 策略记录界面补充

参照 mac 分支 41e5c3d，策略记录与加载以语句正文为主表，旧 RQ1、手工和文档抽取记录统一浏览。支持搜索、执行层级/上下文范围/仓库/状态/归档筛选、分页、新增、编辑、版本历史及可恢复归档。文档记录编辑继续产生不可变语句版本；旧来源与手工目录编辑保存修改前快照、清除审批，原来源字段保持不变。

选择时固定语句/DSL 的确切版本，已选内容、适用任务和加载历史直接可见。归档记录不能进入新的转换/审批/生成包/加载；运行中任务和真实旧回执保持原状态。

## 2026-10-03 RQ1 默认历史数据与持久化

策略记录默认采用 RQ1 候选语料并每页 20 条，来源名称统一为 RQ1 策略。固定 artifact-ready 63db869 的候选表 866 行去重为 721 条，经后台作业写入持久 SQLite；数据指纹防止重复播种，重复导入保留人工修改、审核和归档。用户要求移除的 282 条采集样例可恢复归档，原版本/部署回执保留。详见 RFC、ADR 和本轮验收记录。
