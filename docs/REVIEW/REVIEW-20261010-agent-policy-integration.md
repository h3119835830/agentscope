# REVIEW：Agent 策略第一批验收

日期：2026-10-10。范围：真实页面、真实数据读取、RQ1 模板到指定 Agent 的 DSL 候选联动；用户保留策略应用确认权。

## 分支与交付

核对并 fetch 后，main、WINDOWS、origin/main、origin/WINDOWS 与现有系统源码基线均为 90af640；无需重复推送。第一批在隔离的 codex/agent-policy-integration-20261010 开发。18003 静态 UI 已更新；原系统运行后端文件逐项与基线一致。没有合并静态原型的演示数据。

## 自动验收

- 前端 `node --test src/*.test.mjs`：193 passed。包括候选目标隔离、保留已有文档、重复 ID/大小限制、真实 DSL 编辑器显式校验与确认分离、编辑失效、资源预填和旧 URL 兼容。
- 后端 `test_dsl_configuration.py` + `test_dsl_event_reader.py`：23 passed。复用实际 ActPlane AST 与编译器，测试 DB/特权 IO 隔离。新增六模板校验：5 pending，RQ1-CHECK 按预期 invalid，当前 DSL 未写入，未启动/停止实例。
- `npm run build`：通过；95 modules。现有 FastAPI/Starlette 弃用告警保留，不影响本次断言。

## 本机真实浏览器验收

使用 computer-use/cua_repl 操作 18003 的真实 HTTP 页面；没有绕过原型 file URL 的浏览器限制。

1. Agent 页面读取实际 DSH 与 Hermes，产品名称显示，精确实例身份保留于路由。
2. DSH 模板带入后打开正确目标编辑器，追加候选；初始没有应用操作。
3. 点击保存并校验调用真实 Broker 编译，返回 pending，预览只有目标 DSH 连接；未点击确认应用。
4. 修改名称后确认按钮立即禁用；关闭再刷新可见已保存草案。
5. 系统模板库选择 Hermes，进入 Hermes 编辑器；只预填，没有保存/应用该候选。
6. 系统策略读取实际空文档状态；生成记录实际为空，没有伪造示例。原生成/审核入口保留。
7. 会话位于 Agent 连接下；产品筛选、原生会话 ID、查看策略详情正常；工作区与实例进程筛选移除。
8. Hermes 会话映射不可用时显示数量未知；筛选器仍保留，能切回 DSH。
9. 会话策略域展示系统→Agent→会话；系统调用匹配和工具 Trace 读取实际接口。所选会话暂无对应记录，页面如实显示，没有制造拦截证据。

## 未应用证明

脚本 `scripts/agent_policy_runtime_snapshot.py` 对比交付/真实编译前后的受控 Agent PID、generation、gate、policy_hash、connected、active，以及全部已配置 DSL revision/document_hash/phase 和 API service MainPID/进入时间：一致。仅新增 1 条未应用的 DSH 验收草案；未写入当前系统/Agent DSL，未调用确认接口。该验收候选使用 `/workspace/.env` 的示例路径，只用于联动校验，正式使用应核对真实路径。

部署脚本 `scripts/deploy_agent_policy_ui.py` 只更新静态资源，备份原目录并保留旧哈希文件。不操作 Broker、原生 Agent，也不触碰 18000/18004 或普通 ERP 业务。

## 风险与保留项

自然语言助手尚未接入，当前是模板起草。RQ1-CHECK 的预执行 argv block 不被当前运行时支持。系统策略与 Agent 策略当前未配置用户 DSL，不应将空表解释为全部既有权限约束都不存在。历史加载/编译或继承保护状态不是新候选已执行的证明；本次没有真实加载新策略或运行内核探针。

技术文档同步到用户指定的归纳梳理目录。提交前检查完整 diff，无普通业务代码改动；仅本地提交，第一批新改动尚未推送远端。

## 验收材料

- [Agent 真实页面](evidence/agent-policy-20261010/agent-workbench.jpg)
- [系统模板真实页面](evidence/agent-policy-20261010/system-templates.jpg)
- [结构化验收结果与静态资源哈希](evidence/agent-policy-20261010/acceptance.json)

最终浏览器日志无 console error；快速切换模板后参数即时采用对应模板与目标 Agent 的路径，避免上一模板参数短暂混入。
