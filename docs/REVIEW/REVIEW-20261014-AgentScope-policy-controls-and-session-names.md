# AgentScope 系统策略摘要、结束操作与中文会话名验收

日期：2026-10-14。结论：本次 UI/管理合同修改已验收并更新本地 18003。三个既有运行实例、一个已停止实例的执行身份及策略均未改变；没有批准、撤回、停用或删除正式策略，没有停止正式 Agent。原安全总览和公告未修改。本次不是四项 Agent 业务实验的重新验收。

## 用户可见结果

- 系统审批“适用 Agent”只显示“全部受控 Agent”，以“提交时涉及 N 个实例”说明冻结影响范围；不枚举每个产品和 PID。详情默认折叠逐实例影响，单 Agent 审批保持精确入口。
- 审批标题展示策略名称；新增、修改和停用候选保存变化名称。移除后查看历史仍能看到被停用策略和准确变更数。
- 当前 Agent 基线助手和原生会话助手均增加“停止生成”；取消请求期间显示“正在停止，当前请求结束后退出”，不假装已经杀死模型请求。
- 系统配置和 Agent 文档提供停用入口，形成新候选，批准后再单独应用。系统配置库审批预览已补齐两步接口参数，界面实测“已批准 · 待应用”及另一个“应用策略”按钮。
- 未生效配置提供“删除配置…”确认，保留版本、审批和执行历史。已生效配置不能直接归档，先停用并完成批准及应用。
- 停止 Agent 明确说明全部会话/受控执行进程受影响，显示确认 PID，保留配置及历史；UI 冻结弹窗打开时的代次/策略指纹，服务端锁内拒绝漂移后的停止请求。
- 已按精确实例/会话键保存 11 个既有会话中文显示名，包括两个冷历史会话。无原始标题的三项使用“未命名会话”，不虚构任务。正式列表和审批来源均已读回验证；增加“修改名称”入口。

## 整合和发布

初始实验工作树 bea72bc 缺少已运行的 Agent 基线及两步审批改动。发布前逐文件发现差异，未将旧工作树覆盖到正式服务；改建 `/home/happy/projects/agentscope-policy-lifecycle-20261014`，以 d66605e 为基线，手工合入六个前端冲突，保留基线生成、approve/apply、会话局部候选审查及继承分组。最终测试和正式发布均来自这个整合版本。

后端发布：`/opt/agentscope-policy-lifecycle-20261014-140322`。最终 UI 独立静态发布：`/opt/agentscope-policy-controls-ui-20261014-1410`，HTTP 实际资源 `index-BmLVhcze.js` / `index-B-Afi7J3.css`。最终静态更新把摘要改为提交时范围，避免将历史目标数混称当前全部登记数；此次更新没有再次重启 API。

API PID 从 3051254 变为 1083843，属于本次显式 API 更新；Broker PID 1881389 及进程开始身份不变。UI/数据库备份和旧发布保留在 `/var/lib/agentscope-scope-demo/release-backups/agentscope-policy-lifecycle-20261014-140322`。原总览组件以及 value-evidence.html、value-announcement.html 源码与前一发布逐字节核对一致，公告静态文件发布后也一致。

| 既有运行实例 | PID | generation | 结果 |
| --- | --- | --- | --- |
| DeepSeek Harness，1f446957 | 1881572 | a8ee7f9c5ad64e0a9bf543e3929255ed | 前后相同 |
| Hermes，c0dd272b | 1881769 | 947b1b6dd3334b3c9a2a250bd3705832 | 前后相同 |
| DeepSeek Harness，cc444fe3 | 1881965 | 3028d67dd05a4be2ac4944b26e278a6d | 前后相同 |

策略哈希、执行域、系统/实例 DSL 版本及文档均逐项相同。bb171d31 历史实例保持 closed、无 PID，改名没有启动它。最终核验三个保护均 open/fresh，pending_events=0、outstanding_calls=0；18000/18004 监听身份不变。完整哈希和核验摘要在 [证据 JSON](../evidence/policy-controls-20261014/acceptance.json)。

## 真实内核与管理链验证

