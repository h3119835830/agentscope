# Agent 实例连接历史

状态：独立实现与回归通过，等待和并行策略语句 / DSL 修订统一部署验收。

Agent连接页增加“当前连接 / 连接历史”。历史按 instance_id 汇总，详情保留各次观测的实例代次、进程身份、工作区及会话标识，连接过程与关联任务在同一详情中查看；任务档案来源身份处提供回查入口。历史不承担实时授权或在线判断。

## 保存与接口

`workspace_connection_events` 是追加式元数据表，包含 instance_id、kind、name、event、status、previous_status、generation、occurred_at 和 snapshot_json；按 instance_id / id 建索引。表在已有工作区初始化中幂等创建，不迁移或删除任务、策略、凭据及执行记录。

独立 Observer 记录首次观测、状态变化、进程代次变化、工作区 / 会话变化、实例移除、任务绑定结束；人工检查每次保存。稳定的后台心跳按公开元数据去重，排除检查序号和观测时刻；比较与追加使用同一 SQLite 写事务。API 重启不依赖内存恢复历史，已结束实例从当前列表消失后仍能查询。绑定结束只表示控制面不再持有当前执行连接，不证明物理进程被杀死。

- `GET /api/workspace-connection-history?page=0&limit=12`：分页实例索引，包含首次 / 最近记录、事件数、关联任务数；limit 最大 50。
- `GET /api/workspace-connection-history/{instance_id}?before={id}&limit=30`：倒序事件分页和关联任务，limit 最大 100，游标必须属于该实例。
- 两接口沿用控制面鉴权，返回 `history_only=true, live=false`；只查询数据库，不调用 Broker、激活 Agent、加载策略或创建任务。

关联任务从冻结的 `bootstrap_contexts.workspace_source.agent_id / instance.generation` 读取；受管实例通过 managed:task_id 的固定绑定关联。不会用后来更新的工作区代次改写旧任务来源，也不复制另一份任务档案。

## 信息边界

只保存选定的实例名称和 ID、状态、PID、进程启动标识、代次、检查序号、观测 / 失效时刻、工作区 ID / 名称和会话 ID。排除凭据、原生会话内容、文件字节、模型私有推理、任意 Broker 响应及原始异常。控制接口失败记录“未知”，不得假定目标离线。保存失败不改变真实连接状态，后续检查重试。

从功能启用后的首次观测开始记录；不回填不存在的早期连接事件。任务来源可以关联到更早的已保存任务，来源代次如实保留。历史长期保留，本次不增加自动清理或恢复执行能力。
