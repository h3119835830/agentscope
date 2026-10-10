# RFC：ActPlane DSL 配置与独立会话模块

状态：实施；验收证据见同日 REVIEW。范围为独立 18003 控制台。

## 职责与导航

导航顺序为总览、Agent连接、会话、策略工作台及既有模块。会话为同级入口，连接配置中的“查看会话”跳转到目录并保留连接筛选。会话与进程旧页不再维护第二套目录，连接历史和独立实例进程页不恢复。

用户 DSL 与旧资源挂载／工具准入策略独立保存。系统 DSL 由所有受控连接继承；连接专属 DSL 以具体 connection instance ID 为归属，覆盖其所有工作区与原生会话。上下文需求 self_contained/project/task 为规则说明字段，与来源 system/agent/session 分开。project/task 必须有人工提供的具体上下文依据；本期不提供 AI 上下文推断器，未解决的模板占位符不能应用。

## 原文、编译与继承

原始文档按 UTF-8 精确保留；多 rule 文档保存为一个编辑单元，每 rule 对应一条列表记录。原始语句保留在 metadata，缺失时以完整目标、条件、动作生成确定性的 DSL 摘要。当前旧加载材料可只读展示，未保存的用户原文标为“未记录”。

backend/dsl-adapter 是调用既有 actplane-ifc-compiler AST 的 Rust 集成工具，没有第二套 DSL 语法。原文中的标签、变换、条件、前序门控、进程谱系和子句均由真实解析器处理。每个归属／文档分配不同命名空间；禁止引用文档外标签。文件目标按受控连接的资源映射为 /w/N。系统规则及平台禁止发布规则带 locked 来源标记。用户命名和 declassify/endorse 不能改变继承层的标签或固定边界。

Broker 将旧执行边界与所有继承 DSL 合成，调用真实 ActPlane 编译器。应用要求 ok、来源与子句受支持、编译子句与 source_ref/compiled_name/clause_hash 可核对。展示原始单条 DSL、完整原始文档、实际编译规则与完整加载包时分别标注；加载包不冒充单条原文。

静态 backend support 不是当前受控引擎的全部能力。此运行配置使用 ActPlane pinned engine，full_profile 不包含文件路径 contains/suffix 特性。适配器检查真实编译产物的 taint_config ABI（当前 320 updates、128 rules），从 lowered update/rule/target exception 提取匹配需求；Broker 在保存候选时拒绝不支持的特性。ABI 长度或计数变化即拒绝，不能退化为源文本正则猜测。明确资源路径及路径前缀仍可应用；exec basename 匹配不误判为文件 suffix。此限制不修改 ActPlane 子树。

事件分类保留各子句的 per_event/cross_event。前序门控、谱系条件、文件／endpoint 标签、标签变换以及特定 exec 来源对后代子树的标签依赖均为跨事件；无谱系筛选的 wildcard executor 身份可为单事件。

## 接口合同

- GET /api/security/system/dsl；GET /api/agent-instances/{id}/dsl。
- POST 相应 /dsl/proposals：documents、base_hash、base_revision、request_key。保存草案并按实际目标连接编译。无目标连接的非空系统候选保存为不可应用草案。
- POST 相应 /dsl/proposals/{proposal}/confirm：proposal_hash。用户明确确认后应用，原生 Agent 凭据不能调用这些控制接口。
- GET /api/sessions：产品、连接、名称／原生 ID、cursor、limit。
- GET /api/agent-instances/{id}/sessions/{native_id}/policies、domains、kernel-events、tool-traces；可指定 generation，事件使用 before 游标。

候选冻结原始文档、基准版本、资源、连接、运行代次、执行门和继承版本。确认先核对基准及影响范围，再重新编译比较包 hash。所有受影响门关闭、等待既有 lease、停止旧执行器后提交新修订，仅恢复修改前正在运行且已核验的连接。保存、编译、确认、加载、当前运行核验分别记录；任何停止／加载／核验失败均暂停受影响执行并将该配置范围标为 blocked。重新校验确认可恢复，原来停止的连接不自动启动。

Agent 范围的 blocked 仅关闭自身连接的启动与 lease，不波及其他连接；system 范围的 blocked 才阻断全部受控连接。UI 将部分连接已核验、未运行待加载与失败暂停分别呈现。

## 会话及证据

原生会话身份为 connection ID + native session ID。工作区仅采用可信原生映射，并核对注册资源；无工作区能力时不补造路径。活动状态和 PID 来自适配器，断连缓存不保留活动 PID。策略域页将配置继承链与真实 ActPlane 域分开；共享执行器明确标示，不制造独立会话域。

Broker 固定读取自身受保护目录的 root-owned、不可组／其他写入的普通 NDJSON 文件，拒绝符号链接，以文件身份和字节游标增量读取。每个运行代次使用独立的 control/{generation} 目录，从该新文件偏移 0 开始，按真实进程域筛选；ActPlane 启动时重置反馈文件不能覆盖旧代次原始日志。API 以 connection/generation/source offset 去重持久保存。命中关联需要保存的 generation、包 hash、进程域和编译 source_ref/clause_hash/effect/target 同时匹配。内核 rule ID 可以因父域预留而偏移，保留运行 ID 与编译 ID，两者不强行相等。

会话四页为策略详情、策略域、系统调用匹配、工具拦截 Trace。匹配源没有 syscall 名时展示真实 op。原生工具没有可信内核标签时，共享 PID 事件标为“共享执行器事件，未归属会话”，禁止按 PID／名称／时间邻近拼接。工具准入拒绝不生成内核事件。反馈没有送达回执时不能显示“已送达”。notify 的 report 与 block、kill 分别展示，kill 不宣称事前阻断。

本期不替换 Pi 界面，不实现统一审批中心和历史库复用；保留手动确认应用。现有任务绑定仅在可信 instance/generation/native session/task/domain 映射存在时投影，缺失映射时不补造会话策略。

## 生产界面修订：Agent、工作区、会话

会话目录以 Agent 产品、当前进程 PID、原生工作区和会话组织。已知产品统一使用产品名，DSH 显示 DeepSeek Harness；不展示旧登记名称中的测试别名或内部 instance ID。目录增加 workspace 精确筛选，工作区选项来自已读取的原生会话资源，在名称搜索和分页之前汇总；无可信工作区时不显示字段。产品只有一个可选 Agent 时省略进程筛选。未连接的安装／发现占位项不进入会话目录，受控 Agent 的已保存会话继续可读。

GET /api/sessions 新增可选 workspace（最长 4096 字符），返回 workspaces。connections 增加当前 pid 和 resources，records 增加 agent_pid；策略详情也返回 agent_pid。agent_pid 仅在对应 Agent 当前 connected 且 PID 为正整数时返回，停止后为 null。它表示会话所属 Agent 的进程，不改变会话已保存／活动状态，也不伪造该会话正在执行。

详情按原生会话名、Agent 产品与 PID、原生工作区展示。移除运行代次选择及普通字段；控制台始终读取当前 Agent 运行上下文，旧 URL 的 sessionGeneration 参数忽略并在 URL 规范化时删除。底层 generation、稳定连接 ID、版本、域及来源校验继续保留，后端既有历史读取合同不删。四个详情页、DSL 原文及真实命中保持原语义。
