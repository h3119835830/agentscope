# REVIEW：DSH 工作区绑定与结构化策略记录专项验收

> 逐句合同修订：前版作业级完整 DSL 展示与评估复选框已废弃。现行逐句子句、证据及加载隔离见 [RFC](../RFC/RFC-20261006-逐句DSL与控制台锁定.md)；整包 DSL 仅后台用于验真和加载。

日期：2026-10-06。结论：本次界面、记录合同和自动绑定专项验收通过；不把此前 OS 压力测试重复计为本次新增测试。

## 工程检查

| 检查 | 结果 |
|---|---|
| 后端 backend/tests 全量 | 256 通过，5 条既有弃用警告 |
| 新导航兼容 Node 测试 | 1 通过 |
| Pi runtime extension 真实 Node 加载 | 通过 |
| 前端 Vite 构建 | 通过，最终 index-PmfCqzpm.js |
| 权限注释隔离 | 注释不能扩权，伪造/未读取证据拒绝 |
| DSL 保真 | 完整 DSL 哈希保留；篡改拒绝 |
| 加载判定 | 无真实应用回执的候选不会标为加载 |
| 工作区 | 精确 task/workspace/session 匹配；多候选不猜测；自动排除已结束任务 |
| 审计 | OS / 工具 / 控制面分离；探针工具结果来源继承 |
| 记录隔离 | 管理员认证必需；外任务详情拒绝；轻量接口无原生私有流 |
| 保留增量 | 后续输出扩权时 acceptance.txt 保护仍显示生效 |

## 真实 Pi 与 DSH 复核

任务 d5e21e674b464d16，本次真实用户消息为“继续保留 acceptance.txt，不得修改或删除；本轮只读取它并报告，不修改工作区。”原生持久 user/message 哈希 f9b9b0657b8efe08b85596fb0cf7022136793286068f155a39ff3094a293e3ff 已核验；实际派发轮次 23，接受时轮次 22，冻结 revision 40。

完成的 Pi 作业 1761cfbeed424e9eb9ca93dadc060db8 提交两条真实 identified_statements：保留文件为 per_event；只读并报告为 semantic_only，均显式说明上下文需求及证据。该消息已有保护，返回 no_change，不新增或加载 OS 规则。新提交 DSL 哈希 b510460e72b259a148d7c3ed07052bf6bec0267d4254eacf38cf04ff6f085fa1 核对成功。

同一 Session ID 保持，策略 v7、启动底线 hash 和 acceptance.txt 字节 hash 保持，running/open，Broker 返回 domain_verified=true。没有重新启动 Native DSH，没有发送或覆盖页面用户已有草稿。

## 真实浏览器验收

通过 CUA 在实际 18003 服务核验：无 task 提示时自动匹配唯一活动受管工作区；六项侧栏没有重复运行时 Scope；旧 view=runtime 链接转到工作台且 task 保留；启动三条 OS 记录及对应真实 DSL 可读；上下文显示路径/hash/已读；新 Pi 两条语句及类型正确；关联实际轮次 23；no_change 显示未加载变更；Hook 展示两个阶段的真实流程。

执行审计的三种选择分别展示 OS、工具、控制面记录。实际 acceptance.txt 的内核拒绝详情包含 write、目标、call ID、PID 674675、域 559307901、v4 和 runtime-file-protection。独立探针明确标注，工具开始/结果不冒充实际 OS 成功。切换时清空旧类别并显示读取状态已复验。详情抽屉未展示原始 JSON。

验收截图位于同级 Pi-DSH-验收证据-20261006，结构化摘要为 [structured-workbench.json](Pi-DSH-验收证据-20261006/structured-workbench.json)。本次未执行旧 navigation_ui_acceptance.cjs 的浏览器驱动；仅维护其新合同，实际浏览器由 CUA 验收。未声称本次完成窄屏全模块矩阵。

## 部署与范围

18003 API 与 UI 已加载本次改动；Broker PID 690080 保持，受管 DSH 原会话持续运行。3000 返回既有认证 401，18000/18003 返回 200；父 /opt/agentscope checkout 干净。只涉及 AgentScope、Pi 结构化输出和技术文档，没有普通 ERP/Java 业务改动或远端推送。

能力边界：仅已登记的受管工作区自动匹配，个人 3000 未自动接管；历史规则片段没有被伪称为原始完整 DSL；历史 context_required 推导有来源标记。此前支付完整任务 8 通过/5 失败不被本次记录专项覆盖。更广泛 OS 保护证据沿用前版独立记录，不新增计数。