最终隔离环境是 18186、独立 DB `/var/lib/aslife-flow-20261014`、socket `/run/aslife-flow-20261014/broker.sock`、任务根 `/p14f`、BPF pin `/sys/fs/bpf/aslife-flow-20261014`，仅使用新建合成资源。Agent 为 instance-645361be393b4469。ActPlane 二进制 SHA-256 为 5e8d43c279d88bd4215f654746675debfd976e28426c9fabdabeca408865d6da，内核 6.6.114.1-microsoft-standard-WSL2。

| 阶段 | 实际证据 | 结论 |
| --- | --- | --- |
| 保护生效 | PID 1058832 read_completed=false，errno=1；同 PID/domain 内核 blocked=true，规则来源对应中文测试配置 | 真实内核拒绝，不能仅看诊断进程 returncode=0 判断读取成功 |
| 合法对照 | PID 1058880 read_completed=true | 其他测试文件允许读取 |
| 停用待审批 | PID 1058937 read_completed=false，errno=1；原 generation 保持 | 候选不改变保护 |
| 已批准但未应用 | PID 1058948 read_completed=false，errno=1；原 generation 保持 | 批准回执不等于撤销保护 |
| 显式应用移除 | 仅测试实例重建，旧 PID 退出；PID 1059854 read_completed=true | 新执行域按批准后的配置加载 |
| 错误/旧确认 | 错误哈希、过期候选、旧停止代次返回 409；同应用请求重试幂等 | 不越过版本和目标检查 |
| 删除与停止 | 生效配置归档返回 409；停用后归档保留版本。停止后 gate=closed、active=false、PID=null，原进程退出 | 删除配置和停止执行明确分离，不自动再启动 |

这些读取由受控执行域中的固定 Broker 诊断探针发起，本轮没有调用模型或重跑 DSH/mini 业务任务，不据此新增“模型安全反馈后完成业务”的结论。既有四项业务实验及其失败仍见之前实验报告。最初 18185 辅助验证有测试驱动 URL 写错导致中断，原失败记录保留；修正后通过，但最终验收采用重新建立、含当前两步审批的 18186 版本。两个测试实例均已停止，两个测试 API/Broker 服务已关闭，夹具和证据保留。

## 回归和真实页面

最终前端全套 **270 passed**；后端 13 个相关模块 **170 passed**，覆盖显示名 CAS/跨实例隔离/冷会话/管理员鉴权、停止身份检查及空请求兼容、DSL 与配置库、统一审批、Agent 基线草案、取消生成和执行合同。Vite 构建成功，114 个模块；保留既有单包超过 500 KB 的警告以及后端五条弃用警告，无测试失败。日志见 [前端](../evidence/policy-controls-20261014/frontend-tests.txt)、[后端](../evidence/policy-controls-20261014/backend-tests.txt)、[构建](../evidence/policy-controls-20261014/frontend-build.txt)。

真实浏览器验证了系统配置库新候选→批准待应用→显式应用，仅操作隔离数据；正式页只查看/取消动作。390×844 窄屏无横向溢出；删除弹窗 Escape 取消恢复到原按钮；正式改名弹窗显示元数据边界；正式停止弹窗展示 PID 和全会话影响，并取消退出。正式目录和审批来源显示中文。图示：[系统摘要](../evidence/policy-controls-20261014/approvals-18003-compact.png)、[中文目录](../evidence/policy-controls-20261014/sessions-18003.png)、[停止确认](../evidence/policy-controls-20261014/stop-confirmation-18003.png)、[批准待应用](../evidence/policy-controls-20261014/isolated-approved.png)、[窄屏](../evidence/policy-controls-20261014/isolated-mobile.png)。

## 保留问题与范围

原生客户端的原始英文标题保留供核对；本次改的是 AgentScope 显示名称，不宣称原生所有界面汉化。未来新任务使用中文；没有新增按标题授予权限或自动恢复会话的逻辑。失效审批创建新版本的快捷恢复入口仍未完成，见 [开放 BUG](../BUG/BUG-20261014-AgentScope-stale-approval-recovery.md)。原生工作区/会话独立执行域与局部加载也未在本轮完成，仍禁止扩大到整个 Agent 来绕过能力限制。

未改普通业务 Java、数据库合同、Broker、ActPlane 引擎或原生集成；没有远端 push。文档同步维护 RFC、ADR、BUG 和本 REVIEW。本次即时核验不等于新增 24 小时稳定性观察通过，也未重新开启定时任务。
