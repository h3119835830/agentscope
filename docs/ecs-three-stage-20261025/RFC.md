# RFC：ECS AgentScope 三阶段策略与审计闭环

日期：2026-10-25。范围：AgentScope、原生 DSH 专用桥接、经单独授权的 ActPlane 最小兼容补丁。不涉及普通业务代码。

## 职责与流程

运行前：固定读取进程按已登记工作区浏览目录、读取正文。Pi 自主选择资料、检索模板并调用类型化草案工具。参数通过原有模板与路径校验后保存候选。人工批准与应用是两个独立动作。

运行时：原生 DSH `tools/execute` 串行化顶层调用。Broker 核验运行代次、cgroup、真实进程及 ActPlane domain，在现有 `audit_call` map 写入调用标记，准入后才执行。子进程继承标记，结果回执完成时清除根进程标记。

内核事件必须同时匹配运行代次、domain、调用标记、策略 bundle、source_ref 与 clause_hash。时间接近、模型描述或工具 succeeded 都不作为内核拦截证据。缺少可信标记的事件保留为共享执行域未归属事件。

与真实拒绝关联的 tool_result 触发运行时 Pi。Pi 可以起草限制，不能审批、应用、执行或扩权。`turn/end` 且无未完成准入调用时，触发运行后审计。审计仅可读取冻结证据 ID，发现只能引用实际读取的记录。人工标记以追加记录保存，不改原证据和模型结果。

## 接口与存储

- `GET /api/policy-template-tools`：名称、说明、参数 JSON Schema、模板版本、适用操作及阶段。`draft_*` 仅返回校验后的草案。
- `/api/policy-lifecycle/{instance}`：已认证的配置、按会话查询、同一输入摘要重试和追加复核。
- `instance_lifecycle_configs`：场景要求、读取基线、资源摘要和启用后的事件游标。
- `instance_policy_jobs`：冻结 input_json/input_hash、触发事件、阶段和执行状态；实例与事件键去重。
- `instance_audit_reviews`：追加复核，另写操作审计日志。
- 原生 `/scope` 现返回与会话 UI 相同的新鲜加载投影，基础写入授权不再遮蔽已加载 DSL 约束。未验证的历史回执不展示为当前已加载。

## 安全边界

API 与参考读取进程使用不同 UID。root 启动器只负责固定读取子进程和降权，运行中的 API/reader 无有效能力，NoNewPrivs 开启。不为 API 放宽场景目录权限。

Pi 固定为 1.0.1，以短时回调凭据调用受限工具。无项目目录、业务数据库、shell、审批或内核控制工具，使用独立临时 home 和空 `/proc`。凭据只从专用服务器文件读取，正文、私有推理和 provider 流不进入技术文档。

## 真实能力与限制

只采集策略命中，不是全量系统调用。原生工具回执不复制命令正文和原始输出，审计不能据此证明具体 payload 语义。文件摘要是两点比较，不是连续完整性监控。turn_end 表示 Agent 轮次结束，不保证所有脱离等待的后代进程已经退出。

当前 ActPlane 每台主机只允许一个事件监视器。隔离验收期间暂停原受控实例，结束后恢复原策略，不绕过 singleton。模型相关性选择仍可能给出多余候选，必须人工核对，不得因模型置信度直接应用。

## Jev

[TypeSafe 官方说明](https://typesafe.ai/)将 Jev 定位为带置信度的类型化决策模型。适合用作模板相关性、风险分类和复核分流。可采用“决策模型选择候选 → 通用模型填写参数 → 服务端验证 → 人工审批”的模型无关接口。此项为设计建议，本次没有 Jev 凭据或实际调用结果；实测使用 DeepSeek。

验收入口：`acceptance/evidence/three-stage-20261025/result.json` 与同目录页面截图。代码映射见 REVIEW。
