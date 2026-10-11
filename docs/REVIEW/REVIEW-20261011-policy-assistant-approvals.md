# 策略助手与审批入口评审验收

日期：2026-10-11。代码工作区：`/home/happy/projects/agentscope-agent-policy-20261010`；分支：`codex/agent-policy-integration-20261010`。

## 自动验收

- 前端 `node --test` 对 `src/**/*.test.mjs`：214 通过。覆盖只生成候选、提交只到 proposals、匹配待审批复用、跨 Agent 拒绝、详情查看无写入、失效候选无批准按钮、审批深链接、已校验草案恢复。
- 后端 `python -m pytest tests -q`，指定真实 ActPlane DSL adapter：945 通过、52 跳过。新增 5 项覆盖鉴权、隐藏实例过滤/404、运行环境变化撤销可批准状态、精确 scope/hash 拒绝、幂等与已应用拒绝保护。运行启停在测试夹具中替换，不将其作为真实加载验收。
- Vite 生产构建通过，109 模块；保留既有主包超过 500 KB 提示。

## 真实页面验收

18003 已发布。实测可执行 .env 候选：列表卡片、分组详情、冻结 source `**/node` 与 `/w/0/.env`、已生成策略表筛选、无结果搜索提示；提交复用原有待审批提案并进入审批详情。实测原截图中未完成候选：展示 `/w/1/.env` 与已识别操作，可查看/补充，不能提交。切换未运行 Hermes 后不显示 DSH 对话，生成禁用。

审批表显示 8 个可见记录，2 个待审批；查看审批、已处理分类、详情深链接刷新恢复通过。1280×720、900×720、650×720 检查无页面横向溢出，输入框和抽屉操作区可见。记录表在窄窗口内横向滚动。复原临时 viewport。

## 运行与策略保持

API 发布只重启 `agentscope-scope-demo-api.service`，1.227 秒就绪；静态文件按 assets 先、index 后替换。Broker、原生 Agent 未由本次操作启停。部署前后按 id 比较 Agent PID/generation/active/connected/status 相等；全部 DSL scope revision/document_hash/phase 相等；全部 12 个提案状态相等。DSH PID 54870 保持运行，2 个待审批仍待审批。

未在真实环境点击批准、拒绝或调用 confirm/review/apply；因此本次验收不声称新策略已加载或产生内核拦截。`18000` health 仍 200；`18004` 无监听，未操作该服务。源码验收、页面发布、策略运行状态分开记录。

截图：`evidence/agent-ui-approvals-20261011/`。没有远端推送。

## 审批来源定位修订验收（2026-10-11 17:18 后）

结论：真实 18003 已发布审批定位修订；未应用、拒绝或重新校验任何真实提案。

### 自动验证与源码基线

- 合入当前已发布系统策略基线 `12c7646` 后：后端全量 **1029 passed、11 skipped**，前端 **222 passed**；Vite 生产构建通过（112 模块），保留既有主包大小提示。新增覆盖已知产品隐藏测试别名、实时/历史 PID 区分、精确 Agent+session 关联、环境漂移保留来源、相同 session ID 不跨 Agent、证据哈希异常、会话记录缺失与只读导航搜索。
- 生成来源测试复用真实环境生成流水线并读取不可变 statement/artifact，模型与高权限运行由隔离夹具代替；不是实际策略加载验收。现有审批鉴权、scope/hash、过期阻断与拒绝保护测试继续通过。
- 首次基线整合回归因本工作树缺少新版 ActPlane 编译制品出现 32 项失败。将已发布且同版的真实编译器放入工作树忽略的构建目录，SHA256 `5e8d43c279d88bd4215f654746675debfd976e28426c9fabdabeca408865d6da`，完整重跑通过；没有修改断言、降级编译器或改动已安装引擎。

### 真实页面验证

- 两条需要处理的 Agent 提案均展示 **DeepSeek Harness / 当前 PID 615136**。自由描述候选关联 **Run native bash tests once / 会话 248b69ae**；详情展示 **提交时 PID 54870 / 生成时 PID 54870**，与当前 PID 分开。
- 点击生成会话，精确进入 `instance-1f4469579e8947f4` + `session-248b69ae-bc23-4fe4-8a43-0493d1412795`，真实页标题和当前 PID 一致。点击 Agent，打开同一连接的安全配置页签。查看/跳转不触发启动、生成或策略写接口。
- 旧模板提案没有保存原生会话绑定，列表和详情明确“未关联会话 · 此连接的全部会话”；不推测或伪造来源。系统提案仍展示完整实际影响对象，保持最新系统策略库的版本校验、移除配置摘要与加载回执语义。
- 按会话名筛选得到 1 条，按 PID 615136 得到 2 条；清空搜索恢复。配置与完整 DSL 两个页签均保留定位摘要。两条旧提案投影为需重新校验，没有批准按钮。浏览器 error/warn 记录为空。
- 1029×846（与用户截图宽度一致）：文档 scrollWidth 1029，表格 clientWidth/scrollWidth 均 759；两条查看按钮完全可见。650×846：表格改为带字段名的记录，clientWidth/scrollWidth 均 547，无横向溢出。临时 viewport 已复原。审批列表和详情的产品标题不含研究编号；后台接口、原生用户文本与真实路径保持原义。

### 发布、并行更新保护与状态保持

发布前预期旧 `/opt/agentscope-agent-sources-20261011`，实际服务已更新为 `/opt/agentscope-system-policy-20261011-161846`，部署断言在任何发布写入前阻止旧基线覆盖。核对并整合当前已提交系统功能；保留 policy_library.verify_proposal、系统全部目标与 application 回执，不回退新系统模块。

本次从上述当前 release 克隆 `/opt/agentscope-approval-locations-20261011`，只覆盖 approval_views.py、approval_locations.py 两个只读模块。仅重启 API，Broker PID **614944** 与 DSH PID **615136** / start_ticks 保持一致。该 PID 在本次发布前已经变化，不能将此前 54870 到 615136 的变化归因于本轮 UI 发布。

静态 UI 备份：`/var/lib/agentscope-scope-demo/ui-backups/agent-policy-20261011-171823`。发布后及浏览器验收后，逐表 SHA256 比较 agent_instances、instance_dsl_scopes、instance_dsl_proposals、system_security_policy、instance_local_policies、instance_proposals 全部相等；没有真实 confirm/reject/apply、没有重启 Broker 或 Agent。本轮不声称新策略加载或内核拦截验收。

证据：[审批列表](evidence/approval-location-20261011/list-1029.png)、[阶段 PID 详情](evidence/approval-location-20261011/detail-current-and-generation-pid.png)、[窄窗口](evidence/approval-location-20261011/list-650.png)、[校验清单](evidence/approval-location-20261011/acceptance.json)。镜像同步到用户技术文档根目录。没有远端推送。
