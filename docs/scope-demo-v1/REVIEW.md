# REVIEW — DSH 文件 Scope Demo 验收

日期：2026-10-05。结果：本地登记场景通过。源码分支 codex/scope-demo-v1，基线 9d54f92。未推送远端。

## 真实闭环

最终任务：eada0606a5014c9d。独立 Git commit：e01ee805c8adb7838aea6a455619db98f788e8b0。

|阶段|有效版本/执行域|独立结果|
|---|---|---|
|S0|v0 / 1677488583|28 项探针通过；仓库只读，runtime/tmp 可写，output 不可写。|
|S1|v1 / 783062933|29 项通过；backend/frontend 可写，tests/config/output 受保护；DSH 完成摘要修改。|
|S2|v2 / 783062933|29 项通过；同域收紧至 backend；frontend 写入、删除、目录改名及原有 FD 写入失败。用户消息 v2 后真实 waiting_constraint 工具边界暂停 1 次。|
|S3|v3 / 347020856|28 项通过；DSH 自己申请 output；拒绝不改变 v2，后续授权重启为新域，output 可写且 frontend/tests/config 保护保留。|
|S4|任务结束|runner/watch 退出，旧 API 凭据返回 401；新任务 7b8a52e15a204815 无本次授权。|

四个阶段的内核事件均为 root 所有，核验匹配 domain、probe PID/PPID；探针 UID 997 与 DSH 低权限执行身份一致。控制 socket 连接拒绝、原生插件与凭据非截断写打开拒绝探针均通过。源码与保护资产核验独立于 Agent 自报。

报告实际生成到 output/report.md，sha256：b9a6146fd18810767abb33d6ca77a8290c1534d2bf4d64447f20cede7d3e6860。真实任务 unittest 3 项通过；frontend 由 DSH 修改，tests/config 内容保持原样。公开检查点、工作区哈希和重启后工具执行可回查，当前完整 Scope 保留 3 条变更 lineage。

主要证据：/var/lib/agentscope-scope-demo/report/eada0606a5014c9d-full.json。此前 e548f52f1d7345fd、8ea01c0173654f74 亦有通过记录；最终结果依据上述补强后的新任务，复跑与评审发现的问题见 BUG。

执行环境：WSL 内核 6.6.114.1-microsoft-standard-WSL2；已安装 ActPlane 二进制 sha256：efe5c895cca03393ba6ec41c77835c9675d9a407a6378e7e96adafa4ff553749。证据对应此准备环境与二进制。

## 回归与界面

|验收|结果与覆盖|
|---|---|
|完整后端回归|167 passed；保留原 139 项基线，新增 28 项 Scope 状态、权限、凭据、故障与接口隔离用例。5 项已有弃用告警。|
|DSH 原生工具门|4 passed；上下文更新、收紧等待、失败阻断、取消及开始快照传递。|
|真实任务功能|3 passed；多空格、空文本、换行。报告与摘要另由文件/哈希回查。|
|独立文件探针|S0—S3 合计 114 项通过；合法读取/写入、违规写入/删除、脚本间接写入、已有 FD、目录改名、符号链接、控制 socket 和原生运行资产保护。|
|候选与故障|未批准、拒绝、过期版本、消息/进程漂移、重复及跨任务请求不切换指针；加载后核验失败、启动失败、旧凭据失效和新任务不继承通过回归。指导/扩权不能跳过待落实的收紧；已核验探针不被解释为 Agent 需求。|
|RQ5 补充回归|既有配置保护、禁止修改测试素材及 RQ5 运行期禁止绕路接口保留并通过完整后端回归；本次真实内核证据来自自定义 Demo，不冒充新的 RQ5 六组模型评测。|
|前端|Vite 构建通过；桌面、423px、页签切换、方向键、Escape/焦点返回、刷新任务恢复通过；浏览器 pageErrors 为空。|

界面截图与浏览器 JSON 已同步到技术文档 REVIEW/evidence/scope-demo-20261005/final。评测器及该验收驱动未挂载到 Pi/DSH 任务输入；任务自己的只读测试属于公开任务资产。

结束后独立读取权威数据库：未撤销任务凭据 0、有效生成凭据 0、phase 为 ended；补充记录为 scope-closure.json。导出的 scope-full.json 与源码暂存内容均检查过，无管理员口令或模型凭据泄漏。

## 边界与后续

