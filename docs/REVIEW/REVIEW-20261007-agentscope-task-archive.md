# REVIEW：AgentScope任务档案最终评审与验收

日期：2026-10-07。状态：实现、真实权限闭环和最终页面验收完成；仅本地提交，未推送。

## 结果与证据边界

每个 task_id 一份档案，同来源工作区的新任务保持独立。原生 DSH 为来源和独立观察对象；受管 DSH 为经过人工审核、在隔离快照中执行的实例。历史 PID、加载回执不代表当前在线或当前生效。工具结果、内核拒绝、控制面记录和独立效果探针分别标识；审计覆盖已收集文件拒绝与独立影响，不覆盖全部系统调用。

| 真实阶段 | 独立事实 | 公开证据文件 |
| --- | --- | --- |
| v3 收紧 | domain410489984；已持有FD进程终止；保护哈希不变；7 deny/4 allow | restriction-applied.public.json、task1-restriction-probes.public.json |
| 未批准扩权 | PID942230/domain410489984写output被内核拒绝 | output-unapproved-probe.public.json |
| v4 扩权 | 新domain421785620/runner944897/executor944921；原SID和既有保护保留 | expansion-applied.public.json |
| 实际任务 | DSH修复代码，2项unittest通过，写出2540字节报告；v4 1 allow/4 deny | task1-final-acceptance.public.json |
| 并行实例 | 原生和两个受管实例身份独立；task2原文件完整；观察不增加Pi作业/DSH工具 | task2-acceptance.public.json |
| 结束撤销 | 两任务ended/effective=false，登记PID均dead、任务凭据全撤销；真实plugin gate200→401 | closed-acceptance.public.json |
| 历史图 | 结束后v3/v4可信任务DSL仍可读，live=false；缺底线材料如实报告；任务事件/作业数量不变 | archive-domains-after-close.public.json |

任务1为bef449047cd24af6，任务2为4821ac737a1a4f65。证据目录为[evidence/task-archive-20261007](evidence/task-archive-20261007/acceptance-boundaries.public.json)。v3旧凭据误用admin路由的401不作为插件重放证据；轮换撤销依权威记录，结束阶段才有真实插件前后重放。公开材料不含凭据值/哈希、私有推理或原始模型上下文。


后续入口修订：用户验收指出阶段名称隐藏运行前/运行时策略与OS审计，现已按REVIEW-20261007-history-policy-audit.md继续整改；本文件截图和静态hash表示9b3a0d4时点，最新发布以补充评审为准。

## 最终界面与连接

最终页面采用任务概览、准备与授权、执行与权限、结束与结果四个内部页签。字段、逐条约束和可筛选分页记录取代外露JSON；关键权限记录从全阶段提取，实际v3/v4加载及人工审核在第一页可见。no_change/guidance_only归为策略评估。

桌面和423×900实屏通过：页面宽度423，记录表和历史图仅各自在内部横向滚动；页签方向键只切档案内部栏目；刷新和浏览器后退恢复同任务档案；Escape关闭保留列表搜索/状态/页码，并在直接URL刷新后也恢复对应任务按钮焦点。详情返回保留原记录筛选和焦点。工作区文件抽屉显示真实7文件名称、类型、大小，刷新可恢复。

历史图真实切换v4/v3，节点就地显示标签、策略hash核验和该次加载DSL；历史PID不显示绿色。关闭后底线控制材料缺失明确显示“底线域加载材料未记录”，不补造D0或DSL。接口返回不完整/HTML时局部报错，不使整个档案空白。

API停止后手动检查立即撤销绿色并显示状态未知，恢复后原生PID未变。原生拒绝连接显示断开；历史失败/结束/headless任务不再占当前连接和当前任务选择器。TTL到8秒同时清connected/available，7.999秒与8秒边界已回归。

最终截图：archive-permission-records-desktop.jpg、archive-permission-records-423px.jpg、archive-historical-domain-423px.jpg、archive-historical-domain-dsl-desktop.jpg；此前文件抽屉、API故障和连接窄屏截图也保留。旧archive-423px-closure.jpg仅作为旧阶段锚点UI的历史证据，不代表最终页签实现。

## 测试与发布

完整后端410 passed、52 skipped、5 warnings，12.16秒，日志/tmp/a/task-archive-historical-final-backend.log；该次收集晚于TTL修改，包含最新源码。独立root探针权限8项、原生bridge7项通过；档案专项72项通过。前端最终51项通过、0失败，Vite构建通过。跳过项不计通过。

18003已运行隔离目录/opt/agentscope-task-archive-20261007源码，最终静态资源index-BVZOdasf.js/index-CKbQv6NF.css。真实测试任务已关闭，原生DSH保持在线。最终源文件与部署源90文件对照0变更/0缺失，普通业务Java和ActPlane本轮改动均0；未初始化gitlink不声明内部提交已核验。原有继承变更通过独立基线checkpoint保留，本轮功能提交与基线区分。

完整差异通过临时索引read-tree基线、add -A、diff --cached --check检查，覆盖新增文件；公开JSON按白名单导出。静态报告保留验证范围。长临时路径超过既有DSL64字节限制的诊断在BUG中保留，未放宽编译器。
