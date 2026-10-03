# RFC：AgentScope 历史策略库

日期：2026-10-02。状态：已实施并完成有限范围真实链路验收。代码：WSL `/opt/agentscope`，应用版本 0.2.0。范围仅 AgentScope 历史库及独立 AI 集成；不修改普通业务或 ActPlane 内核。

## 职责与数据流

| 子模块 | 职责 | 合同 |
|---|---|---|
| 文档采集 | 固定 GitHub commit，递归 AGENTS/CLAUDE，支持指定文件；只读快照 | repository、commit、relative_path、scope_path、SHA-256 |
| 策略语句抽取 | 单 MD、两轮 DeepSeek、原子语句及四轴分类、原文核验、中英文本 | MarkdownDocument → ExtractionResult |
| 策略转 DSL | 单批准语句版本；结构化记录渲染伪代码；编译真实语义片段 | StrategyStatementVersion → PolicyArtifactCandidate |
| 策略记录与加载 | 确切版本选择、完整任务包编译与批准、Broker 加载、域绑定回查 | task_id + approved_policy_version_id → LoadReceipt |

实现位于 `backend/agentscope_app/history/`。两个 LLM 函数通过 provider 依赖注入，不依赖 HTTP、数据库或 Broker，不启动 Agent 会话。后端独立 DeepSeek 客户端使用 `deepseek-flash`、JSON 模式、无 tools、关闭 thinking。保存最终结构化结果与模型/提示版本/耗时/hash；凭据只存服务环境，不保存 reasoning_content。

程序核验连续 source_quote、精确行号/字符区间，不自动修复引用。四轴为内容类型、主题、执行层级、上下文依赖；描述保留且不能自动成为约束。按最多 65 行分块，两轮完整复核；覆盖率不是语义正确率。text_original 保留原语种，text_en 与 text_zh 支持英文/中文译文；旧英文记录可由原文派生英文显示，不重写旧批准数据。

## 不可变版本与审批

复用 strategies 目录。新增 history_documents、strategy_statement_versions、history_jobs、history_artifacts、history_compilations、history_policy_artifacts、history_deployments 七表，增量初始化不删除旧数据。语句修订产生新版本；相同快照/抽取/产物结果幂等复用，重复模型调用另留审计。

审批绑定结构化内容 hash。选中产物必须来源批准、产物批准、hash 一致、完整编译、DSL 非空、仓库/commit/任务适用；整批不合格则失败。同一策略只能选一个版本。稳定私有前缀防重名，禁止片段重定义 AGENT 或引入 declassify/endorse。

policy_record 是伪代码数据源；编译与部署事实独立保存，原始候选不被后续状态覆盖。真实 DSL 仅规则语义，来源和治理字段不进入内核规则。

## 上下文与执行边界

requires_context 时 DSL 空；required_context 只列剩余缺口，context_used 列已提供参数。语义/内容/描述项保留为 unsupported。缺路径、主体、任务授权不猜测，禁止把 no access 缩成 no write。

任务绑定核验仓库/commit、目录存在性、真实路径、文档子目录范围。允许修改目录产生闭合 modification_scope：仓库内未列目录不授权修改，仓库外不属于该规则范围；这只定义修改授权，不代替读取、网络或其他策略。人工明确已解决缺口后保存新语句版本、审核，再用同一转换函数。

## 后台作业与 API

管理员 API：sources、documents、extractions、statements/revisions/review、artifacts/review/compile、jobs/retry。采集/抽取/转换返回 job ID，单进程单 worker FIFO。running 在重启后标 interrupted，可人工重试；queued 继续。每种失败独立记录，不自动批准。

现有任务生成 API 增加 artifact_version_ids，选中 DSL 实际并入基础限制编译；settings 缺省继承既有配置。生成通过 policy_generating CAS 防并发启动/重生成。完整编译和批准后，launch 调用 ActPlaneProvider.load_task_policy。

Provider 只读取批准的存储版本，不接收自由命令/DSL。通过现有 Broker watch、control launch-child --delta 启动，核验真实 child Domain 与 runner PID。仅编译为 compiled，绑定确认后为 loaded；提交包 SHA-256 与真实回执保存。任务结束/停止撤销凭据、清理 watch、关闭活跃部署。

仅在前次失败发生于启动前、没有 Domain/PID、清理已确认时，允许显式重试同一批准版本；绑定不确定的尝试禁止该重试路径。首版禁止运行中新增历史规则，既有 Scope 完整重启继承历史规则。

## 验收与已知限制

固定 ZeroClaw 六文档、真实 DeepSeek、两组 DSH 同操作对照及内核事件归因见 REVIEW。当前 file write/unlink hook 不能保证全部元数据不变；新建空文件残留、64 字节模式上限、单 Broker runtime、模型原子性/标签人工审核均如实记录。没有修改内核以掩盖该缺口。

参考：[ActPlane 2.2/5.2](https://arxiv.org/html/2606.25189v2)、[ZeroClaw 固定快照](https://github.com/zeroclaw-labs/zeroclaw/tree/18622d91b681f1898dfc02414bdcdf2a77116670)、主规划《AgentScope_历史策略库模块技术规划.md》。

## 2026-10-03 界面导航更新

左侧保留历史策略库一级入口；文档采集、策略语句抽取、策略转 DSL、策略记录与加载是该入口下的二级菜单，在右侧面包屑下方显示并保持吸顶。正文不再重复历史策略库标题。侧栏保留可访问的收起/展开按钮、图标名称提示和浏览器收缩偏好；二级菜单切换保留当前文档多选，左右方向键与 Home/End 支持切换。此变更只修改前端导航，不改变上述 API、权限、审批或运行时合同。
