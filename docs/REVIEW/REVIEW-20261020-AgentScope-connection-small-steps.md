# 连接小步修复与分支核对

## 第一项：已有连接紧凑布局

基线：main `0d526d2`；18003 JavaScript 仍为 `b37b4fd` 发布物。功能源文件仅 `frontend/src/agentInstances.css`，新增 9 行限定样式，编译后新增 1021 字节；移除这一段后与线上 CSS 逐字节相同。

验收：

| 项目 | 结果 |
|---|---|
| 前端测试 | 388/388 |
| Vite 构建 | 通过 |
| CSS-only 发布防串包测试 | 5/5 |
| 1280px | 打开方式与网页入口同排，无横向溢出 |
| 600px | 单列，无横向溢出 |
| 添加连接、资源页签、关闭/Esc | 正常；未保存或启动 |
| 生产 JS 兼容 | 预览使用 `main-DImLISr8.js`，只替换 CSS |
| 浏览器错误 | 未观察到 console error |

证据位于指定技术文档目录 `REVIEW/evidence/connection-compact-20261020/`。发布脚本校验线上 index 哈希、CSS 哈希、准确插入、干净 main、API/Broker 身份、策略及引擎不变。保留旧资源及 index 备份，不重启。

发布结果：`f7d62f0` 于 2026-10-20 18:27:17 单独更新 18003，主服务浏览器复验通过。index SHA-256 为 `8492be382a29697404fb0c50fdaa150c1819a30756efb6017762e6d1d7e72e7f`；JS 仍为 `main-DImLISr8.js`。发布脚本核对 API/Broker 进程身份、引擎、策略及其他静态资源均不变。

## 第二项：保留打开，恢复须确认

- 改动仅连接展示、打开 helper、确认交互和对应提示文字。不新增配置入口或技术字段。
- 列表与抽屉的未知受控连接显示“打开”，只查询当前入口；失败后检查准确目标，提供有中断影响说明的重启确认。
- 取消/Esc、请求失败、身份变化、弹窗被阻止、非法地址等不触发启动；确认时同一实例已恢复则只打开现有入口。后端合同不改，前端检查不宣称服务端原子 CAS。
- main 400/400 前端测试与构建通过；线上基线加本次六文件覆盖的精确发布包 382/382 原有测试与构建通过。
- 浏览器：列表打开 → `/open` 409 → `/check` 200 → 确认；取消；抽屉打开 → 同一确认；600px 对话框宽 470px、无横向溢出；Esc 取消。不点击确认重启，不发送 start/stop/配置/策略写入。实际成功启动链路由隔离单元测试验证，不声称主服务重新启动验收。
- 发布不使用 main 的完整 build。每个文件核对生产基线或六文件 allowlist，保留 `0d526d2` 未发布；本地 `ProductOverview.jsx`、`productConsole.test.mjs`、设计规范的并行修改未纳入本提交/包。
- 当前：第二项已独立发布，见下方结果。

### 并行发布保护检查

打开入口提交 `a476533` 后，第一次发布被 index 哈希检查阻止，尚未写入线上资源。另一项工作已把线上 JS 改为 `main-CUSNOPOG.js`（总览恢复 SecurityNotice）。

只读核对该发布源码相对 b37b4fd 仅改变 `ProductOverview.jsx`；在我方临时目录独立重建，JS SHA-256 与线上 `4c6cd0cbb36b0b378c3da3bac304bba8a731475aed1716aabceccdca4a44a7ad` 完全相同。新版发布包保留此已上线文件的固定 SHA-256，不提交它的并行源码改动，再覆盖本次连接六文件。不会将已有线上功能退回，也不复制整个 main 构建。更新后的精确包 382/382 回归再次通过。

### 最终发布结果

