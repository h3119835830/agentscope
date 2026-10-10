# RFC：Agent 策略与系统模块第一批真实接入

日期：2026-10-10。实施分支：codex/agent-policy-integration-20261010；基线：90af640。

## 范围与职责

真实 React 页面承接独立 HTML 原型的信息结构。Agent 连接保持连接管理；会话作为其下一级入口。原策略工作台改为 Agent 页面，提供策略助手（当前仅模板起草）和 Agent 策略。历史策略库入口改为系统，包含系统策略、策略与模板、生成记录。保留既有生成、审核及历史策略记录入口，页面不新增服务与能力模块。

系统策略由 `/api/security/system/dsl` 管理，作用于所有受控 Agent；第二层 Agent DSL 按受控连接的精确实例身份管理，作用于该 Agent 所有工作区和会话；会话仍读取实际场景/运行时策略，第一批不新增场景生成或运行时权限变更机制。

## 接口合同与流转

| 用户动作 | 调用与行为 |
|---|---|
| 进入 Agent/模板页 | GET `/api/console/agents`，读取真实连接，不生成演示 Agent |
| 读取系统/Agent DSL | GET `/api/console/security/system/dsl` 或 `/api/console/agents/{id}/dsl` |
| 模板带入 | 浏览器内构造候选；重新 GET 当前目标 DSL，再追加文档；不 POST |
| 保存并校验 | POST `/api/agent-instances/{id}/dsl/proposals`，提交 documents/base_hash/base_revision/request_key |
| 人工应用 | 独立的 POST `/api/agent-instances/{id}/dsl/proposals/{proposal}/confirm`，携带 proposal_hash；本次验收不调用 |
| 会话、策略域、系统调用、Trace | 原有精确实例+原生 session ID 路由，经 productReadUrl 读取真实投影 |
| 生成与审核 | 复用 HistoryLibrary、PolicyGeneration、StrategyRecords、ProductGenerationHistory，保留真实历史服务 |

GET 继续使用产品投影；写入仍走原受保护控制接口。未修改鉴权、Broker、Agent 启停或权限合同。当前本机配置为显式 loopback 开发免口令；本次没有改变其配置。

## 候选约束

模板只可导入受控 Agent，禁止导入系统层或其他实例。以最新 GET 的文档列表追加，不覆盖已有文档；限制文档数、总 UTF-8 字节数和重复 ID。参数使用所选 Agent 的第一资源目录预填；切换目标后重置，并由用户核对具体路径。模板只保护填写路径，不自动扩展为所有工作区。

当前 ActPlane 词法器不支持字符串内嵌引号且保留反斜杠，参数拒绝引号、反斜杠、控制字符、相对路径及 `..`，不假设 JSON 转义等同于 DSL 转义。策略语句和上下文说明保留在候选文档 metadata；模板 ID 与 RQ1 UID 写入 DSL 注释，可随草案持久保存。

内容/说明/名称变动使预览失效；当前层文档哈希或版本变化禁止旧候选应用。服务端原有 CAS、目标快照、系统/Agent 版本、资源和运行代次检查继续作为最终权威。

已保存候选由现有 proposals 表持久化；未点击保存的编辑内容为临时状态，刷新会丢失。没有引入浏览器长期保存原始 DSL。

## RQ1 数据与能力边界

版本化收录原型已整理的 6 个候选，来自原始 607 条导出；保留 artifact commit、export SHA256、原文和行号、样例 DSL 及局限。没有将 721 条本地派生结果当成原始 607 条。历史 compiled 不继承到适配候选。

五个模板在隔离的实际解析/编译测试中通过。RQ1-CHECK 的 argv 预执行 block 不受当前运行时支持，必须保持 invalid；页面明确提示。notify 仅提醒，kill 是事后处置，uv 执行顺序不证明测试通过。

## 交付与后续

只更新 18003 的静态 UI，保留旧哈希资源，index 最后原子替换；不重启 API/Broker/Agent，不修改 18000/18004。Agent 自然语言策略助手接入、生成结果到 Agent 的新交接入口、真实加载与内核探针属于后续工作；策略应用保持人工确认。
