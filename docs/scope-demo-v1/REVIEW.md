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