- 源码功能提交：`f7d62f0`（布局）、`a476533`（打开与恢复确认）；发布基线保护提交：`eb3a663`。
- 第二项发布时间：2026-10-20 18:37:46；静态资源 `main-BlhRh--D.js`，SHA-256 `be0f22af1b2c6d4753623bbc4101f306c0cf4a64db5432efb60b48718591ac30`。
- index SHA-256 `70b769a17402f71910dd74b1a6bbb3a90499c254e0caa1b66421725f7862bc73`。API/Broker 身份、当次发布前后 Agent/策略权威状态及 ActPlane 哈希均不变；保留此前 CSS 和所有已有资源。未推送远端。
- 18003 浏览器复验：运行中实例“打开”、未知受控实例“打开”、明确未运行实例“启动并打开”。截图 `published-open-18003.png` 与 `published-layout-18003.png`。
- 本次任务没有发送 Agent start/stop/配置保存/策略应用请求。工作期间其他操作曾改变 RQ5 DSH 运行状态，不能把整段任务期间的变化归为本次发布；不声称所有实例整个任务期间均未变化。
- 回滚备份：`/var/lib/agentscope-scope-demo/release-backups/connection-layout-20261020-182717/` 和 `connection-entry-20261020-183746/`，保留旧 index、资源及结果。

## ActPlane 核对

- `git diff a182291 main -- actplane` 为空。
- a182291 / b37b4fd / main 的 ActPlane tree 均为 `3b3e40e3eb4b1c927496aa73759407757a494fb3`。
- 自定义传播回执引入于 `0d0cd2d`，被 `26dca2f` 撤回；当前不能宣称完整多跳因果链。
- 实际配置的 `/var/lib/agentscope-scope-demo/bin/actplane`、10 月 14 日运行基线及 10 月 20 日 API 发布目录副本均为 SHA-256 `5e8d43c279d88bd4215f654746675debfd976e28426c9fabdabeca408865d6da`。
- “原生版”在这里指未保留本次标签功能对 ActPlane 的改造，不等同于整个仓库与上游零差异。

## 未合并分支核对（本地 refs，只读）

未执行 fetch、merge、push。19 个分支 tip 不是 main 祖先；这不等于 19 项产品能力遗漏，历史上有内容整合提交。

| 最近分支 / tip | 未进入 main 的提交 | 内容判断 |
|---|---|---|
| codex/windows-main-sync-20261016 / f4cd64d | 1 | 仅旧标签传播验收文档，包含已撤回的自定义完整链叙述；不应直接合并 |
| codex/rfc-execution-unit-audit-20261014 / a15630e | 9 | 架构、模板与执行域设计/原型文档；旧四层/工作区方案与当前产品合同有差异，需逐文档评审，不是缺少最新连接 CSS |
| dataset / 143c090 | 4 | 研究提案与归档文档，不是主服务 UI |
| codex/policy-lifecycle-20261014 / 1197a7d | 2 | 独立候选重新校验及审计；main 已有 approval_recovery，相关测试文件与 a894713 相同，代码在后续模板/统一状态提交中继续更新，不应按提交号盲目重并 |
| codex/value-reliability-20261012 / bea72bc | 2 | 审批可用性及隔离 DSH/mini 实验证据；main 已有实验反馈集成（55be2fe）和后续审批实现，剩余需按证据文件比较，不能称作遗漏产品功能 |

其余较旧分支（仅列出非祖先状态，未逐项裁定业务差异）：技术文档 `231b79d`、codex/four-layer-audit-20261012 `e4e56ad`、codex/because-feedback-20261011 `6499157`、codex/policy-approval-unification-20261011 `7ce54b6`、codex/architecture-review-20261011 `a5de0ba`、codex/ui-redesign-notice-publish-20261009 `f956dfa`、codex/runtime-hooks-20261008 `e721f39`、codex/connection-history-20261007 `42257d4`、history-records `6e1117c`、codex/runtime-observability-ui `79452ec`、fix/overview-remove-layer-flow-20261007 `6ae3313`、codex/windows-release-20261007 `150872b`、codex/managed-dsh-policy `23d4eb9`、archive/windows-before-scope-20261007 `9400185`。

标签原生整改、统一状态、子配置删除的当前实现已进入 main；不是要从上述旧分支再次整体合并。main 的 `0d526d2` 已本地提交但不随本次 CSS 发布。
