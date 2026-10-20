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

当前记录：验收通过，发布待执行；完成后追加结果。

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
