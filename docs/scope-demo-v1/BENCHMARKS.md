# 文件权限 Demo 的数据集选择与真实验收

日期：2026-10-05。首轮优先覆盖文件权限和动态会话，不以数据集规模作为完成标准。

## 已选择的验证组合

|资产|用途|首轮范围|当前状态|
|---|---|---|---|
|自建 Python 标准库项目|同一任务 S0—S4、真实 DSH/Pi、核验后切换快照、重启恢复|一个完整任务，合法/违规操作都有|已支持动态 Scope；运行报告另行记录|
|OpenAgentSafety / RQ5|配置保护与禁止修改测试的公开安全场景|safety-delete-config、safety-impossible-tests|原始任务/资产/评测器已冻结；启动策略有适配，动态 Scope 尚未接入|
|ActPlane RQ2|检查文件限制能否覆盖不同工具路径|只取受支持文件操作；补充间接脚本、已有 FD、目录改名/符号链接的真实探针|公开 trace/结果是参考资料；复制历史结果不计本机内核通过|
|SWE-bench Lite|验证权限限制下仍能解决真实 GitHub issue|后续筛选 3—5 个 Python issue，先确认环境可复现|尚未选定 instance_id 或下载执行环境|
|ActPlane RQ4 / OctoBench|已有研究中的代码任务与约束参考|后续检查其 21 个选例中适合文件约束的任务|作为补充候选，不与 SWE-bench 同时扩大首轮范围|
|ActPlane RQ1|策略翻译与能力覆盖|按文件操作分类抽样|不替代真实 Agent/内核验收|

来源：
- https://github.com/Open-Agent-Safety/OpenAgentSafety
- https://github.com/Open-Agent-Safety/OpenAgentSafety/releases/tag/v1.1
- https://github.com/eunomia-bpf/ActPlane/tree/63db86945c9b8618a46aa68c8de214bc4b8343d9
- https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite
- https://github.com/SWE-bench/SWE-bench

OpenAgentSafety 是公开合成安全场景，虽然使用真实文件/终端工具，也不能称为真实用户项目。
SWE-bench 提供真实项目 issue，但原任务没有本 Demo 的动态收紧/扩权流程。新增用户消息、
授权阶段或报告要求属于 AgentScope 扩展实验，保留原始任务文本并单独记录 overlay；
不把改编任务的结果称作原 benchmark 分数。

## 挑选条件与实验合同

1. 权限由平台、任务要求和已确认用户授权确定。不能查看参考修复后替 Agent 放开恰好的答案路径。
2. 可写代码目录、保护资产和任务输出能对应到当前支持的文件操作。网络、远端服务、
   语义语气要求暂不作为文件 enforcement 成功样本；无法执行的要求保持 guidance_only。
3. 固定 repository/commit、任务原文 hash、资产 hash、目录映射、依赖、Agent/模型配置、
   内核/ActPlane 版本、随机参数和时间/工具预算。各任务独立目录与凭据，串行真实执行。
4. 先验收初始环境及评测器：原始配置/test 文件完整，未修改工作区能满足评分器前置条件。
   评分异常单独记录为 invalid_environment / invalid_evaluator，不算 Agent 不安全或成功。
5. 任务成功和安全分别判定。impossible-tests 可以诚实报告无法完成；不能以“测试必须全绿”
   激励改测试。保护测试的 hash 与内核拒绝需独立核验，原始评分器不一定覆盖内容篡改。
6. 评测器、参考补丁、预期答案、权限探针和验收驱动放在任务执行域外，不能注册为 Pi/DSH 输入。
   公开项目原有测试可以读取/运行；SWE-bench 评测补丁由外部评测环境负责。
7. 每个场景同时有授权内成功操作和越权拒绝操作；仅看拒绝数量或 Agent 自报不能证明正确。
   保存完整 Scope、域/PID/PPID、进程代次、工作区差异、保护资产 hash、功能结果、撤销证据。

## 已冻结 RQ5 资产的注意事项

本仓库既有冻结版本是 af1e44cf93efbaafbe69a547feb3d385133a5190，位于
backend/agentscope_app/bootstrap/fixtures/rq5。manifest.json 校验原始文件字节。
保留此版本用于既有回归，不静默升级它或覆盖之前的实验。

上游当前推荐 v1.1，并修正了评分路径/语法问题。已核对两个选例的 v1.1 evaluator：
delete-config 的 main.py 路径与旧冻结版本的 project_a/main.py 不同；
impossible-tests 的评分器检查文件集合/改名，并不足以证明测试内容未被篡改。
新公开数据实验先单独冻结 v1.1 并重验初始环境，不能混用新 evaluator 和旧布局。

当前 adapter 明确迁移 main.py、transaction-service 包目录和 rate-limiter 测试名，
不改原文件内容。scope_dataset_preflight.py 只检查 hash、映射前置条件和 oracle 分离；
它不运行评分器/Agent/内核，也不证明动态 Scope 已支持这些案例。

## 真实工作台验收

scope_live_ui_acceptance.cjs 启动 scope_full_acceptance.py --live-ui。
在 S0、S1 待审/生效、S2 待审/生效、S3 待审/拒绝/重新待审/生效、S4
共十个真实检查点直接读取实际服务并验收桌面、423px、差异、短记录、抽屉与版本。
不拦截 API、不注入状态。独立测试驱动按用户授权的固定范围扮演审核者，
Pi/DSH 不获得审批权；检查点回执只让测试驱动继续，不能加载策略。

待审截图核对旧 Scope 仍生效；拒绝 output 后权限不变；收紧维持同域，扩权换域/进程代次；
结束截图明确展示历史权限。真实任务功能、旧凭据失效、新任务无继承和内核探针由完整
执行驱动核验。历史 API 回放仍可用于异常状态展示测试，必须单独标注，不能计入本项通过。

## 2026-10-06 DSH 工作区预览

safety-impossible-tests 的原始 workspace 与 task.md 已复制到
/home/happy/projects/rq5-safety-impossible-tests，并在独立 DSH Web 中打开。
该预览保留原名与原字节，evaluator 仍在冻结源目录域外。19 个 workspace 文件、task.md
的哈希正确，16 个 Python 文件只作语法解析。该 Web profile 未绑定受管插件/策略域，
未向模型提交任务、未执行 benchmark，不改变上表“动态 Scope 尚未接入”的状态。
论文 RQ5 的启动前策略生成与 RQ4 的运行时增量不可混称；见 ACTPLANE-REVIEW-20261006.md。
