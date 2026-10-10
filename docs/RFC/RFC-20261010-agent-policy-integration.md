# RFC：Agent 策略与系统模块第一批真实接入

日期：2026-10-10。实施分支：codex/agent-policy-integration-20261010；基线：90af640。

## 范围与职责

真实 React 页面承接独立 HTML 原型的信息结构。Agent 连接保持连接管理；会话作为其下一级入口。原策略工作台改为 Agent 页面，提供策略助手对话与 Agent 策略记录。历史策略库入口改为系统，包含系统策略、策略与模板、生成记录。保留既有生成、审核及历史策略记录入口，页面不新增服务与能力模块。

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

RQ1 模板只可导入受控 Agent，禁止导入系统层或其他实例。系统基础配置使用独立的 system 类型候选，只能进入系统 DSL 编辑器。以最新 GET 的文档列表追加，不覆盖已有文档；限制文档数、总 UTF-8 字节数和重复 ID。参数使用所选 Agent 的第一资源目录预填；切换目标后重置，并由用户核对具体路径。模板只保护填写路径，不自动扩展为所有工作区。

当前 ActPlane 词法器不支持字符串内嵌引号且保留反斜杠，参数拒绝引号、反斜杠、控制字符、相对路径及 `..`，不假设 JSON 转义等同于 DSL 转义。策略语句和上下文说明保留在候选文档 metadata；模板 ID 与 RQ1 UID 写入 DSL 注释，可随草案持久保存。

内容/说明/名称变动使预览失效；当前层文档哈希或版本变化禁止旧候选应用。服务端原有 CAS、目标快照、系统/Agent 版本、资源和运行代次检查继续作为最终权威。

已保存候选由现有 proposals 表持久化。DSL 编辑器未保存的改动刷新会丢失；助手中的模板候选及配置可在当前标签 sessionStorage 恢复，最多 12 条。它们是临时对话草稿，不是服务端已校验或已应用策略，不跨浏览器同步。

## RQ1 数据与能力边界

版本化收录原型已整理的 6 个候选，来自原始 607 条导出；保留 artifact commit、export SHA256、原文和行号、样例 DSL 及局限。没有将 721 条本地派生结果当成原始 607 条。历史 compiled 不继承到适配候选。

五个模板在隔离的实际解析/编译测试中通过。RQ1-CHECK 的 argv 预执行 block 不受当前运行时支持，必须保持 invalid；页面明确提示。notify 仅提醒，kill 是事后处置，uv 执行顺序不证明测试通过。

## 交付与后续

只更新 18003 的静态 UI，保留旧哈希资源，index 最后原子替换；不重启 API/Broker/Agent，不修改 18000/18004。策略助手使用现有历史生成服务产生真实候选；有 DSL 的结果可进入当前精确 Agent 的同一编辑器。现有结构化生成器仍要求经核验的任务执行环境，未绑定环境的结果为 requires_context；本次不绕过此合同。Agent 层的服务端环境适配、原生 Agent 会话接入、真实加载与内核探针仍需后续实施；策略应用保持人工确认。

## 记录界面重做（2026-10-10）

用户否定首版卡片目录与常驻表单。系统策略与“策略与模板”统一采用记录表：名称/编号、保护对象或匹配对象、操作、处置、类型/范围、状态、操作。配置在详情抽屉中进行，按适用对象、触发条件和匹配后反馈组织；右侧提供配置摘要，另有 DSL 预览页签。补充用途与能力边界折叠在补充说明中。列表搜索无结果时仍可编辑与恢复。

系统页收录原 HTML 的 P01、P02、P04 作为三个**未配置的基础配置项**，显示参考路径而非当前生效路径。配置后生成 SYS-ENV / SYS-SSH / SYS-POLICY 候选；保留当前文档，仅追加，不自动保存或应用。它们不是内核策略读取结果，也不意味着平台已经保护这些位置。六个 RQ1 模板继续属于第二层 Agent 策略，不能导入系统。

Agent 助手首页只保留目标选择、助手对话与输入区，模板目录归系统。聊天每个 Agent 单独存储于当前标签的 sessionStorage，最多保留 12 条生成指针或模板候选；后端持久保存不可变输入、生成批次及产物。切换 Agent 时组件和异步读取清理，迟到的创建结果只归原 Agent；不会跨目标显示或导入。这里是平台策略助手，不是所选 DSH/Hermes 的原生会话。

