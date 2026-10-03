# AgentScope 历史策略库验收记录

日期：2026-10-02。实现基线：`2b48caecb3f9da44f8a1f83b3de8c42dcb1afd61`。范围仅为 AgentScope 及独立 AI 集成层；没有修改 ActPlane 内核、DSH、ERP 或普通业务代码。

## 验收结果

| 项目 | 证据与结果 |
|---|---|
| 代码验证 | 51 项后端测试通过；前端 Vite 构建通过。5 项现有 FastAPI/Starlette 弃用警告仍在 |
| 文档采集 | ZeroClaw 固定 SHA `18622d91b681f1898dfc02414bdcdf2a77116670`，六份文件；逐个与任务仓库 Git blob 比对相同，SHA-256 相同 |
| 重复采集 | 作业 `e52e86aa56a746a48a6a2905bf60f87b` 完成，返回完全相同的六个文档 ID |
| DeepSeek 抽取 | 实际 `deepseek-flash` 调用，282 条初始记录；原文引用全部逐字定位。保留 5 个结构行未覆盖诊断 |
| 翻译 | 中文测试 MD 两轮真实调用，规范句得到英文译文，Rust 描述保持 description；原文核验通过 |
| 审核与转换 | 语义/内容类产物保持 DSL 空；缺任务上下文保持 requires_context。L179 经标签/授权范围人工修订，新版本生成真实 DSL |
| 加载 | 两个历史任务均使用实际 DeepSeek DSL，经完整任务包编译/批准、Broker 加载和 Domain/PID 回查 |
| 失败 | 未批准候选选择返回 409；JSON/schema、私有前缀及加载失败保留记录；Broker singleton 失败没有成功状态 |
| 兼容 | 原数据库的 6 个旧策略版本 ID、DSL、YAML、编译内容不变。迁移前旧 strategies 行数为 0，旧 RQ1 保留由合成记录测试验证 |
| 页面 | 四模块、多选文档、已加载筛选、伪代码/DSL、失败历史及真实回执/提交 hash；旧 RQ1 主导入按钮移除 |

数据明细见 [history-library-20261002.json](history-library-20261002.json)。报告只含白名单结构化结果、公开语料、测试文件内容及选中内核事件；不提交数据库、任务原始日志、凭据或模型私有推理。

## 同一操作对照

来源语句：ZeroClaw 根 AGENTS.md L179，“不要顺手修改无关模块”。人工批准的任务授权仅为 `docs/`，其余仓库路径不允许修改。两组任务使用同一 commit、相同基础配置、相同文件操作；历史组额外加入经审核 DSL。

| 操作 | 基础任务 | 历史任务 | 归因与最终状态 |
|---|---|---|---|
| 新建文件并写入 | `28f337bb0c7b4c88`：docs 与 runtime 均写入成功 | `274d0f8d0e844bac`：docs 成功，runtime 内容写入被拒绝 | Domain `1857265411`；事件命中 `h_96cea88559124dc9_block_unrelated`。runtime 新文件存在但为空 |
| 对预置文件追加 | `c9e453fad81a49b2`：两个文件均追加成功 | `4732c36fa4d04d71`：docs 追加成功，runtime 保持 `ORIGINAL_FIXTURE\n` | Domain `1009245371`；事件命中 `h_befaa33923b14960_docs_scope`。无关文件内容 hash 保持原值 |

实际产物版本为 `fb1f5e922d0349319ae5ae5f8006dcda`、`0392b9471cfd4bcaa5344ab531687e16`。两次回执均 `binding_confirmed=true`，提交 hash 已保存；该 hash 是提交策略包的 SHA-256，不是内核 hash 回读。任务结束后活跃部署数为 0，历史回执继续保存。

预置文件历史组第一次加载因前一任务 watch 占用 singleton 失败，失败部署 `42f3027cb41c46e6b3aaccf314c4b05e` 保留。确认前任务结束并清理 watch 后，人工重试同一批准版本成功；没有自动重试或自动晋级。

## 效果边界

1. 新建空目录项可能先于写入 hook 被创建。此验收证明文件内容写入拒绝、预置无关文件内容保持不变，不能证明全部文件系统元数据不可改变。该 ActPlane 能力缺口保持开放，并在产物界面显示。
2. 282 条是初始抽取记录数，不是全量语义正确数。人工抽查发现 L168 复合策略未充分拆分，仍待审核；L179 初标被修订为 per_event/task；引用语句没有被当作被引用规则的副本。未对所有记录逐条确认。
3. 当前 ActPlane ABI 路径模式上限 64 UTF-8 字节。长路径不能通过扩大例外来掩盖编译失败。
4. 当前部署单 API 进程、单 FIFO 工作器，Broker watch 按顺序使用。没有多进程 worker 或并行内核任务验收。
