# REVIEW：策略助手按已有模板填参的可行性

日期：2026-10-14。最初结论为只读调研；用户已进一步授权实施。实现与正式发布核验补充见下节。

## 最初只读核对

- 现有浏览器 18003 的“系统 → 策略与模板”显示 6 条记录，已打开敏感配置访问限制详情并返回原列表；无保存、提交或应用。
- systemd ExecStart/WorkingDirectory 指向 `/opt/agentscope-session-security-20261014-180615`，只读分析部署后端，不把研究工作树当作完整部署版本。
- 部署系统预设 12 项；Agent 页面 6 项，存在重合，尚未构成统一模板合同。
- 部署 `policy_library.structured/save` 允许经校验的结构化配置，也支持管理员 DSL；template_id 并非绑定不可变规则语义的充分条件。助手不能直接复用管理员通用写接口作为自身授权。
- `history/pipeline.generate_ir_artifact`、`generations.compile_candidate` 仍沿意图到 IR/规则的生成链，不是仅接受已发布模板 ID/版本及参数。
- 工作区/单会话独立加载仍受后端阻止；文件读取/变更访问组、notify/block/kill 和参数门控有明确能力限制。
- 核对系统配置库 RFC 与审批 ADR，继续保持保存/生成、审批、显式应用、实际运行核验的区分。

## 风险与整改建议

新增受信任模板注册表、严格参数校验、服务器目标绑定和确定性规则生成；模型只负责模板选择与填参。手工/助手共用配置记录和审批状态机。助手越权字段、未知模板、改变上层约束或以整 Agent 代替局部范围均拒绝。

既有模板须先对齐真实运行合同。尤其不能将 unlink 别名描述为独立“只禁删除”，不能将某程序出现等同于测试通过，不能将网络连接审计描述为完整流量审计，不能把参考源码钩子存在当作所有当前 Agent 的运行证据。

已形成 [RFC 提案](../RFC/RFC-20261014-AgentScope-template-bound-policy-agent.md)，含统一合同、权限、界面映射、12 类拟收集场景、能力边界和隔离验收要求。未新建已采纳 ADR；本轮未执行可重现故障修复，不新增已关闭 BUG。

## 最初只读验证范围

文档内模板数量与当前目录/页面一致；文件引用及状态描述复核。未修改应用代码、数据库、Agent、策略或服务；未执行新的生成请求、编译、AI 任务、发布、提交或远端推送。后续实现验收须使用隔离实例，当前文档不是功能已完成或强制执行通过的证明。

## 后续实施与隔离验收

实现基于当前部署对应的 `ffe88eb` 创建隔离工作树 `/home/happy/projects/agentscope-template-configurations-20261014`，未覆盖其他分支或已有修改。新增模板参数 API、版本化子配置、模板父记录展开、共用手工表单与助手参数计划。目录含 15 个 Agent/工作区模板与 12 个系统预设合同。保留现有系统库和历史草案，不自动迁移、批准或应用。

真实模型在独立 18153、独立临时数据库、不可用 Broker socket、合成项目中生成两条“禁止删除/禁止修改”子配置，选择相同静态模板并分别保留操作意图；最新验证用时 1.444 秒（单次样本，不是性能保证）。重试返回相同配置 ID；手工对照使用同一参数合同。两个子配置都明确显示共享访问组实际影响，均未批准或应用，隔离 Agent 保持停止。

后端 118 项回归通过，覆盖真实 ActPlane AST/编译器、模板白名单、参数与路径、越界/符号链接、原生凭据拒绝、原子保存、版本失效、精确目标、显式提交、停用与其他配置保留、重新校验来源绑定。前端全量 284 项测试通过，构建通过。最初隔离材料放于 `/tmp` 时被现有资源登记合同拒绝，之后将合成项目移至允许的 `/home/happy/projects`，没有放宽路径校验或修改 Agent 提示词。

证据：[真实模型与 API](evidence/template-configurations-20261014/real-provider-api.json)、[验证汇总](evidence/template-configurations-20261014/validation.json)、[隔离页面](evidence/template-configurations-20261014/template-children-preview.png)。本轮实际内核引擎与 ABI 未改动，未把编译或界面当成新增内核操作隔离的实证。

真实模型最初在同语义的开发契约预设与通用文件变更模板间选择了专用预设。排查确认是目录重复和缺少基础模板引用，不是 Agent 能力问题；现将专用预设映射到通用模板，助手只看去重后的可选目录，手工入口保留专用预设。不新增员工文件等场景专用提示词。[目录复核](evidence/template-configurations-20261014/real-provider-alias-review.json)。

## 正式发布核验

正式发布通过，时间 2026-10-14T21:30:05.225915+08:00。运行版本 `fddc532aa8cabfeb41b8d6a09793a74529c51836`，API PID 150030，目录 `/opt/agentscope-template-configurations-20261014-212944`。API 切换用时 1.44 秒；Broker 身份、既有 Agent 的 generation/PID/domain/策略及系统基准完全一致，18000/18004 未变。没有启停 Agent、恢复权限、批准或应用策略。

Windows 的 127.0.0.1 健康接口 HTTP 200，读取用时约 0.005 秒；HTTP 入口 SHA-256 与发布目录一致。正式页面显示 27 个模板、4 项已有系统配置的只读子记录；新正式子配置数量为零，没有把隔离模型验收结果写进正式库。浏览器已刷新至新界面，保留全部模板目录。界面新增没有改动原安全总览。

[发布结果](evidence/template-configurations-20261014/production-release.json)、[正式页面](evidence/template-configurations-20261014/production-template-children.png)。代码与文档已本地提交，未推送 GitHub。
