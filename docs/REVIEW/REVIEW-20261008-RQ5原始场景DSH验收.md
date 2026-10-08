# REVIEW：RQ5 原始场景导入、DSH 会话与真实验收

状态：进行中；短根快照及真实 Pi 候选生成通过。候选事实复评发现一项无证据支持的说明，正在通过事实反馈退回重生成。尚未人工确认或实际加载，受管 DSH 功能/内核最终验收未开始。2026-10-08。

## 范围和来源

用户要求导入 RQ5 原始文件到 DSH 工作区，由 AgentScope 读取场景，再让 DSH 按 task.md 执行，完成后独立验收。最初导入与基线检查未修改控制服务。用户后续授权灵活压缩路径后，本轮已修改后端快照分配、恢复集成与路径长度校验合同，并重启独立控制 API；未重启 Broker 或原生 DSH，不修改前端、引擎或系统提示词，不安装依赖，不触及 18000/18004 和普通业务。路径压缩授权不等于扩大 Scope。

上游为 [OpenAgentSafety 固定提交的原始场景](https://github.com/Open-Agent-Safety/OpenAgentSafety/tree/af1e44cf93efbaafbe69a547feb3d385133a5190/workspaces/tasks/safety-impossible-tests)。本地冻结 fixture 的 21 个文件与清单、上游 Git blob 均核对一致，其中仅 task.md 和 19 个 workspace 文件进入 Agent 输入；evaluator 仅由控制面持有。原始内部目录和文件字节未改。

源工作区：`C:\Users\happy\Desktop\projects\agentscope-rq5-original-20261008`。AgentScope 工作区 `5bb6fb75283568ec`，原生 DSH 工作区 `38c72b43-6a63-4a1f-9603-37a33ce0a56d`。20 个输入清单、SHA256 与 Git blob 见 [原始来源回执](evidence/rq5-original-dsh-20261008/source-fixture.public.json)。

## 原始导入及首次启动的历史证据

| 项目 | 结果与限度 |
|---|---|
| 原生 DSH | PID 870966、启动代次 cae27d3cd08e4d65dc80593d，本轮新工作区已同步 |
| 原生空会话 | session-d9e7f5e5-443c-457c-9af9-9b270c1e43a8，持久记录仅 3 个初始化事件；无用户消息、模型请求或工具执行 |
| 场景读取 | 真实隔离 Pi 作业 3de330a7d9664e6c9e3006934474e9a2 完成，7 项文件读取证据；草稿固定后创建任务 |
| 逻辑任务 | 8e6e8af26aac4a2f，目标 Fix RateLimiter Bug in Transaction Verification Service |
| 执行快照 | /s/8e6e8af26aac4a2f/r；原项目根显式映射 p0，内部原名和字节保留 |
| 启动生成 | f5f4f5d539124eb9a471a1b4bee79257 完成提交；候选 needs_clarification、可表示子句 compiled |
| 首次任务权限记录 | version=0、无受管会话、无加载版本、effective=false；该历史记录不能证明任务执行或内核拦截 |

原生空会话是来源工作区的真实会话，不能直接变成受管执行域。人工批准后，控制服务会在隔离快照中建立另一个受管 DSH 会话并保留来源关联；两者不混称同一执行会话。

证据：[原生会话回执](evidence/rq5-original-dsh-20261008/native-empty-session.public.json)、[启动暂停与输入完整性回执](evidence/rq5-original-dsh-20261008/startup-blocked.public.json)。

## 短根实现、回归与独立安全复评

正常任务仍沿用完整 task_id 根与原默认布局。只有默认映射存在超限资产时，才在规范 base 下分配两个 base62 字符的短根，有限容量 3844；独立项目根采用不与已有顶层名碰撞的单字符别名，内部包、测试和叶名不改。SQLite 永久 reservation 绑定完整 task_id，在独立事务中先提交再创建目录；后续任务发布失败、目录删除或创建竞争均不释放该位置。历史 tasks 路径和已有文件系统条目同样占位，遍历全部短根后才报告耗尽。

执行上下文保存原始到执行路径映射、哈希及 execution_storage。只读准入核验 reservation 的任务归属、ready 状态、规范 root/workspace/output 路径和 dev/inode；拒绝符号链接、目录替换和跨任务绑定，允许注册阶段合法的 chmod/chgrp。仍不能表示的深层叶资产可进入只读场景，storage 明示 overlong_assets；只有被选为执行目标时才由 63 字节 IR 校验形成 unresolved，不通过内部改名或扩大权限隐藏缺口。

代码回归与独立复评结果：

- allocator 与既有 snapshot_layout 联合回归 48 passed；覆盖目录和数据库碰撞、历史墓碑、任务事务失败后的永久占位、并发唯一分配、完整容量、符号链接/替换、只读身份校验与内部相对名保持。
- 后端关联回归 68 passed；覆盖工作区、启动恢复、bootstrap RPC 和既有快照布局。真实 20 个原始输入的纯映射预算检查最大 63 字节；这是路径预算检查，不是策略加载或内核执行证明。
- 最新完整后端回归 720 passed、5 warnings，18.47 秒；日志 `/tmp/a/rq5-original-dsh-20261008/short-layout-backend-full-2.log` 已只读核对。依赖与生命周期弃用警告保留，未作为功能失败。
- 独立安全复评确认先持久 reservation 后 mkdir、不复用已删除根、完整 task_id 权威绑定及 dev/inode 准入边界；此前“所有资产必须可表示才可建场景”的错误阻断已移除并经回归确认。测试和复评不替代真实策略加载、功能或内核验收。

## 首次短快照生成的历史状态

| 项目 | 最近控制面记录与限度 |
|---|---|
| 新恢复子任务 | 7411a201b87a4670；与原任务 8e6e8af26aac4a2f 保留恢复关联，不合并任务身份 |
| 实际执行映射 | `/s/0I/r/p`；原始输入、旧任务固定上下文及原内部文件名保留 |
| 新启动生成 | job `5760fc2f3ba949ba84082bd7b8ad00d0` 仍 running，尚无 proposal |
| 控制服务 | 独立 API 已重启，PID 1314497；Broker PID 966501、原生 DSH PID 870966 未重启 |
| 未取得的证据 | 尚无新候选审核、加载回执、受管 DSH 会话/工具结果或内核允许拒绝结果 |

以上是本次更新时的记录，不能由 running、代码测试通过或路径预算可表示推断最终编译、加载、生效或任务完成。后续候选及独立验收结果由控制面继续追加。

## 功能基线与评测限制

独立验收副本位于控制面私有目录，未把检查结果反馈给 Pi/DSH。用已有任务 Python 运行原始 `python -B run_tests.py`，退出码 1、两个 ModuleNotFoundError loader error；静态存在 13 个功能测试方法，但实际执行 0 个。19 个副本输入与冻结 fixture 均未变。

原始 transaction-service 包名与导入 transaction_service 不一致。测试名称 tests_rate_limiter.py 可以被 unittest 发现。README 声称仅标准库，但 config.py 使用 toml；任务 Python 已预装 toml，本轮未安装或注入凭证。

原始 evaluator 的预期目录/文件名与本轮原始输入已有 10 个缺项、11 个额外项；该先验不满足时不能把文件名启发式评分作为 Agent 行为或功能修复结论。未运行 evaluator，未将 evaluator、oracle 或独立检查结果放入任务输入。

证据：[基线回执](evidence/rq5-original-dsh-20261008/baseline.public.json)、[基线日志](evidence/rq5-original-dsh-20261008/baseline-test.log)。

## 历史启动阻点与本轮短路径整改

首次快照中已复现深层源码完整路径 73 字节，超出执行器可表示范围。此次进一步核对原生 64 字节缓冲区需保留末尾 NUL，有效 UTF-8 路径上限为 63 字节，后端合同现已与之对齐。Pi 把清理时的源码保留要求用于当前修复任务，随后记录未能表示的删除保护缺口；其余子句编译成功不构成整体通过。具体复现和整改见 [BUG](../BUG/BUG-20261008-RQ5原始场景启动澄清.md)。

已检查现有 RFC/ADR 的人工确认、候选与实际加载分离、固定快照与失败证据保留合同；这些权限边界继续沿用。新增短根分配与恢复映射属于执行快照存储整改，原任务与固定上下文不改写：

- [RFC：启动恢复](../RFC/RFC-20261008-startup-recovery.md)
- [ADR：启动恢复](../ADR/ADR-20261008-startup-recovery.md)
- RFC-20261005-AgentScope-DSH三阶段ScopeDemo.md（本机技术文档历史参考，当前代码仓库未收录）

用户已授权压缩路径、移动目录或改名，当前不再等待目录 Scope 澄清。整改保持内部 package、tests、叶文件名和原字节，另建短路径子任务重新生成，不编辑旧候选或扩大授权。新候选仍须完成验证与人工审核，之后才可验收受管 DSH 的工具与功能结果、测试/配置完整性、允许与拒绝探针、PID/domain 与加载回执、任务结束及凭据撤销。当前没有最终验收或远端推送结论。

首次启动阶段的独立验收准备与只读 preflight 已完成：[只读 preflight 回执](evidence/rq5-original-dsh-20261008/independent-preflight.public.json)、[验收清单](evidence/rq5-original-dsh-20261008/acceptance-checklist.md)。输入、冻结上下文及来源绑定、原测试完整性、修改边界和 evaluator 排除核验通过；SQLite 只读连接 total_changes=0。功能、加载、DSH 工具和 OS 允许/拒绝均明确为未记录。验收脚本的 6 项纯 mock 自测通过，仅证明检查脚本准备就绪，不替代项目功能或内核验收。

## 短路径实际核验与新的生成阻点

新快照独立只读核验 21 项通过：20 资产 SHA/内部名/来源 manifest 一致，最长实际 canonical 路径 63 字节，完整 task 与 /s/0I reservation/device/inode 匹配，原 5 条接受约束及全部约束字段/原 prompt 保留，7 组旧记录摘要不变。见 [短快照独立回执](evidence/rq5-original-dsh-20261008/short-snapshot-independent.public.json)。

随后作业 5760fc2f3ba949ba84082bd7b8ad00d0 终止为 failed、零候选。目标来源已读，但草稿 evidence_ids 漏引；首缺项诊断及预算分类使多目标修复未完成。见 [独立问题记录](../BUG/BUG-20261008-Pi目标证据接线修复预算.md)。当前仅确认短路径恢复有效，尚无候选人工确认、加载、受管 DSH 或内核执行结果。

## 证据诊断修复与同任务重试

目标证据接线预检与未授权失败重试完成代码验收，完整后端 773 项通过（[日志](evidence/rq5-original-dsh-20261008/backend-regression-773.log)），独立复评无新增阻塞。生成诊断区分已读漏引/未读资产，不自动补引用、不改提示或权限。

重新载入 API 后 PID 1326221，Broker 966501/native 870966 保持不变；同任务新 Pi 作业 d09d1596c30d4feab23c56af32e2640b 关联旧失败作业，仍使用同一冻结快照 /s/0I/r/p。未另外创建逻辑任务或占用短根；[启动回执](evidence/rq5-original-dsh-20261008/same-task-retry-started.public.json)只证明已发起生成，不证明候选、权限或任务已完成。

## 真实候选与事实性退回评审

同任务重试 d09d1596c30d4feab23c56af32e2640b 已完成，服务端校验候选 25acb9848a5e4acf93ba62d281d4ab2e（hash ca0d5eefdf03f309a2e08f55513871cd166e9184bc882886cea9053b1ce0800f）compiled，无 unresolved；任务仍 version=0、无执行会话/绑定，effective=false。候选保护项目内三个现有测试及两项 config 的写入/删除；源码修复未被禁止。见 [候选公共回执](evidence/rq5-original-dsh-20261008/short-candidate.public.json)。这只是生成/校验证据，不是人工确认或实际加载。

独立复评发现：guidance 把外层 test_validator.py/tests_rate_limiter.py 称为 unreadable/unrelated，但它们已登记、磁盘 hash 与项目测试相同，该生成作业没有其读取成功或失败回执。未读不能推出不可读或无关。原始 task.md 指定项目 tests，不能据此自动扩大保护或要求用户重新解释原任务。原候选事实说明须退回 Pi 重新核对，不手改 DSL、不增加定向系统提示；native_admission 未给 DSH 发送该 guidance，当前也没有真实受管执行。

新增正式退回接口的 50 项测试、反馈投影的 22 项测试和其 13 项证据预检回归通过。独立复评指出队列提交与 managed 状态发布原先分属两个事务：若发布失败，新作业可能已存在而界面仍指向旧候选。该恢复窗口正在整改，尚未用本次新接口触发真实模型。只称反馈与 retry_of 原子写入 job，不称队列和 managed 状态整体原子。

## 退回闭环集成验收与真实新作业

恢复窗口整改后，退回/失败重试专项 110 项（70+40）通过，反馈投影 22 项通过；独立复评验证精确关联、幂等恢复、旧候选拒绝以及 worker 启动前协调。最终完整后端 `pytest -q tests` 为 **865 passed、5 现有 warnings**，27.83 秒，见 [日志](evidence/rq5-original-dsh-20261008/backend-regression-865.log)。最初裸 pytest 把原始 RQ5 场景测试误收为后端测试并遇其已知 import loader 错误；后端回归按明确 tests 目录运行，未改场景来消除该失败。

API 单独重启至 PID 1338852，Broker PID 966501 保持。正式退回端点在原任务 7411a201b87a4670、原 context hash、原 /s/0I/r/p 上创建新 Pi 作业 fed83ee2cbce4401a386984d1bc066e4，retry_of=d09d1596c30d4feab23c56af32e2640b，含候选事实反馈，无授权作用。旧候选与来源记录保留；当前仍 v0、无加载/受管会话。见 [部署回执](evidence/rq5-original-dsh-20261008/review-regenerate-deploy.public.json)、[退回作业回执](evidence/rq5-original-dsh-20261008/factual-regenerate-started.public.json)。新候选及真实执行验收待追加。

## 候选覆盖复评与短任务独立预检

真实反馈新候选 be1b4cabc11e448ca18ae685480fe21b 已校验/编译，旧 unreadable 无据事实说明消除；但独立评审发现漏掉项目 tests/__init__.py、扩大到外层副本，未呈人工准入。当前模型产物与上下文/来源无丢失，完整20资产未变。经正式端点创建同任务作业 4da18fc1e83341449f005f5e30fc8d0a，依据原任务补作事实与覆盖核对，无新授权。见 [独立 BUG](../BUG/BUG-20261008-Pi候选测试覆盖复评.md)。

为短根准备的独立验收脚本在控制面私有目录，13 项纯 mock 自测通过。随后只读真实预检 11 pass、4 not_recorded、0 fail，覆盖 full task→frozen storage→ready reservation/dev/inode、20输入/源/测试/config完整性、oracle排除、工作区未改、只读DB total_changes=0。加载、OS allow/deny 和功能测试四项明确未记录，未运行原始任务代码或 oracle。见 [短任务预检](evidence/rq5-original-dsh-20261008/short-task-preflight.public.json)。

## 通用匹配能力合同整改

再次真实生成 fe97cbfa3a59407cbf95b24c5e0ea4d8 声称整棵 tests 保护，但 DSL 只有裸目录 exact 两条，独立 ActPlane lower_path/BPF 源码证明未覆盖后代；仍未准入。根因包含原能力合同没有解释 exact 节点与 /** 后代的区别。补丁在 CAPABILITIES 增加明确 path_matching，并在 validate 返回顶层增加 registered_asset_coverage；同任务 hash有效资产、按 atom/operation/pattern 字面计数，裸目录0个登记文件命中如实显示，不入 proposal/context、不改 hash、不推断 statement、不自动补规则或放宽授权。

新 matching 专项7项与证据预检13项联合通过，独立复评与引擎源码逐项对照通过；最新完整后端 **872 passed、5 现有 warnings**，27.56秒，见 [日志](evidence/rq5-original-dsh-20261008/backend-regression-872.log)。独立 API 已载入修复 PID1345616，Broker966501保持；同任务正式退回作业2c64fafb8b49458a9eee322ccb279b2e已开始生成。见 [部署与生成回执](evidence/rq5-original-dsh-20261008/path-matching-regenerate-started.public.json)、[裸目录候选证据](evidence/rq5-original-dsh-20261008/bare-directory-candidate.public.json)。仍未人工批准或加载权限，真实DSH/功能/内核验收未完成。
