# AgentScope 审批重新校验链路验收

日期：2026-10-14。结论：失效详情→只读版本对照→重新校验新候选→独立批准→再次确认应用的入口已更新到本地 18003。正式“环境凭据文件”只完成新候选创建，状态为待审批；未代用户批准或应用。三个既有运行 Agent 的 PID/generation/策略/执行域保持不变，原已停止实例保持停止。

## 本次失效原因

旧候选 4902875341f142e0b7f3d43b49ac29a3 于 2026-10-13 14:29:26（北京时间）提交，冻结配置库 policy-db7104b8c42647c090581ac5d55f512c 的 v1。该资产于 2026-10-14 13:37:10 保存为 v2。逐字段比较 v1/v2 的 config 和 document 内容完全一致，均为 `.env` 后缀、open、notify（记录通知）。既有 save 每次成功保存创建新 revision，verify_proposal 按资产版本核验；旧 v1 与当前 v2 不一致触发 stale。不是时间到期，也不是本次应用/停止了 Agent。

页面原来把不同失效原因合为“Agent 环境或策略配置已经变化”，本次改为明确显示资产名称及 v1→v2。没有删除版本检查，也没有把旧审批改回可应用。正式策略的处置仍是原始 notify，没有擅自改为 block。

## 正式交付状态

新候选 **27739bdbca0a43bfa20e42d62e2267e4**，显示“新增 环境凭据文件”，采用配置 v2，status=pending、can_approve=true、can_apply=false、approval_status=unrecorded。原候选内容、目标快照、基线、哈希和创建时间保持不变，两条记录可相互查看。

用户下一步：勾选核对内容与影响范围→批准变更→在“已批准·待应用”再次核对→应用策略。批准只保存决定；应用才会按影响范围重建运行中的执行器。当前没有批准回执、没有加载动作，系统 DSL 仍是原 revision 6/空用户文档。原审批依旧失效，不直接复活。

API 发布目录 `/opt/agentscope-approval-recovery-20261014-143959`，资源 `index-BJHcG1dY.js` / `index-C0IfdlsY.css`。API PID 1083843→1187353 为本次显式 API 更新；Broker PID 1881389 与开始身份不变。旧 UI/数据库备份和回滚配置保留在 `/var/lib/agentscope-scope-demo/release-backups/agentscope-approval-recovery-20261014-143959`。

| 既有实例 | PID | generation | 前后结果 |
| --- | --- | --- | --- |
| DSH，1f446957 | 1881572 | a8ee7f9c5ad64e0a9bf543e3929255ed | 相同 |
| Hermes，c0dd272b | 1881769 | 947b1b6dd3334b3c9a2a250bd3705832 | 相同 |
| DSH，cc444fe3 | 1881965 | 3028d67dd05a4be2ac4944b26e278a6d | 相同 |

系统/实例 DSL 版本、文档、typed policy 哈希和其他 18000/18004 监听身份逐项相同。最终三个保护均 open/fresh，pending_events=0、outstanding_calls=0；历史 bb171d31 实例没有启动。后端运行文件和源码逐文件相同，实际 HTTP 资源与本次构建逐字节相同。原安全总览和两份公告均未修改。

## 隔离真实链路

环境为 18187、独立 `/var/lib/asrecover-20261014` 数据库、`/run/asrecover-20261014/broker.sock`、`/p14r` 任务根、`/sys/fs/bpf/asrecover-20261014`，唯一测试实例 instance-d385ac26af4a424e。新建合成文件，未使用真实凭据数据。受控 Agent 进程内的固定 Broker 探针验证实际系统效果，未调用模型，不扩大为模型任务完成或反馈验收。

1. 旧 notify v1 候选因库中改为 block v2 失效，预览明确内容已变化；重新校验产生新独立待审批记录，重复请求返回同一记录，原进程/代次及当前策略不变。
2. 新候选待审批、已批准未应用阶段，测试文件仍可读取；批准本身不装载 block。旧候选和错误批准哈希均不能应用。
3. 显式应用后仅测试执行器重建，旧 PID 退出；读取受保护测试文件返回 errno=1，内核 blocked=true 事件与探针 PID/执行域/规则绑定一致；读取另一合法测试文件成功。
4. 真实浏览器再验证“正文相同 v1→v2”的恢复、独立待审批、批准待应用、重新勾选确认应用成功。应用第二文档后再做真实探针，原 block 文档仍拦截，合法文件仍可读取，证明合并保留其他文档。
5. 测试实例最后显式停止，测试 API/Broker 关闭，未操作正式实例的停止或应用接口。

预览/编译曾因文档排序不同产生 next_dsl_hash 假漂移，相关回归发现后修复为共用 canonical_documents。窄屏全局主题的 th nowrap 曾造成名称重叠，已用局部名称元素修复并截图复验。以上失败及整改原因记录于此，最终验收取修复后的结果。

## 回归与证据

最终前端全套 **272 passed**；后端 14 个相关模块 **178 passed**；Vite 构建 115 个模块成功，保留已有 >500KB 包警告及后端五条弃用警告。覆盖相同/不同配置版本、预览后漂移、精确范围、差量合并与冲突、旧基线缺失、源资产归档、生成绑定、局部能力不足、管理员鉴权、幂等及创建中断。未完成的恢复子候选在统一批准、直接旧 DSL 应用、再次从子候选校验三处均拒绝，不能跳过来源关联。

真实页面验证只读预览、内容一致提示、当前采用的版本、未勾选不可创建、新旧记录链接、独立批准和第二次应用确认；390×844 布局无横向溢出或名称重叠，Escape 返回原“重新校验”按钮。正式页面仅创建待审批候选并停在该页。

[验收 JSON](../evidence/approval-recovery-20261014/acceptance.json)、[前端测试](../evidence/approval-recovery-20261014/frontend-tests.txt)、[后端测试](../evidence/approval-recovery-20261014/backend-tests.txt)、[构建](../evidence/approval-recovery-20261014/frontend-build.txt)。截图：[正式失效原因](../evidence/approval-recovery-20261014/stale-18003.png)、[正式版本对照](../evidence/approval-recovery-20261014/preview-18003.png)、[正式待审批](../evidence/approval-recovery-20261014/pending-18003.png)、[隔离批准待应用](../evidence/approval-recovery-20261014/approved-isolated.png)、[隔离应用成功](../evidence/approval-recovery-20261014/applied-isolated.png)、[窄屏](../evidence/approval-recovery-20261014/revalidation-mobile.png)。

## 范围与保留限制

恢复支持系统配置库和有旧基线证据的手工 Agent/System DSL。生成绑定必须回助手重读生成；归档源资产、缺失基线和冲突回所属配置处理。原生工作区/会话独立加载能力未新增，导航保留原精确目标，不扩大范围；失败加载的 blocked/paused 状态不自动解除。普通业务 Java/数据库合同、Broker、引擎和原生集成均不改。无远端 push，也未重新开启定时观察。对应 RFC/ADR 与原 stale-approval-recovery BUG 同步维护。