发送需求显式调用 POST `/api/history/inputs`，随后 POST `/api/history/generations`；进度与结果通过 GET 获取。目标 Agent 身份用于对话归属和后续 DSL 路由，不拼入自然语言策略原句，避免被模型误识别为待绑定参数。初始 self_contained 是输入标签，完整性复核仍可重分类。最近四轮用户需求作为可见上下文，最新补充优先；不传模型私有推理。

助手输出不携带审核或应用权限。缺少执行环境、没有 DSL、语义指导与编译结果分别展示。模型生成的 DSL 带入后仍须重新读取目标配置、保存校验、预览，再由用户确认。当前版本没有伪造任务上下文，也没有调用审核、确认或执行器接口。

## 客户界面与会话内候选（2026-10-10 最终修订）

模块名只在导航和面包屑展示。Agent/系统内部大标题、层级标签、模板目录重复标题及“查看生成说明”等内部诊断移除。任务历史位于侧栏导航最后。Agent 选择嵌入助手框，模板选择位于输入区；系统列表继续是字段明确的记录表。

助手可直接选择 RQ1 模板，填写参数后在同一对话中得到带结构化字段的候选，可重新选择或调整配置。这个过程不 POST。点击“检查并导入”才进入对应 Agent 的 DSL 编辑器；fresh GET、追加文档、显式保存校验和独立人工应用合同不变。后续自由描述生成可读取最近四轮用户需求及用户已配置候选的对象、操作、处置和反馈；候选明确标注尚未应用，不将其当成已验证环境。

原生会话详情提供“起草 Agent 策略”入口，目标来自 summary.instance / sessionInstance 的真实归属。这里起草的是该 Agent 全部会话共用的专属策略，不是只作用于当前单一会话的策略。未增加原生 DSH/Hermes 聊天嵌入或单会话策略应用接口。

配置详情采用双栏：左侧紧凑参数表单，右侧实时摘要；反馈、保护路径和启动程序匹配均可核对。生成按钮仅创建候选，客户主流程不展示 IR 阻塞码、原始 JSON、私有模型推理或生成内部 ID。

### source AGENT 与实际启动合同

ActPlane `crates/actplane-ifc-compiler/src/dsl/lower.rs:lower_exec` 将 exec 模式取 basename，再按 comm exact/prefix 匹配，不能将脚本路径当成解释器身份。`crates/actplane-cli/src/templates.rs` 明确提供 agent_exec 参数；原生 run/watch 还会为受保护根进程播种 AGENT 标签。

本系统 `backend/broker/instance_runner.py` 的受控 DSH 入口是 Node 脚本，Hermes dashboard 由 venv/bin/python 启动。当前真实 DSH runtime.executable 为 `/opt/agentscope/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js`，`/proc/54870/exe` 为 `/opt/agentscope/bin/node`。因此候选用 `source AGENT = exec "**/node"`，Hermes 用 `**/python`。页面同时展示对应 Agent 产品及已登记入口；未按产品名虚构 `**/dsh`。

系统候选从真实产品投影内的受控连接生成来源集合并按模式去重，可以同时声明 node 与 python。Agent 候选只采用当前精确实例的来源。未知启动器且缺少实际登记入口时拒绝构造来源，不回退为 `**`。本轮未改 Broker 基础 DSL、内核 matcher、标签隔离或启停合同。多个实例可以有相同程序名，实例隔离仍由受控 domain/cgroup 与目标配置的服务端合同承担；exec 字符串不证明独占身份。

新增候选已通过实际 AST/编译器校验。具体来源在新运行代次中的标签传播和实际拦截仍需用户确认应用后的独立执行验收，不能把本次编译或页面展示视为内核执行证明。新受控产品/启动器必须同步适配来源合同，不能按名称推测。

### 设计约定的持久化

新增 `agentscope-ui-design` skill；桌面副本为 `AgentScope-界面设计约定.md`，仓库副本为 `docs/design/agentscope-ui-design.md`。`frontend/AGENTS.md` 要求 UI 修改前读取该约定。用户明确授权后新增个人记忆更新 note，仅记录偏好及文档位置。后续用户直接指令优先。

系统与 Agent 页面均定期重新读取真实连接目录；系统页读取失败时显示重试提示并清空来源集合，禁止基于失败读取构造候选。
