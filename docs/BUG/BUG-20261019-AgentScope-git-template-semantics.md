# BUG：Git 模板条件固定且详情缺少可执行参数（2026-10-19）

状态：修复，验收见 REVIEW-20261019-AgentScope-git-template-semantics.md。

复现：18003 /api/policy-templates 中 RQ1-GIT v2 parameters=[]，renderer 固定生成 reset/clean/stash/--no-verify 四个 token 规则；RQ1-CHECK 仅 target/checker，生成 after exec 而无 exits。进入模板详情不能配置 commit/push、检查退出码或正确理解实际支持能力。

根因：模板将实验预设当成通用 Git 策略；参数表由空定义渲染，且检查启动事件与成功结束事件未区分。

修复：新增 10 个有固定执行合同的专用模板（6 个有限支持、4 个暂不支持）；已支持参数实际写入 DSL。对暂不支持需求保存 document=null 参数草案，单项/批量/重新校验均由服务端拒绝，不靠禁用按钮保证安全。详情展示参数与能力边界，旧模板保持原版本。

验收：1408 项后端测试、352 项前端测试及构建；真实编译/审批/单独应用/停用链与负面参数测试；隔离真实 Git/BPF 13 项，检查成功放行，未检查/失败/再次写入终止；真实模型分别选中 commit/push。生产发布及浏览器证据见 REVIEW 与 evidence/git-templates-20261019。

限制：不宣称 Git 参数事前阻断、任意 Git 调用覆盖、测试与提交 SHA 一致性或完整企业 Git 治理已实现。