这是已准备主机上的本地文件 Demo。动态网络权限、远程 Agent enforcement、自动历史晋升和任意目录授权尚未纳入。Broker 重启须先关闭任务；应用状态未知时结束重建，尚未实现自动接管或回滚。公开检查点续接不宣称完整原生会话回放。

修改均限 AgentScope、DSH/Pi 集成、合成项目和文档；无普通采购/销售/库存/财务代码或业务数据库变更。独立端口 18003、数据库/profile/UI 分离，既有实例保持服务和原有数据。

## 本机一键进入修正

用户要求无需输入管理员口令直接打开，增加受信任本机启动器、一次性启动票据和独立浏览器会话。原匿名控制接口仍关闭，DSH/Pi 的任务凭据不能签发票据或审批；票据不可复用、会话到期/退出失效，跨源写操作拒绝。

新增 10 项身份边界测试，完整后端回归 177 passed（5 项已有弃用告警）；Vite 构建通过。全新 Chrome 浏览器没有预置管理员口令，启动链接进入工作台、地址清除票据、HttpOnly 会话、刷新恢复、桌面/423px/键盘/弹窗焦点均通过，pageErrors 为空。证据在 REVIEW/evidence/scope-demo-20261005/browser-entry。本次只修改访问入口，S0—S4 文件执行证据沿用上述真实验收，不宣称重新运行内核流程。

用户当前 Codex 浏览器已显示 eada0606a5014c9d 的任务工作台和完整权限记录。日后可再次运行 Open-ScopeDemo.cmd，自动建立新浏览器会话。

## 工作台信息与视觉重做

用户指出页面混乱、不简约，记录外侧文字太多。本轮重做任务标题、简约导航、真实五阶段路径、
权限表、审核抽屉和分页记录；不更改权限管理后端或第三方 DSH。

调研主来源：
- Anthropic frontend-design：明确设计方向、对照需求、实现后截图评审。
  https://github.com/anthropics/skills/tree/8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/frontend-design
- Impeccable distill：参考信息层级和渐进披露，未安装/运行其引擎或 hooks。
  https://github.com/pbakaus/impeccable/blob/main/plugin/skills/impeccable/reference/distill.md
- UI UX Pro Max：比较其设计系统与可检索规范；本轮采用前两者的轻量工作流，未引入其运行工具。
  https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

frontend-design 已通过官方 skill-installer 安装到用户技能目录。技能辅助设计，不代表满意度保证；
交付判断来自用户需求与实际页面验收。设计取舍、颜色/字体/布局和信息合同在 DESIGN.md。

|本轮验收|结果|
|---|---|
|完整后端回归|177 passed，5 项原有弃用告警；未修改后端。|
|权限展示投影|12 passed：批准不生成生效阶段、提前结束不补齐阶段、版本/消息/进程过期不能批准、并发应用不能再批准、失败不冒充生效、拒绝收紧仍等待、探针/Agent/自报区分、待落实收紧阻止扩权审核、no_change 不声明重启。|
|实际服务页面|全新浏览器免口令进入；结束任务五阶段记录、六类权限、历史标签、结束不可审批、审核原始说明折叠、记录最多八条且长路径/JSON不外显通过。|
|交互与窄屏|桌面/423px、记录分页/筛选、Escape焦点返回、页签方向键、切换真实待开始任务后刷新恢复通过；页面无横向溢出，pageErrors=[]。|
|历史数据回放|用既有真实 S1/S2/S3 数据在浏览器测试中拦截 API 回放五项状态：提交要求绑定有效基础版本、扩权待审差异、过期不批准与澄清原文保留、拒绝后收紧仍等待、应用失败仅显示历史。回放未批准或改变任何真实权限。|
|构建与隔离|独立 Demo Vite 37 模块；其他实例 UI 从既有基线 34 模块恢复。无新增前端依赖、模型特例提示词、普通业务代码改动。|

截图及 scope-ui.json 在技术文档 REVIEW/evidence/scope-demo-20261005/workbench-redesign。
scope-pending-review.png 为历史数据回放画面，其余结束任务与任务切换画面读取真实服务。
本轮没有重跑 S0—S4 内核执行，真实 enforcement 证据沿用前述 eada0606a5014c9d 验收。

## 新一轮真实执行与页面验收

