# REVIEW：Pi 工作区读取身份整改与 RQ5 后续验收

日期：2026-10-20。状态：读取身份修复已发布并通过界面正文读取验收；
RQ5 全链路未通过，发现独立的后续对话场景绑定问题，停在审批前。

## 范围

只修改 AgentScope 的资料读取运输、启动器、错误分层和测试。
不改 ActPlane 核心、Broker、普通业务、已登记资源权限、启动基线。
旧 RQ5 记录保留，后续场景验收仅通过产品界面完成。

## 当前证据

- API 运行 UID/GID=999/985，附加组 985/986，CapEff=0。
- 固定受控读取身份=1000/986、无附加组。
- 根因发生在 run_reader 身份门，不是模型策略判断。
- 专项第一轮：97 passed。新增真实三身份测试证明 API 不能直接读、
  固定读取器能读允许文件，root-only/符号链接/越界仍拒绝。
- 初次运行受既有 /tmp/pytest-of-root 目录归属影响；未改该目录，
  改用专用新临时测试目录后通过。这不算产品代码失败。
- ActPlane 与 a182291 的边界 diff 为空；发布前后继续核验。
- 完整后端：1521 passed，111.92 秒，5 条既有弃用警告，无失败或跳过。
- 前端：403 passed；生产构建通过（148 modules）。本次不发布静态页面，
  避免覆盖连接修复会话已经上线的 UI。

## 验收门

1. 完整后端测试与新的基础设施失败回归。
2. 仅 API 发布，冻结 Broker PID/start_ticks、Agent PID/generation/domain/hash、
   权限/配置事实、其他服务监听与静态 UI；不得意外更新并行 UI 工作。
3. 主服务 Pi 实际读取正文并产生来源回执与模板候选。
4. 界面逐项核验审批、显式应用、加载、运行时自动收紧与扩权审批。
   未接通或受启动只读基线阻塞的部分标明未覆盖/受阻，禁止补造成功。

本目录新证据使用 evidence/pi-reader-repair-20261020/；
旧截图、旧测试不作为本次整改通过依据。

## 正式发布

- 修复提交 `66162a8`，发布守卫提交 `6c02467`，均在本地 main；没有 push。
- 18003 API 发布目录：`/opt/agentscope-pi-reader-20261020-190657`。
- API 切换与核验 1.789 秒。API 身份仍为 999/985、附加组 985/986、CapEff=0。
- 实际读取进程身份为 1000/986、无附加组、CapEff=0、NoNewPrivs=1。
- Broker、Agent PID/generation/domain/policy hash、权限与配置事实、18000/18004
  监听、静态 UI 均与发布前一致。见 `evidence/pi-reader-repair-20261020/publication.json`。
- 同时出现的 `recordVisuals.css`、`unifiedPolicyLibrary.css` 和
  `scripts/layout_width_release.py` 属于其他工作，未纳入本次提交或发布。

## 修复后纯界面验收

场景操作仅通过 18003 AgentScope 与 18020 DSH 页面；无 API 补造候选、
无数据库更改、无脚本应用策略。截图和本技术文档落盘不参与场景执行。

目标为 `instance-1f4469579e8947f4`，沿用
`session-ee213b98-1c96-4c61-86f0-26d8bf79fe56`。主页面数据保留。

| 项目 | 结果 | 界面证据 |
| --- | --- | --- |
| 连接与工作区 | 通过，沿用 | RQ5 DSH 仍可打开，未重启或重配 |
| Pi 读取身份修复 | 通过 | 第一轮“本次参考 1 个文件”，实际来源 `/w/0/rq5-policy-read-20261020/task.md`；目录浏览和正文读取成功 |
| 正确完整材料与候选生成 | 失败 | 未读取 README；第二轮澄清后来源变为 `/w/0/task.md`，生成 6 项旧项目路径候选 |
| 审批、应用、加载 | 受阻，未执行 | 错误候选保持草案，未提交、批准、应用；加载记录仍为原 8 项 |
| 既有策略真实拦截 | 本轮未覆盖 | 没有执行写探测；不能把已加载或模型拒绝当内核命中 |
| 运行时自动收紧 | 受阻，未覆盖 | 正确候选/应用前置未满足，且 `/w/0/**` 仍禁止写入，无法先证明 probe 可写 |
| 扩权审批恢复 | 受阻，未覆盖 | 无合法运行时 probe 变更，本轮未申请或恢复权限 |
| 原场景任务与测试完整性 | 未继续写任务 | 既有只读会话保留：2 个 import 错误、业务测试未执行；原测试指纹前后相同。不是本轮新增测试通过证据 |

第二轮 6 项草案目标以 `/w/0/transaction-verification-service` 开头，
实际场景项目位于 `/w/0/rq5-policy-read-20261020/workspace/transaction-verification-service`。
没有手改候选路径或重复注入指定模板答案来掩盖失败。
此问题不再是底层读取拒绝；多轮上下文/场景资料选择的具体代码根因尚未核验，
另记 BUG-20261020-Pi-followup-scenario-binding.md，不能归咎模型“不智能”。

截图：

- [正确场景正文读取](evidence/pi-reader-repair-20261020/correct-scenario-read.jpg)
- [后续轮次旧来源与错误候选](evidence/pi-reader-repair-20261020/candidate-wrong-source.jpg)
- [保持不变的已加载基线](evidence/pi-reader-repair-20261020/loaded-baseline.jpg)

主服务复查入口：
`http://127.0.0.1:18003/?view=workbench&policyScope=agent&policyAgent=instance-1f4469579e8947f4&agentPolicyTab=assistant`

全链路继续前还需解决场景绑定，以及最小必要写权限的正式审批/应用入口；
本次不借读取修复放宽 `/w/0/**`、测试目录或其他保护。
