# REVIEW：三阶段闭环实现与验收边界

日期：2026-10-25。

## 主要代码

- `backend/reference_reader_channel.py`、`reference_file_reader.py`、`instances/workspace_references.py`：固定读取身份、fd 锚定的正文/目录/元数据核验。
- `scripts/ecs_api_with_reader.py`、`deploy/systemd/agentscope-preview-reader.conf`：读取进程启动和 API 降权。
- `backend/broker/instance_runtime.py`、`instance_supervision.py`：固定启动 argv 匹配、真实 PID/domain 校验、调用 tag、重放和串行准入、持久回执。
- `integrations/dsh-instance-runtime/lib/index.js`、`execution-lane.js`：原生工具 hook、顶层执行队列、轮次结束观察。
- `instances/controller.py`、`sessions.py`：可信事件接收、精确关联与当前加载上下文。
- `instances/template_tools.py`、`policy_context_agent.py`、`template_configurations.py`：发布模板工具化、相关性检索、严格参数验证、系统及 Agent 约束上下文。
- `instances/pi_provider.py`、`integrations/pi-policy-tools/policy-extension.ts`：原生 Pi RPC、只读工具回调、版本和结果校验。
- `instances/policy_lifecycle.py`、`lifecycle_api.py`、`store.py`、`main.py`：自动作业、冻结证据、失败重试与追加复核。
- `frontend/src/SessionAudit.jsx`、`LifecycleSettings.jsx`、`sessionAudit.css`：会话审计表、渐进展开、准确目标设置与人工标记。
- `actplane/bpf/process.bpf.c` 及对应 prebuilt object：仅拒绝返回的 verifier 兼容实现。

## 已验证

后端全量 1,588 passed（5 条 FastAPI 既有弃用警告）；前端 413 passed，生产构建通过。ActPlane Rust workspace 145 passed、49 ignored；C predicate tests 42 passed。ignored 项不能声称已执行。

ECS 实际加载兼容引擎，DSH 原生调用收到 `/w/0/release.json` 的 block，可信 tag 与单一原生调用对应，编译 source_ref/clause_hash 和 domain 一致。另一会话没有被关联到该事件。独立文件摘要检查发布清单和无关文件未变。运行时 Pi 与运行后审计自动完成，审计复核没有改写原结果。

最后一轮真实场景记录 11 次原生工具调用，内核命中编号 6。报告确认过期缓存 expired.tmp 已删除、清单回写被阻止。完整场景中的运行时 Pi 返回 no_change，未生成或应用新策略。此前多余候选的结果保持不变。

原受控 DSH 已恢复，原策略摘要不变，启动保护、受保护文件完整性、写入授权探针和网络核验均通过。API 重启后原生 PID 与运行代次不变，API 与 reader 的有效/ambient 能力均为零。证据见 restored.json。此测试不是 Broker 崩溃或宿主重启后自动恢复授权的承诺：Broker 丢失后按原设计关闭执行边界，须重新核验再启动。

本地 SSH 转发的真实页面在 1440 与 850 宽度检查无横向溢出，设置限于所选 Agent。长模型说明默认折叠，内部 ID 只在原始证据中保留，不铺在主页面。

## 风险与未声称事项

第一次原生任务自行 chmod 444，产生的是 DAC 拒绝，无内核命中，明确判失败并保留原记录。随后补齐缺失的已加载 DSL 上下文，才取得真正内核事件。不得用前一次报告代替内核证据。

一次运行时 Pi 给出了重复清单保护和额外报告生成约束。这些是模型候选，不是必要变更或授权，保持草案，未批准、未应用。追加完整 Agent DSL 上下文解决信息缺失，不意味着模型永远不会建议多余约束。

审计模型文字仍须复核：成功工具回执不证明具体业务动作，摘要一致不证明整个历史没有瞬时变化，策略命中不等于恶意或全系统零损害。原生工具 payload 未复制到本审计层，相关推断保留不确定性。

可信调用归属依赖原生 hook 作为受信集成组件，不是对已遭篡改的原生进程或插件本身的独立完整性证明。未宣称所有工具均获强进程级独立认证。

内置浏览器控制工具初始化失败，本次采用独立无登录 Chrome 对真实 SSH 转发页面进行自动化截图和断言，不用模拟截图替代实际页面。

发布状态：允许本地提交；没有远端推送授权，不执行 git push。服务器是本任务候选 release，不能称为 GitHub main 已发布。