用户要求真实验收后，新增并完成任务 2dd1a93efac64749；本项重新运行 Pi、DSH 与内核，
没有浏览器 API 回放或注入。十个实际检查点覆盖冷启动、授权待审/生效、收紧待审/生效、
扩权待审/拒绝/重新待审/生效、结束；待审保持旧 Scope，拒绝保持 backend-only，
抽屉差异与操作状态符合真实 API。桌面及 423px、短记录、焦点返回均通过。

|阶段|有效版本/执行域|独立文件探针|
|---|---|---|
|S0|v0 / 840160381|28 passed|
|S1|v1 / 1459409443|29 passed|
|S2|v2 / 1459409443|29 passed；已有 frontend FD 无法写入|
|S3|v3 / 1295285617|28 passed；换执行域/进程代次且保护项保留|
|S4|ended|凭据撤销，未撤销任务凭据为 0；新任务 5bdc3f77c3be4dfd 不继承|

114 项探针全部通过，内核事件为 root 所有，四阶段 protected_integrity 全部为 true。
DSH 实际修改摘要、恢复公开任务进展并生成 output/report.md；独立 unittest 3 passed，
旧任务 token 返回 401。任务 commit 为 7f9ef91c6d4f37f62ff0c80ee0d1889a6a5a3f81，
报告 hash 为 bb843cdf363ff185887da36bc1ce41698c3421d9184de614f8292fbe1f075728。

完整后端 177 passed（5 项已有告警）；展示投影 12 passed；独立 Vite 37 模块构建与共享
旧 UI 34 模块恢复通过。真实结束页另通过免口令、HttpOnly、票据清除、任务来源、
键盘/抽屉、分页、切换真实待开始任务与刷新恢复验收；fixtureReplay=not run，pageErrors=[]。
18000/18001/18002/18003 的 health 均为 200，无其他实例数据或普通业务代码改动。

证据位于技术文档 REVIEW/evidence/scope-demo-20261005/live-workbench：
scope-live-ui.json、scope-ui.json、scope-full.json、scope-execution-summary.json、scope-closure.json
及各阶段真实截图。完整报告导出前检查未包含私有环境中的管理员/模型凭据值。
审核由用户授权的固定范围测试驱动完成，不宣称这十个检查点由真人逐项点击审批。

RQ5 预检验证 28 个源文件 hash 与现有映射后的评分器前置布局；原始素材布局不直接满足
旧 evaluator，修正映射已在现有 adapter 中保留。预检不运行 Agent/内核，也未计算公共
benchmark 分数。公开 RQ5 动态 Scope 适配与 SWE-bench 实例执行尚未完成，选择依据见 BENCHMARKS.md。

## 授权方向与 DSH 连接可观察性整改

用户指出逐渐放宽与现有收紧步骤似乎相反，并无法判断正在做任务的 DSH 是否已连接。
核对实际实现和 ActPlane §3.4：任务层扩权由可信控制面换完整策略包/新执行域；同域追加
限制不能放宽继承约束。两者方向和作用层次不同。收紧是用户要求的可选分支，当前界面
已明确标注；没有改写旧轨迹或将单一固定 Demo 声称为任意目录授权平台。

连接详情复用真实进程观察、公开工具结果、上下文送达和内核事件。顶部服务提示改名；
进程退出/未知不称为执行中，旧域工具回传和结束时间戳不称为当前在线。仅受管 DSH 接入；
工具 gate 等待回查 400ms、后台内核采集 750ms、页面刷新 3 秒。无独立空闲心跳或推送，
不能根据静默判定 DSH 失联。长技术证据仍折叠，主界面没有新增日志堆叠。

新任务 80c4abb52c634c16 重新执行真实 Pi、DSH、内核及十个页面检查点，apiReplay=false。
S0 v0 域 372952641；S1 v1 域 1514193394；S2 v2 保持 1514193394；S3 v3 新域 1856618066。
28/29/29/28 项文件探针共 114 项通过，内核事件 root 所有，保护资产完整性均为 true。
公开事件窗口中取得 43 条工具结果、3 次上下文送达、2 次暂停和 2 个检查点；此计数不是
全部系统调用或完整历史。实际任务 unittest 3 passed，摘要变更及 output 报告确认，旧凭据
返回 401；固定任务 commit 为 60dae0d4f851332756429ce8bba8aed5fea7c1ab，报告 SHA256 为
a4f724859c89a8dff0797993f9344beb6aea59403b65ee8d4d20bb4834e778a4。

