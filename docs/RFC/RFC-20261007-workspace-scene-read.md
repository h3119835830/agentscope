# 工作区场景先读后确认接口

状态：实现与验收通过。适用于任务创建入口，保留 Agent 连接、策略工作台、任务历史三模块。

## 职责

工作区选定后，先请求独立 Pi 读取作业，尚不创建执行任务。Pi 仅有列出场景来源、读取冻结来源片段、提交任务草稿三个受控工具。任务名称由 Agent 从已读证据生成；没有明确任务目标则返回 needs_clarification，补充目标后重新识别。不能用 README 文件名、模板关键词或硬编码任务替代真实 Agent 阅读。

只读识别不是任务执行，也不是策略审批。源文件为不可信项目证据；用户点击采用草稿后，目标与约束才成为该次用户确认的任务来源。平台底线保持独立。后续启动策略仍由 Pi 提议，经人工确认与执行域核验后生效。

## 接口合同

- POST `/api/agent-workspaces/{workspace_id}/scene-reads`：expected_manifest_hash 与可选 supplement；创建不可变读取作业。
- GET 同路径 `/{read_id}`：queued/running/completed/failed/interrupted；read_only=true，draft、draft_hash、实际读取证据及非敏感运行时事实。
- 完成草稿：name、goal、state=ready/needs_clarification、constraints、clarification、evidence。引用含 source_id、relative_path、sha256、精确 quote；引用必须出自该作业实际返回的读取片段。
- POST `/api/agent-workspaces/{workspace_id}/tasks`：read_id、draft_hash、expected_manifest_hash。服务端复核工作区、完整清单、来源实例代次、草稿 ready 与未使用状态；不接受同时覆盖 name/prompt。
- 内部 `/api/scene-reader/jobs/{read_id}/tools/{tool}`：独立短期作业凭据，仅访问绑定快照，不能调用管理员或任务执行接口。

同一 read_id 只可采用一次；任务、上下文、来源证据及采用关联在同一个数据库事务提交。采用前后新探测来源实例身份，冻结字节必须与已确认 manifest 一致。重新识别产生另一条读取作业；新逻辑任务仍独立 task_id，历史不按目录合并。

## 数据边界

读取和后续执行快照共同使用 registry.scan 的过滤和哈希清单，排除 .env、凭据、私有运行目录及保留评测来源（例如 RQ5 utils/evaluator.py 和 oracle/reference-policy 材料）。工作区是逐文件受控读取后冻结的内容，不宣称对原始目录提供文件系统事务快照。

模型约束先保存为 accepted_task_constraints、已确认任务文字及 workspace_scene_read 证据。declared_constraints 继续保留已有带权威角色、hash、对象绑定的结构，不能直接塞入字符串或把项目要求冒充平台要求。

原始提供方输出、模型私有推理、密钥与会话凭据不得持久化或公开。历史档案引用读取作业和公开草稿，不额外复制策略数据。
