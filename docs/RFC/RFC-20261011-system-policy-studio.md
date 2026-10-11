# RFC：系统策略配置库与统一根层载入

2026-10-11。状态：正式实现与隔离验收通过，发布结果见 REVIEW。原静态预览保留作设计参考。

## 接口与职责
React 系统策略记录表负责编辑、筛选、勾选与差异预览。服务端负责配置版本、启动身份、编译、审批、加载及核验。系统固定作用于全部受控 Agent，含界面收起的受控项；专属策略追加当前 Agent 约束。原生 Agent 凭据不能访问人工配置接口。18003 保留原有本机控制台管理模式，本次不改变认证部署模式。

新增 GET /api/security/system/policy-library、POST 同路径、/{id}/versions、/{id}/archive、/proposals，及 GET /api/security/system/execution-capabilities。候选请求包含 selections(id, revision)、removals、base_hash、base_revision、request_key。服务端合并已应用文档与所选版本，再复用现有 DSL proposal、审批记录和 confirm 接口。

system_policy_library 保存当前配置，system_policy_library_versions 保存版本，system_policy_library_proposals 绑定候选版本。保存、勾选均不改变执行策略；编辑创建新版本；取消勾选不移除旧版本。停用单独预览并确认。已有 DSL 仅补入缺少的文档 ID，不覆盖库内编辑版本。不迁移预览 localStorage。

## 文档与继承
多规则逐条显示、完整文档应用；原文、来源、标签、前序依赖和变换完整保留。不能无损转换的文档保持 DSL 文本编辑。结构化配置的 AGENT 声明由 Broker 实际受控启动合同补全（DSH node、Hermes python），另由独立执行域限制目标。原始 DSL、合成加载 DSL、行号/规则/标签/子句映射分别保存。

文档命名空间由 scope 与 ID 生成；系统文档锁定。下层重名或 declassify 不能解除系统保护。确认前核对库内版本、系统/Agent 基准、所有目标、编译产物和执行能力。全部目标先编译，关闭执行门后逐个重载，仅恢复先前运行者；全部成功才解除更新状态。失败保存目标/阶段及逐项结果并暂停执行。停止目标启动时加载，新 Agent 首次启动也必须继承。重复确认回读同一次结果。

## 后缀能力
.env 后缀生成 **/*.env：匹配 .env、production.env，不匹配 .env.local；字面、大小写敏感。同名文件生成 **/.env；目录同时包含自身和内容。符号链接按实际内核对象解析。

来源、目标、例外及前序门控的文件模式字面量上限 63 字节，超限拒绝；contains 独立保留 16 字节上限。现代匹配缓冲 4096 字节，手工解析最多 32 层；无法可靠解析时失败保护。现有审计目标字段可能截断，不冒充完整路径。仅 procfs 的只读 mountinfo 在 pivot_root 后路径不可解析时保留沙箱引导兼容，不豁免普通同名文件。

后缀必须显式预留。root 所有且不可普通用户写入的能力清单绑定二进制 SHA256、内核版本、63 字节上限及实际运行验收；另读运行中的内核特性 map。旧版本缺少证据仍拒绝后缀规则。确认页说明重载执行器。block 拒绝操作；notify 记录并继续；kill 终止命中进程，不宣称事前阻断或反馈已送达。

12 类候选来自仓库 ActPlane/RQ1 与平台保护需求；未知实际目录留空，所有候选初始未配置、未选择。保留会话、策略助手、审批，不改 Pi。破坏性验收独立于 18003，使用 18143、独立 DB/socket/pin root 与合成子进程。
