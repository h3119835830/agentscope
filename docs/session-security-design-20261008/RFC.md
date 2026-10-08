# RFC：平台安全底线与会话权限清单

状态：设计提案；2026-10-08。

平台高权域维护通用规则版本，session 绑定批准的基线，场景 Agent 只提交场景规则与合法收紧提案。统一 UI 展示 OS、内容与语义约束，并明确执行方。详见本目录 README、policy-catalogue.json 与新增 HTML 原型。

配置合同应包含 template_id/version、origin/evidence、object/operation/condition、effect、reason、domain/source lineage、requested_by、批准、compile/support、加载/激活与验收回执。客户端只提交配置意图，可信服务完成路径/对象与仓库解析、能力检查、授权、编译、批准与加载；Agent 不可自行批准平台规则或扩权。

`compiled.ok` 不能取代 `backend_support.clauses[].supported/pre_op`。没有实时绑定、探针与反馈送达证据不能显示“已保护”。无法表达的 Git 分支区分配置保留为需求，不输出伪 DSL。通用语义约束统一展示，不伪装成内核支持。

基线更新创建新版本，默认作用于新会话；现有会话遵守继承单调性与合法迁移机制。普通进程继承域和显式子域创建分别展示。平台 D0 是否在真实部署中存在必须有绑定证据。

本轮只新增 docs 研究脚本、JSON、文档和离线 HTML，没有修改 backend、frontend 或 ActPlane 执行代码。没有生产接口、数据库或服务状态变更。
