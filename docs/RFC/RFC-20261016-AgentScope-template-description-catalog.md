# 模板目录字段与共享 description 合同（2026-10-16）

主列表展示模板名称 / 分类、说明、配置项、默认动作、触发操作、子配置数量、详情与新增入口。默认动作和触发操作独立成列。模板并非一个已加载配置，故主列表不使用实例策略的名称、实际范围或应用状态字段。名称前的展开箭头和详情入口控制同一展开状态，展开后直接展示独立表头的子配置记录，不再追加模板说明或参数定义区。

GET /api/policy-templates 的 catalog 每项增加 description。内容由服务器 template_descriptions.json 维护，目前覆盖全部 27 个已发布模板，包含适用场景、参数含义及重要能力边界。目录说明列、配置编辑摘要与策略助手输入复用同一份描述；说明可被搜索。

description 为选择元数据，public_catalog 导出时合并，不写入 get(id,version) 返回的已发布执行定义，因此不改变既存 template_hash。生成基线包含公开目录，生成期间描述变化仍会触发重新分析；已保存配置 / 审批的执行定义不因文案变化失效。

现有策略助手通过目录读取模板合同，将选定的 template_id、template_version、实际名称、parameters、reason 作为结构化配置计划交给服务端验证并保存。外部 Agent 若封装配置工具，仍调用现有 GET /api/policy-templates 和 POST /api/policy-template-configurations 管理端接口；后者只保存草案。未新增凭据、外部工具权限、原生 DSH 工具或绕过审批的接口。系统及指定 Agent 范围仍由原服务端校验。

同日后续更正：主表删除触发操作值，详情改为模板版本编辑，箭头单独展开子配置。旧说明中详情与箭头同步、操作值列的展示约定已被用户新要求取代，最新合同见 RFC / ADR-20261016-AgentScope-template-version-editor.md。
