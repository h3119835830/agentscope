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


## 记录界面与 Agent 助手修订验收

首版卡片目录虽通过工程测试，但用户否定其信息结构；不能把首版的工程通过当成界面认可。本轮按记录式布局重做。

| 验收项 | 结果 |
|---|---|
| 模板首页 | 6 条真实版本化模板记录，列出名称/编号、分类、匹配对象/操作、处置、适用范围、操作；无常驻配置表单 |
| 筛选 | 不匹配结果为 0；清空可恢复；“开发流程”筛选为 2 条 |
| 配置详情 | 基本信息、匹配条件、处置与反馈分区；配置/DSL 预览/适用条件页签；固定操作栏 |
| Agent 模板交接 | 默认取所选 Agent 的真实登记资源；重新 GET 后带入精确实例编辑器；未保存或应用 |
| 系统配置 | 原 HTML P01/P02/P04 三项未配置记录；修改参数后预览正确，候选进入系统编辑器；未保存或应用 |
| Agent 助手 | 单一对话框和发送区，没有模板目录；DSH/Hermes 切换时对话隔离 |
| 真实生成 | 两个实际批次返回候选；requires_context 准确显示为待配置执行范围，无伪造 DSL |
| 视口 | 571px 窄屏无整页横向溢出，表格内部可滚动；1280×720 助手发送区首屏可见、欢迎区无裁切或滚动 |
| 页面错误 | 独立真实页面标签 console error 为空 |
| 应用边界 | 未调用 confirm/review；系统与 Agent DSL 当前版本/哈希、受控 Agent PID/代次/gate/策略哈希、API 服务 PID/启动时间保持不变 |

验证结果：前端 198/198；后端 DSL 配置和事件读取 26/26（隔离 DB/执行器，实际 AST/编译器）；Vite 102 modules 构建通过。系统三项配置均在隔离环境编译为 pending，未应用。RQ1-CHECK 继续因当前运行时能力保持 invalid。构建有约 502 kB 主 JS 的体积提示，不影响构建通过；本次未扩展为打包性能改造。

部署仅复制前端静态文件，保留备份及旧哈希资源，最终资源为 `index-5W4KcMyX.js` / `index-BQlypGmi.css`。未重启 API、Broker、DSH 或 Hermes。修改范围为 AgentScope React、候选构造、隔离测试及文档，无普通业务代码。

真实助手结果的限制见 BUG：现有生成服务的结构化分支要求任务环境，Agent 层服务端适配仍待实施。本轮只验收真实候选展示、对话归属、模板到 DSL 的交接和人工确认边界，不声称自然语言助手已完成 Agent 环境适配或策略内核执行。

证据目录：[记录与配置验收](evidence/agent-policy-records-20261010/acceptance.json)。图片包括 template-records、template-configuration、agent-assistant 和 system-policies。验收生成批次保留，未最终审核、未加载；上一轮 `7df4ac16c8c5` 待应用草案保持原样。

## 客户界面与会话选策略修订验收（2026-10-10 最终批次）

用户继续否定上一轮模块大标题、层级标签、生成诊断和配置详情外观。本次工程验收仅证明下面的功能与显示事实，不代表用户已经认可视觉设计。

| 验收项 | 当前结果 |
|---|---|
| 导航与标题 | 任务历史位于最后；Agent/系统首屏无重复模块大标题或层级标签 |
| 助手目标 | 在对话头部选择真实受控 Agent；切到 Hermes 不显示 DSH 候选，切回恢复 |
| 会话内策略 | 输入区可选 6 条 RQ1 模板；参数配置后候选在对话中以保护对象、操作、处置、反馈展示，可调整和重选 |
| 精确交接 | 检查并导入进入 DSH 的精确实例编辑器，保护路径取登记资源，来源为 **/node；保留既有待应用草案 |
| 客户提示 | 去掉查看生成说明、IR/英文阻塞码及内部生成 ID；缺少上下文用补充执行范围的可操作提示 |
| 系统详情 | 表单与实时摘要双栏，提供保护路径、触发操作、反馈、启动程序来源及独立 DSL 预览；配置仍为候选 |
| 原生会话入口 | 实际 DSH 原生会话详情“起草 Agent 策略”跳转到其所属连接；不会新建或伪造原生会话 |
| 浏览器 | 1280×720，输入区 bottom=665，首屏可见，无页面横向溢出，无 console error |
| 应用与运行 | 本轮无 confirm/review、新 live proposal 或 generation；全部当前 scope、受控生命周期和 API 服务快照相同 |

最终自动验收：前端 204/204；后端 DSL 配置/事件读取 26/26（隔离 DB/执行器，真实 ActPlane AST/编译器）；Vite 103 modules 构建通过；新 skill 官方 quick_validate 通过。实际来源模式 node/python、系统多来源同标签声明已被真实解析器与编译器接受；未进行当前实例加载或内核拦截验收。主 JS 506 kB 体积提示保留。

最终静态资源：`index-DZw3GZjX.js` / `index-BJgrhIkW.css`，HTTP 返回字节与本地构建逐项一致。只复制静态文件；未重启 API/Broker/DSH/Hermes，未触及 18000/18004 或普通 ERP。运行快照比较通过，系统与全部 Agent 当前 DSL revision/hash/phase、PID/generation/gate/policy_hash 均保持一致。

自由描述到任意 Agent 策略的通用环境适配仍未完成；历史生成服务的 task-context 要求保留。当前对话内模板候选闭环与后续配置上下文已完成，不能把二者写成任意自然语言策略均可生成执行 DSL。此处是 Agent 层策略，作用于该 Agent 的全部会话；没有新增单会话策略应用。

已安装专用设计 skill，并保存桌面/仓库约定及用户授权的个人记忆更新 note。前端 AGENTS.md 链接约定；后续直接指令优先。代码与设计文档均仅本地提交，未推送。

证据：[结构化验收](evidence/agent-policy-customer-ui-20261010/acceptance.json)、[对话候选](evidence/agent-policy-customer-ui-20261010/agent-conversation.jpg)、[系统记录](evidence/agent-policy-customer-ui-20261010/system-records.jpg)、[系统配置](evidence/agent-policy-customer-ui-20261010/system-configuration.jpg)、[DSL 来源](evidence/agent-policy-customer-ui-20261010/system-dsl-sources.jpg)。独立验收标签保留新版系统配置详情供用户查看，原用户标签未被导航或清空。
