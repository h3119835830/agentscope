# 模板版本编辑与子配置独立入口合同（2026-10-16）

按用户确认，仅修正模板 / 子配置职责：移除主表触发操作值列；箭头展开子配置，“详情”编辑模板。模板可编辑名称、说明、配置项名称 / 默认值和默认动作。参数键与类型仍由执行器限定，不支持增删或更换类型，界面说明该边界。其余导航、列宽调整、子表独立滚动及审批流程沿用原实现。

新增管理员 POST /api/policy-templates/{id}/versions，输入 name、description、effect、parameters[{key,label,default}]、base_version、request_key。服务端固定既有 renderer、system_preset、scopes、allowed_operations、参数键 / 类型，验证默认值。数据库 policy_template_versions 以 (template_id,version) 为不可变主键、request_key 唯一；事务内核对当前版本，冲突返回 409，同请求同内容重试返回同一版本。

GET /api/policy-templates 提供最新已保存模板。public_catalog 与策略 Agent 共用最新目录；生成过程中目录变化使材料基线失效，重新分析。get(id,version) 精确解析静态 v1/v2 或数据库 v3+，旧模板定义、已保存子配置 / 候选继续引用旧版本，不迁移、不自动审批 / 加载。description 单独作为选择元数据提供。模板的默认动作需被所有既有 renderer 使用；旧定义默认值对应的生成行为保持原状，不能仅修改展示字段。

保存模板只影响后续起草依据；实际策略仍保存独立子配置，提交审批、人工批准后另行应用。此次不改 DSH、原生工作区 / 会话或 Broker。模板执行类型、任意 DSL、额外参数与作用范围不可通过编辑接口写入。