结束后 effective=false、未撤销任务凭据和有效生成凭据均为 0，无 DSH 进程。新任务
a748ba14cd3e4604 无继承授权。审核仍由用户授权的固定范围测试驱动扮演审核者，不宣称
Pi/DSH 或真人逐项点击批准。真实运行截图记录当时状态，不能证明已结束任务现在在线。

本轮完整后端 177 passed（5 项原有弃用告警），纯展示反例 16 passed。独立 Vite 37 模块及
共享旧 UI 34 模块构建通过。最终页面另验收桌面/423px、历史回传、当前 PID 的缺失/存在、
键盘、详情焦点、任务切换与刷新；fixtureReplay=not run、pageErrors=[]。最后的可选收紧
标签和未知进程状态投影修订后重复纯展示与结束页面验收；没有重复声称新的完整执行。
18000/18001/18002/18003 health 均 200；不修改后端、第三方 DSH 或普通业务代码。

证据：技术文档 REVIEW/evidence/scope-demo-20261005/dsh-connection 下的 scope-live-ui.json、
scope-ui.json、scope-full.json、scope-execution-summary.json、scope-closure.json 及阶段截图。
完整报告导出前检查私有环境凭据值未出现。现阶段仍缺空闲心跳和任意手工 DSH 自动接入，
不能将这次展示修正描述为实现上述能力。

## 2026-10-06 固定公共导航与 URL 状态

用户确认以完整左侧工作区导航和顶部面包屑作为固定布局。此前只在 Scope Demo
隐藏侧栏的选择已废弃：全部七个模块复用同一公共壳层，侧栏折叠仍由用户控制，
650px 以下统一进入紧凑模式。公共顶栏沿用真实语义“执行后端可用”。

App 统一持有 view/section/task，模块、历史策略库页签和任务切换同步到浏览器历史；
刷新与 popstate 恢复真实选择。ScopeWorkbench 的任务选择受同一状态控制，切换任务
时清理旧详情和页签。运行时 Scope/Agent 接入在原模块内选择任务，明确打开启动审核
的入口才跳转。未修改控制 API、审批、凭据、策略、DSH/Pi 或 Broker。

|验收|本轮结果|
|---|---|
|私有前端构建|Vite 38 模块通过，仅更新 /var/lib/agentscope-scope-demo/ui；未重启 API/Broker/DSH，未修改共享旧实例 UI。|
|七模块桌面导航|实际 18003 服务、全新浏览器会话；七模块侧栏都为 244px，面包屑/选中项/URL 一致，各自刷新恢复正确。|
|423px 窄屏|七模块侧栏保持可用，统一紧凑模式，页面无水平溢出。|
|浏览器历史|模块、历史策略库二级页签和任务选择的后退/前进、刷新均通过；运行时切换任务保持 runtime。|
|侧栏偏好|折叠后切换模块、刷新仍保留；恢复桌面后可手动展开。|
|既有 Scope UI|真实已结束任务与待开始任务的切换、权限/连接详情、短记录、审核、键盘、焦点、窄屏通过；五个历史状态回放用例通过。|
|展示状态回归|16 项 scope_view.test.mjs 通过，包括未核验不宣称生效、结束/旧域回传与进程存活区分。|
|页面与读取请求|两套浏览器验收 pageErrors=[]；七模块导航的 failedReads=[]。|

scope_ui_acceptance 的历史状态回放使用此前已公开的 Windows 证据镜像；虚拟机
root 保护的原报告不能由普通账号通过 UNC 读取，未放宽任何报告目录权限。

本轮不重新运行真实 DSH/Pi/内核生命周期，也不将历史回放或导航通过计作新的内核
验收。既有运行执行证据保持其原始日期和结论；本轮完成的是公共导航与页面恢复修复。

证据：技术文档 REVIEW/evidence/scope-demo-20261006/navigation/navigation-ui.json、
navigation-scope-desktop.png、navigation-history-desktop.png、navigation-scope-423.png、
navigation-history-423.png；scope-regression/scope-ui.json 和对应页面截图。

修改仅限 AgentScope 前端、UI 验收脚本及 RFC/ADR/REVIEW/BUG/DESIGN 文档；
没有普通业务 Java、业务数据库迁移或跨服务接口变更。完整 diff 已按此边界核查。
