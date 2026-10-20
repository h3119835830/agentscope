# RFC：固定 Git 命令与模板 DSL 预览（2026-10-20）

## 合同

Git commit/push 的程序与动作属于模板固定事实，不能由手工或 Agent 填参改变。六个可执行 Git 模板发布 `git-fixed-command.v1` 新版本：从 parameters 移除 program，存储 fixed_fields.program=git 与固定 command；本地清理/跳过检查继续以受限 tokens 表达可变选择。dsl_clause_template 为服务端只读规则骨架，实际 materialize 使用该骨架生成规则，不是仅供界面说明的文本。

发布时从当前最后版本追加一个不可变版本（全新或本环境从 v2 追加 v3）；已有自定义版本也向后追加，不覆盖其名称、说明、可变参数默认值及历史定义。重复初始化不再追加。旧配置与审批仍绑定旧版本和哈希，不自动迁移/停用/加载。新建配置及助手不得降级到旧 Git 合同；编辑旧配置不得改其已保存 program，允许保持旧语义或显式升级。

## DSL 预览

新增管理员接口 `POST /api/policy-templates/{id}/preview`：输入 template_version、已声明 parameters、可选 effect/reason；拒绝额外固定字段、任意 DSL 或可执行器修改。返回 state、dsl、missing、errors、preview_only=true。complete 仅表示参数齐全，不表示已编译、批准、加载或生效；incomplete 显示双花括号参数位置，invalid 不生成看似可用的 DSL，unsupported 保持 dsl=null。

模板详情使用默认值与当前默认动作预览；新建/编辑子配置使用当前输入预览，不要求先保存。预览和实际保存共用 normalize_parameter/render_document，保存时仍核验目标、资源和全部必填参数；预览不访问 Broker、不启动程序、不保存配置/审批、不读取资料内容。未绑定执行目标的预览不代替提交时的资源验证。已有子配置另可展开已保存 DSL，不把未保存输入冒充历史版本。

所有可执行模板通过 public_definition 暴露默认 DSL 骨架/预览给界面与策略助手；旧模板定义哈希不因投影字段改变。新的 Git 模板把服务端固定命令、规则骨架和变量参数一起提供给 Agent；生成快照冻结固定命令。

## block

Git argv 在 exec 后观察，当前只允许 notify/kill；界面显示禁用的 block 和原因，服务端仍拒绝。kill 不是事前 block。整体禁止启动 Git 属于原有程序执行限制，不能自动扩大成整个 Git 的禁用来冒充仅禁止 commit/push。

## 安全与界面

规则占位符只经单次替换；文本参数 JSON 转义、整数与动作单独校验，参数正文不会被再次作为模板解析。类型、固定命令、DSL 骨架仍由服务端限定，模板版本编辑不接受这些执行字段。助手只选模板填参，不能自行输出/修改规则。保存、人工审批、单独应用及停用审批边界不变。

沿用主表、展开箭头、列宽与详情样式；固定命令只读展示，动作禁用原因占完整行，避免挤入单选框窄列。子配置表单采用满高 flex，正文独立滚动，保存栏固定可见。无 DSH、ActPlane、Broker 或原生工作区/会话改动。
