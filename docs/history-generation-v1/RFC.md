# RFC：历史策略库第一版统一生成

日期：2026-10-04。实现分支：`codex/history-library-v1`。本轮第一、二层均保留 GitHub；本地目录、上传延期。本 RFC 更新此前“策略输入与采集审计”的第一层页面和转换合同。第二层 Pi 的任务工具、审批和执行范围继续独立。

## 职责与数据流

历史策略库只保留“策略生成”“策略记录与加载”“生成记录与审计”。一次输入锁定 GitHub commit，保存原始文件 SHA256，按完整段落、列表和围栏代码块组织语义块。65 行是目标大小，完整块不硬截断。大于 80 KB 的块或大于 120 KB 的复核上下文保留为待澄清。

固定、无工具的 DeepSeek 流水线执行初次抽取、独立完整性二审、PolicyIR 生成。二审读取完整块、标题、相邻块、候选和结构化能力定义，保存公开结论、多段准确引用及调用元数据。完整性指原文要求是否完整；机器路径是否绑定归属适配。独立单条二审只审核选定候选，不执行整篇抽取任务。

原文和附加证据逐段定位；未定位、缺失要求、超限或悬空引导语阻止最终批准。完整祈使短语可以成立，描述性内容不作为执行策略。描述性记录用于覆盖率与审计，策略结果及目录默认隐藏。LLM 的语义判断仍需最终人工确认，程序不保证自动分类完全正确。

`PolicyIR/v1` 结构化来源、原子规则、事件、标签布尔表达式、例外 gate、指导项、缺失参数及执行缺口。代码确定性渲染 DSL 和展示伪代码。共享渲染器支持文件、执行、网络和跨事件语法；Pi 适配器仍只接受此前受控的 write/unlink 草案能力。渲染器限制名称、未登记标签、64 UTF-8 字节 pattern、argv 敏感 exec 的 kill 语义；文件对象须位于服务端核验的工作区、嵌套指令范围和操作对象内。

语义/内容要求保存指导项，新增执行 DSL 为空；伪代码不能加载。候选编译最多初次加一次诊断反馈修订。失败保留诊断、成功结果继续保存，不进入执行包。

## 接口与检查点

- `POST /api/history/generations`：GitHub 输入或确切 `statement_version_id` 二选一。GitHub 包含 repo_url/ref/additional_paths/include_instruction_files；后者默认 true，false 可只采集指定文件。request_key 绑定相同输入；固定 commit 缺省采用稳定键；活动相同输入复用批次。
- `GET /api/history/generations`、`GET .../{id}`：批次、阶段、状态、统计与步骤。
- `GET /api/history/generations/page`：生成记录分页，q/status/limit/offset，默认20、上限100，返回 items/total/limit/offset，按 created_at、id 倒序；静态路由先于 /{id} 注册。旧无参数列表保留数组和最近100条兼容合同。单条生成从其不可变语句来源投影仓库、commit、路径，搜索覆盖这些继承字段，不改写来源快照。列表统计默认排除描述性内容。
- `GET .../{id}/results`：分页及 q、execution_level、context_scope、completeness、adaptation、loadable 筛选，返回证据、产物、编译、review_blockers 和 load_blockers。
- `POST .../{id}/cancel`、`POST .../{id}/retry`：取消于当前调用返回/超时边界生效；重试复用有效完成步骤，重新执行失败候选及覆盖不完整的文档。保留原成功版本及历史作业。
- `POST .../{id}/review`：一次事务批准/拒绝语句及产物，绑定 statement_version_id、expected_statement_hash、artifact_id、expected_artifact_hash。新版本需重新审核。旧分阶段接口保留兼容，但不能绕过加载校验。

新增 history_generations、history_generation_steps、history_generation_results，不改写旧版本 JSON/hash。创建和重试的批次/作业在同一 SQLite 事务中排队。服务启动将运行中的批次标为 interrupted；取消不回滚已经完成的证据/结果。有保留结果的覆盖不完整或单条失败显示 partial，全部产物失败显示 failed，不能伪报全部成功。伪代码从结构化记录（含 PolicyIR 条件与规则）确定性渲染，仅供阅读。

## 页面职责与浏览状态

策略生成只负责来源输入、创建生成和本次结果审核，无历史选择器。无当前记录时显示输入，有结果时由“新建生成”弹窗发起；创建成功后才切换当前记录。页面保留来源、版本、五类筛选和策略产物详情，过程操作通过“查看生成记录”定位到第三模块。

生成记录与审计默认展示每次生成的一条记录，另有后台作业、操作日志；重试不产生新的父生成记录。历史结果复用 GenerationResults 的只读模式，不提供选择或审核按钮；“继续审核”显式切换当前生成并回到策略生成页。取消、检查点重试、模型调用和过程诊断集中在记录详情中，阶段名称使用中文。

HistoryLibrary 管理当前生成 ID 和历史预览 ID；sessionStorage 延用 historyGeneration 键。历史预览不覆盖当前对象，切换结果重建筛选、分页和勾选状态；刷新恢复当前对象，记录不存在时清理失效 ID 并显示输入空态，不自动选最近历史或测试记录。手工输入和 RQ1 单条转换继续共用原生成接口。此次页面调整无数据库迁移、不改变审批 hash 或加载权限。

## 适配与加载边界

未绑定参数的候选标记 adaptation.required，保留原仓库、commit、scope 和原因，不提前替换本机路径。允许审核入库，禁止构建可执行包或加载。

适配通过确切语句版本修订生成新版本，核验当前未启动任务的同仓库/commit、工作区内真实文件/目录、嵌套指令范围，保存 target_paths/allowed_paths/context_note、参数来源及 adapted_from。再次二审、IR 校验、编译和最终审核。环境绑定包括任务、仓库 commit、工作区/输出映射、DSH profile、有效配置 hash、运行包和执行能力；Broker 只返回公开配置事实，API 不读取私有凭据配置。

策略包构建时会更新的策略选择/基础限制不放入环境指纹，以免自行失效；这些内容受整包版本与批准 hash 约束。列表、整包构建和 Provider 启动前复核共用 eligibility 合同；标签变化不能消除 IR 缺口、环境凭据或内容 hash 限制。继续执行域/PID 回查与退出清理。

任意附加文档只表示证据来源，不能因为文件位于深目录就自动取得该目录的指令权限；只有嵌套 AGENTS.md/CLAUDE.md 形成目录 scope。符号链接采集拒绝逻辑保留。

## 本机部署与隔离

独立工作树 `/opt/agentscope-history-v1`，API `127.0.0.1:18002`，独立数据库 `/var/lib/agentscope-history-v1/acceptance.sqlite3`、任务根 `/h`、Broker socket `/run/agentscope-history-v1/broker.sock`。开发页面沿用已授权的本机免口令模式；生成器仍使用任务级凭据，不能审批或加载。

不覆盖正在改动的 `/opt/agentscope` 和 18000，不批量修改 721 条 RQ1，不涉及丰安途/Hermes 业务代码。该工作树共享已安装的只读 Node/DSH/ActPlane 依赖。Pi 沙箱只挂载固定扩展、系统提示和解析后的依赖目录，避免绝对依赖软链在沙箱中失效。

入口：`sudo /opt/agentscope/.venv/bin/python scripts/history_service.py start|restart`；验收 `scripts/history_acceptance.py first-layer` 与 `rq5`，串行执行并检查其他实例活动域。当前运行证据见 REVIEW，代码入口默认路径适用于本机已安装环境。
