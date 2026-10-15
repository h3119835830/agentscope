# 统一策略入口评审与验收

日期：2026-10-15。

## 代码结果

- AgentPolicyWorkbench 移除长期基线 / 工作区策略切换，改为全部受控 Agent / 指定 Agent 字段。
- 全部范围复用现有 SystemPolicyLibrary，指定范围复用 TemplatePolicyAssistant 与 ActPlanePolicies；记录表增加作用范围。
- 工作区改名为参考工作区，并明确浏览不改变作用范围、不会自动发送文件正文。
- 旧工作区链接进入 LegacyWorkspacePolicies 只读视图；不转换已有草案，不提供生成、提交、编辑或应用控制。
- 后端、Broker、ActPlane、普通业务代码和数据库合同均无修改。发布辅助脚本仅切换静态入口。

## 验证

前端 291 项测试通过，其中新增 7 项覆盖全局目标、精确实例切换、旧工作区不提升、原审批导航、工作区浏览无写接口和继承约束在本模块切换。Vite 生产构建通过，git diff --check 通过。

真实浏览器在只读 18154 预览核对了指定 Agent 助手、空策略表、全部范围 12 个预置 / 4 项已保存配置及范围列。方向键可切换页面标签。390px 视口下文档宽度 375px，范围列保留，860px 表格只在 287px 容器内部横向滚动。预览代理禁止 POST，未生成或提交正式候选。

测试编写过程中曾因 Node harness 的模块 filename 未赋值导致测试进程中止；已改为显式传入文件名，7 项及全套 291 项均通过。此问题只在测试夹具，没有调用运行服务或 Agent。

## 边界

本轮不新增全局模型生成，不新增工作区正文自动读取，不实现独立工作区执行域；这些能力不能从入口统一推导出来。历史工作区后台兼容接口仍存在，资格仍由服务端验证。

原系统入口保留，和 Agent 页全部范围共用数据与组件；没有产生第二套系统策略。策略应用仍由用户单独确认。

## 发布核对

已完成源码审核、本地提交与正式静态入口发布。代码提交 d6a2afe124211c0279bfbc193532c4dab0dc0f12；仅上传内容哈希命名资产，原子切换 index.html，保留全部旧资产和旧入口备份。

正式 HTTP 页面哈希为 a2f8d4629f62f0fa995cb02056ff75b649a9fb3bb841ec1009a8747a106a4a28，与构建一致。发布脚本核对 API/Broker 进程身份、全部受控 Agent 的 PID/generation/domain/active/策略、系统约束版本和 18000/18004 均保持不变；没有重启任何服务或启动/停止 Agent，没有应用策略。

正式 18003 页面已复核指定 Agent 助手和全部 Agent 配置库，截图与摘要位于 [evidence/unified-policy-scope-20261015](evidence/unified-policy-scope-20261015/validation.json)。静态发布私有回滚记录保留于 /var/lib/agentscope-scope-demo/release-backups/unified-policy-scope-20261015-164120/result.json。远端未推送。
