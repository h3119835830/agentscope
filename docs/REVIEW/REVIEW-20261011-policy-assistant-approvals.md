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
