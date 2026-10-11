# DSL 导入工具栏按钮错位

日期：2026-10-11。状态：已修复并通过真实页面验收。

## 复现与根因

18003 → Agent连接 → DeepSeek Harness → 配置 → 安全配置 → Agent策略 → 导入 DSL。“新增文档”与“导入 .dsl”上下错位。文件导入入口使用 label，位于 task-console 内，继承 `.task-console label` 的 20px 底部间距；其文件输入还继承 8px 顶部间距。文件选择区域与旁边的真实按钮因而不一致。连接页还没有向编辑器传入 scopeLabel，导致配置范围为空。

## 修复

导入入口改为原生 button，由 ref 打开 hidden 文件输入；保留 UTF-8 解码、50KB 限制和现有本地候选逻辑。所属文档选择框与两个动作按钮统一为 36px 高，并在 DSL 编辑器内限定样式优先级，避免修改全局表单。连接页传入当前连接的 agentName；scopeId 与应用合同不变。

## 验收

前端 215 项测试通过，Vite 构建成功。真实浏览器以 Enter 打开文件选择器并读取无敏感信息的本地 DSL 测试文件；新增文档、切换回导入文档后内容保留。1280px 和 650px 视口中选择框及两个按钮高度均为 36px，顶边一致。关闭后丢弃本地测试候选；未点击保存、校验、批准、拒绝或应用。

静态前端已部署到 18003，备份为 `/var/lib/agentscope-scope-demo/ui-backups/agent-policy-20261011-151602`。未重启 API、Broker 或 Agent。验收前后 Agent PID/generation/active/connected、DSL scope revision/hash/phase、proposal state 完全相同。

证据：`C:/Users/happy/Desktop/归纳梳理/技术文档/evidence/dsl-toolbar-20261011/` 中的 fixed-toolbar.png、narrow-toolbar.png、browser-acceptance.json、frontend-tests.log 和 runtime-invariance.json。
