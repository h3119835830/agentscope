# REVIEW-20261011 Node 来源与 Agent 策略隔离复核

结论：**/node 是程序匹配条件，本身可以匹配其他 Node；当前两份待审批 Agent 草案的目标均仅为 instance-1f4469579e8947f4。控制面按连接 ID 选择有效文档，Broker 将规则和标签更新绑定该连接的进程域，不能把 basename 匹配误称为实例隔离。此次没有确认、加载或应用新策略。

## 代码合同复核

- instances/dsl_policy.py documents_for 仅组合 system 与指定连接 ID 的文档；target_snapshot 的 Agent 分支只选择 ID 相等的行。Agent proposal/confirm 按 scope_id 查找，冻结目标、代次、revision/hash，重新核验后才进入既有启停/加载流程。
- broker/instance_runtime.py run_id 由完整实例 ID 派生；每连接使用独立 BPF pin root 和 cgroup。start 的 control launch-child 显式携带该连接 domain_id 和有效 DSL delta。当前控制台 Agent 草案不走系统分发范围。
- ActPlane lower_exec 将 **/node 降低为 basename=node 的精确程序条件；即便写完整绝对路径，此处也不能当作实例 ID。
- ActPlane append_policy_delta 显式指定非零 target_id。实际 BPF cap_domain_matches_pid 根据 cap_task 查调用进程域并遍历父域；te_rule_effect 在标签/操作匹配前检查规则域，exec 更新也按域检查。兄弟域、域外和未绑定进程不能获得 DSH 本地规则/标签。
- 子域继承父域约束是明确设计：当前 DSH 连接及其受控子进程处于该执行边界，同一连接的原生会话共用执行器。独立 Agent 连接不属于该子树。系统策略则明确分发到所有受控连接；不能将系统层 **/node 草案描述为 DSH 专属。

## 测试结果

定向后端测试 69 passed、0 failed、0 skipped，5 项既有弃用警告，3.20 秒。范围为 test_dsl_configuration.py、test_policy_sources.py、test_agent_policy_context.py、test_actplane_domain_guard.py。

新增三项真实 AST/编译器集成测试：

1. 当前 DSH、另一个同名 DSH（同工作区、同 **/node）及 Hermes 同时存在时，Agent proposal 只编译/选择当前 ID；在隔离测试数据库和假执行器中模拟确认，仅该 ID 被启停，其他连接的行、文档和运行状态不变。
2. 将当前 Agent proposal 从其他连接 confirm，操作在启停前被拒绝。
3. 相同 source 的 system proposal 与 Agent proposal 具有不同明确目标集合；保存校验均不启动或加载执行器。

另新增一项实际 BPF C 代码的用户态测试：直接提取部署源码 cap_domain_matches_pid 与 cap_labels_for_pid_domain，只有 map lookup 使用测试数据，编译后执行 14 项断言。当前域/子域匹配；另一 DSH、另一 Agent、父域进程、未绑定进程及无效域不匹配当前 DSH 本地策略；共享父域继承仍成立。这不是重写一个模拟判定器，也没有加载 BPF 程序。源码 hash 见证据。已核对实际运行 Broker 的 main.py/instance_runtime.py 及 API release 的 dsl_policy.py，与本次评审文件逐字节一致，hash 留存在 deployed-code-hashes.json。

初次测试把既有生命周期中的 start 前再次 stop 误认为只应一次 stop，断言失败；核对 controller.start 后按真实合同修正。所有启停仍严格属于目标 ID，未修改生产生命周期以迎合测试。

## 真实 18003 只读验收

scripts/audit_agent_policy_isolation.py 以 mode=ro 读取当前数据库，核验 root 所有 manifest、boot/代次、cgroup 路径/inode、实际 PID/start_ticks/exe；只读取 pinned BPF maps，未执行 map update。

- DSH PID 54870 → cap_task 域 310407274；同 PID 在该连接 cgroup。实际程序 /opt/agentscope/bin/node。
- 当前域 cap_policy 规则位图与所有活动 ts_rules 的非零 domain_id 一致；父域保留独立绑定。不存在把这份连接本地规则作为 domain=0 全局规则的证据。
- 两个临时、无网络/文件操作的独立 Node 对照进程使用相同 /opt/agentscope/bin/node：均不在 DSH cap_task 与 cgroup 中。测试后已退出，仅终止本次启动的对照进程。
- 两份 pending proposal（7df4ac16c8c5、abc350357edc）的 scope 和 target_ids 都只指向当前 DSH。
- 验收前后数据库连接/策略/草案快照、已加载规则与位图、API/Broker PID 和启动时间完全一致。没有服务重启、Agent 命令、策略 compile/proposal/confirm/load/apply 请求。

证据：用户技术文档目录 evidence/node-isolation-20261011/runtime-audit.json、targeted-tests.log、engine-source-hashes.json、deployed-code-hashes.json。

## 验收范围与应用边界

本次证明控制面的精确目标选择、真实内核绑定事实与实际域判定函数行为；没有把新候选装入内核并执行 allow/deny 文件探针，因此不声称已验收新候选的实际拦截或反馈送达。真实 Hermes 当前离线，跨 Agent 同程序场景由隔离测试实例验证，没有启动真实 Hermes 或第二个 DSH。现有两份草案仍 pending，用户确认权限保持原状。

只新增测试、只读验收脚本与文档；运行产品代码未变，无需重启/部署。未推送远端。
