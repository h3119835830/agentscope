# 策略 Agent 自主浏览与正文选择验收

日期：2026-10-16。源码基线：`c485c019549c630208a62439460be231dfbbb4a4`，保留已发布统一策略目录及审批改动。隔离工作分支 `codex/policy-context-agent-20261016`，目录 `/home/happy/projects/agentscope-policy-context-agent-20261016`。未推送远端。

## 结果

用户只输入中文场景即可生成已有模板子配置，界面不要求填写参考路径。模型自主决定目录和正文读取，实际结果进入下一轮上下文。最终策略须由用户核对；提审、批准、应用保持独立，读取与生成不会改变运行策略。

后端 `pytest tests -q --disable-warnings --tb=short`：**1,353 passed，5 warnings**；前端 `node --test frontend/src/*.test.mjs`：**310 passed**；Vite 构建通过，134 modules。新增后端 36 项，覆盖真实 fd 读取、目录分页、 typed/真实 DSL 拒绝、跨实例/额外工具拒绝、目录先行反馈、累计预算、全部来源新鲜度、超时与并发幂等。前端覆盖场景直接提交、系统范围不扫描、忙碌状态、实际依据/拒绝/无正文展示及旧记录兼容。

首次直接在 backend 根目录运行 pytest 误采集了业务攻击样本中的测试文件，因样本包不在 sys.path 而报 2 个导入错误；改用项目正式 `tests` 目录。首次正式目录回归为 1,257 通过/93 环境错误，均因历史测试依赖的 `/tmp/a` 不存在；只补齐临时目录后完整回归全部通过，没有修改产品代码绕过测试。

## 真实模型与 HTTP

运行 `/opt/agentscope/.venv/bin/python scripts/accept_policy_context_agent.py`，启动独立 18156 API、临时数据库、合成中文项目，关闭实例/历史/执行 worker，Broker 指向不存在的隔离 socket。未启动原生 Agent、未应用策略。模型配置只在内存中取用，不打印凭据、私有推理或真实业务资料。

场景：“请根据这个项目的业务说明，为订单日报配置资料隔离，保护不参与统计的员工资料。只使用已有模板，不增加无关限制，名称用中文。”用户没有提供路径；员工名册路径在测试时随机生成，必须从实际资料中获得。

最终代码测试记录：**4 轮、6 次接口调用、4 个文件、315 字节、4.548 秒**，仅为单次样本，不是性能统计。过程为根目录浏览 → README 正文 → people/sales/docs 三个目录浏览 → 业务说明、员工名册和订单样本正文。生成已有 **FILE-READ v2**，目标 `/w/0/people/roster_496710.csv`。目录过滤了合成 .env 和链接。模型读取了全部 4 份允许的合成资料，不能宣称最小读取。

同键重试返回原子配置；修改决定性正文后，旧请求返回 409。隔离 Agent 保持未启动，DSL 与运行权限无变化；正式 API/Broker、实例权限和其他端口在此次测试前后完全一致。完整结构化记录在仓库 `docs/REVIEW/evidence/policy-context-agent-20261016/real-provider-api.json`。

## 正式更新

**已发布并通过正式 HTTP 与保护复核。** 部署代码提交 `5ae0bb404373b8abf4e95e3eb62d5d3ee50c5913`（主功能 `65ddde5`），正式目录 `/opt/agentscope-policy-context-agent-20261016-113618`。仅 API 更新重启，完成健康与身份检查用时 1.361 秒（不是客户端端到端延迟统计）。API PID 50675，Broker PID 443 未变。发布脚本核对此前实时应用代码为 `2a026fb666d57e36c034fec39567b26f1037ca0d`，实时 UI 与后续统一目录源工作区构建一致；没有从旧正文读取版本覆盖后续统一目录。仅覆盖应用代码、固定读取程序与主界面，Broker、DSH、集成和引擎文件完整保留。

发布前检查无进行中的生成/租约/策略更新，实际 Broker 保护和队列正常，冻结活跃实例 PID/start ticks、generation、策略与执行域。两个活跃实例 PID **4427 / 4712**、各自 start ticks、generation、policy hash、domain 均未变化；其余非活跃实例也未启动或恢复权限。发布后再次核对 Broker 进程、完整实例权限/DSL 和保护状态与发布前一致，队列空，18000/18004 监听保持不变。未停止/重启 Agent、未恢复权限、未应用新策略，也未恢复数据库快照。

第一次发布阶段 `/opt/agentscope-policy-context-agent-20261016-113510` 的不存在实例探针错误预期 HTTP 404，实际沿用既有 invoke 合同返回 409；探针触发了自动代码/UI 回滚，未恢复数据库。回滚后核对：Broker 进程、全部实例权限与两个活跃实例的 PID/start ticks、generation、策略和执行域完全一致，保护正常。已修正发布探针并新增接口合同测试，新增测试文件现为 **37 passed**。产品代码未因此放宽权限或改 HTTP 合同；完整回归仍为上文的 1,353 项，新增合同测试单独通过。

Windows 侧 `localhost`、`127.0.0.1` 健康接口均 200；主页面及 `main-DzbcrIEj.js` / `main-BXhQ6kVe.css` 均 200，页面入口哈希与构建一致。新目录接口对不存在实例按既有合同返回 409，27 个已发布模板保留。正式实例没有执行模型生成或正文读取；这些验证使用隔离合成项目。发布后 API 的 error 级 journal 无新记录。脱敏发布汇总在 `docs/REVIEW/evidence/policy-context-agent-20261016/publication.json`，同时同步至中央文档 evidence 目录；私有数据库与原始运行快照备份保留在 `/var/lib/agentscope-scope-demo/release-backups/`，不进入 Git 或技术文档。

## 边界

本轮验收证明资料选择与模板参数链路，不替代某项策略的真实内核拦截验收，也不保证每个场景语义正确或读取最少。现有降权身份、允许文本类型及保守 DSL 守门适用范围见 RFC。没有修改 Hermes/Java/业务数据库，没有使用 computer use；未做像素级浏览器验收，界面证据来自组件交互、构建与正式 HTTP 资源检查。
