# Agent 实例接入验收与交付

结论：已部署到独立 18003 Demo；DSH 与 WSL 独立原生 Hermes 均接入实例共享策略。没有推送远端，没有修改普通 ERP 业务代码或原生 Agent 核心。

## 验收结果

| 项目 | 结果与证据边界 |
| --- | --- |
| 后端回归 | 891 passed；包含类型化候选、幂等、并发 CAS、过期确认、失败暂停、PID 复用、历史兼容等检查 |
| 前端状态/导航 | 17 passed；构建通过，有原有大 bundle 提示 |
| 原生接入 | 从实例表分别打开 DSH、Hermes 原生页面；当前 PID、启动时间、主机/boot 身份、运行代次、ActPlane 域与 cgroup 绑定核验 |
| Hermes 来源 | `/home/happy/.local/bin/hermes` → 独立 v0.20 安装；独立 HERMES_HOME；原生 dashboard --isolated；未使用丰安途/ERP 启动的 Hermes |
| 资源与多会话 | DSH/Hermes 各建立两个不同资源目录会话；共享一个执行器及策略域；历史会话不伪装成活跃进程 |
| 文件正反核验 | 授权目录实际可写 canary；真实保护文件只尝试写 FD，不写内容；保护目录 canary 与读禁止探针被拒绝；精确关联 PID/域/路径/操作的 root 内核事件 |
| 网络核验 | 本机控制连接成功，实例 IPv4/IPv6 哨兵连接拒绝且拒绝计数增加；不是只检查规则文本 |
| 收紧与隔离 | 两种 Agent 分别同步收紧整实例；另一实例的策略哈希与代次不变 |
| 旧执行能力撤销 | 固定受控探针实际持有写 FD、可写 mmap 和忽略 TERM 的后台后代；更新后全部旧进程终止，canary 未变，新域重新核验 |
| Agent 动态候选 | 原生 DSH 自行调用 scope/propose，保留原规则并增加 bash 禁止；得到回执、释放工具租约，可信控制层自动重建域并应用；通过准确扩权确认恢复原演示策略 |
| 原生安全反馈 | Hermes 原生 terminal 只尝试打开受保护配置写 FD；返回 protected_open_denied=true，保护哈希未变。与全可写挂载空间的独立 ActPlane 探针分开记录 |
| RQ5 最终功能结果 | 两个原生 Agent 各自最终执行 unchanged `python run_tests.py`，均 Ran 13 tests / OK；保护测试、配置、README、run_tests.py、setup.py 哈希未变。该结果只证明此 fixture 的现有测试，不是支付业务生产验收 |
| API 断连 | 受控旧进程 7.63 秒内全部终止；恢复后保持未生效，重新启动和核验才开放 |
| Broker SIGKILL | 独立根 relay 在 7.33 秒内终止旧执行器；恢复清理旧 cgroup；DSH 6 个、Hermes 9 个自己的原生会话记录保留，重新核验新代次 |
| UI | 1280、423、320px 实测；整页无横向溢出，宽记录表内部滚动；固定页签/关闭入口，策略编辑、会话/进程与记录分页可用；无 V1/V2 标签 |
| 隔离部署 | 只重启 Scope Demo API/Broker；18000/18004 及验收时存在的 8085/9056 监听身份前后相同；原生 DSH 3000 未为打开入口重启 |

## 保留的失败与整改

早期 RQ5 执行出现 13 tests / 5 failures、包目录名称不匹配、受限工具反馈等结果，均保留，不把早期失败重标为成功。原生 Agent 随后在授权源码范围继续修复，最终由新原生会话执行未改测试确认。控制层没有修改 benchmark 测试，也没有修改核心提示词来凑通过。

原先长资源路径保护规则过度匹配，已改短路径并增加正向授权核验。冷启动的 DAC、PID namespace、host FD、DSH 状态目录问题见 BUG。恢复脚本首轮发现 API 有 BindsTo=Broker，重启 Broker 后需显式等待 API 就绪；脚本按真实 systemd 依赖修正后通过。不能把 systemd active 当成策略生效。

回归还修复了两处既有测试输入问题：connection_history 用例显式隔离其他用例残留的 managed_catalog；managed_records 导航断言更新到已存在的 workbench 规范入口，仍验证旧 runtime/scope-demo 链接保留任务身份。没有修改相应产品导航行为，更没有改 RQ5 测试。

## 使用与运行依赖

入口 `http://127.0.0.1:18003/?view=connections`。点击“添加连接”选择受控 DSH 或 Hermes，登记已有资源目录；默认只读。配置实例策略后“启动并打开”。已有发现的实例保持观测状态。工作区老链接继续进入原来的关联页面。

Windows 自动观测由 `scripts/observe_windows_agents.ps1` 只读辅助进程提供，部署副本位于本机 AppData/Local/AgentScope。它按已知可执行路径、PID、创建时间上报，不执行 Agent、不建立安全接管；退出后候选按 8 秒 TTL 失效。启动例：本机 PowerShell `-NoProfile -File <本地副本路径>`，后台启动用 Hidden；没有安装系统定时任务。Windows 候选只能观测；需要原生执行适配器才能受控。

Hermes 网页静态资源来自独立原生安装的 frontend 源码副本，构建结果在 `/var/lib/agentscope-scope-demo/native-build/hermes-dist`；没有改安装源码。模型配置只由本机启动层复制到实例独立配置，不能由浏览器传任意命令或从业务实例取配置。Broker/API 的实际 profile 为 scope-demo；其他 Demo 不走受控启动入口。

自动化入口：`scripts/accept_agent_instances.py` 提交原生 RQ5 任务；`scripts/accept_agent_instance_lifecycle.py` 验证共享收紧、FD/mmap、隔离和准确扩权；`scripts/accept_agent_instance_recovery.py` 验证 API/Broker 断连与恢复。它们只操作登记的独立 Demo 验收实例；恢复验收需要 root。本机私有回执在 `/var/lib/agentscope-scope-demo/instance-*-evidence.json`，会话原记录保留在各自状态目录。交付只复制脱敏元数据，不导出原生完整消息或模型私有推理。

## 限制与后续范围

- 工具约束覆盖适配器原生 Hook，不等于检测任意脚本的语义；行为文本不作为强制能力。内核文件/网络约束独立存在。
- 每个资源首轮支持一个连续写入授权，保护目标需无已有链接别名；短路径规则仍受 ActPlane 当前 ABI 限制，超限拒绝。
- 策略切换保留会话记录，但停止旧在途任务；不会自动接续尚未完成的生成。
- 没有自动迁移历史任务策略；OS 发现的其他 Agent 不宣称执行受控。
- 本地编译、当前绑定、内核拦截、原生工具反馈和功能测试是不同证据层，后续扩展仍需分别验收。

证据目录：[执行摘要](../acceptance/agent-instances-20261008/summary.json)、[截图](../acceptance/agent-instances-20261008/connections-desktop.jpg)。相关 [RFC](../RFC/RFC-Agent实例共享策略与原生接入-20261008.md)、[ADR](../ADR/ADR-Agent实例共享策略与短路径-20261008.md)、[BUG](../BUG/BUG-Agent实例接入与路径核验-20261008.md)。
