# RFC：控制台首页安全亮点公告

日期：2026-10-09。状态：已接入正式 React 首页并部署到 18003。

## 行为与职责

首页标题右侧展示「安全亮点」按钮。浏览器首次访问本公告版本时自动打开原生 dialog；叉号、Escape 或「知道了」关闭并记忆，按钮可随时重新打开。localStorage 键为 agentscope-security-notice-v2-seen，与独立设计预览隔离；存储不可用时仍可关闭和手动打开，但刷新可能重新展示。

公告有「执行与数据」「授权与流程」两组各六个案例，默认插件自行外联。每次展示一个具名用户的任务、涉及文件、入口或上下文 trace、系统或控制面 trace、行为关联和新增价值。三步过程与结果放在「案例过程」。两组分别记住当前选择，切换案例重置展开详情。X/Escape/确认关闭后焦点返回入口；模态期间背景不能交互，Tab/Shift+Tab 在公告内循环。窄屏上下排列 trace。

## 接口与安全边界

- SecurityNotice.jsx 只展示案例，不读取审计接口、不调用工具、不改变审批、加载、执行域或内核策略。securityNoticeCases.mjs 人工维护案例数据；React 文本渲染避免 HTML 注入；CSS 限定在 security-notice-dialog/sn-*，不修改其他对话框样式。
- 公告的 trace 是说明案例的事件序列，不是当前会话的实时采集、实际拦截记录或已验收成绩。产品正文以「案例」和具体人物过程表达，技术文档保留实现边界。
- 左侧可以是工具调用、应用事件、文件流转、会话摘要或审批过程；非工具场景不补造调用 ID。系统调用、内核钩子、对象解析、审批/加载与流程暂停分别标注，不统称内核拦截。
- 插件直接联网只有在插件运行于已绑定受管进程域时才能受该域规则约束，不能自动推广到受信 DSH 宿主或模型传输。文件信息流需实际覆盖读写与新建连接，不能据案例宣称 HTTPS 内容、已有连接、共享内存等全部覆盖。
- 验收回执绑定源码版本的发布门禁是能力设计示例，当前公告并未实现这一发布集成。审批快照、执行副本复核与 compiled/approved/loaded/active 各阶段仍按已有真实接口事实判断。
- 链接、已有 FD、映射、异步 I/O 与跨任务 IPC 等保证仍需各自真实操作验收；本 UI 发布不改变已有 BUG 的结论。

## 验证与发布

在隔离工作区构建并验收。运行分支现有前端回归 152/152；候选浏览器检查 20/20、18003 正式页面检查 18/18，覆盖 12 案例、关闭记忆、手动重开、键盘、423/320px 窄屏和原有导航入口。仅替换静态资源：发布前/切换前校验入口哈希，保留旧资源及入口备份，原子替换 index.html；不重启 API、Broker、DSH。

关联：[ADR](../ADR/ADR-20261009-home-security-notice.md)、[交互迁移评审](../REVIEW/REVIEW-20261009-home-security-notice-redesign.md)、[原公告验收](../REVIEW/REVIEW-20261009-home-security-notice.md)。

研究依据沿用既有评审：[ActPlane](https://arxiv.org/html/2606.25189v2)、[OpenAgentSafety](https://arxiv.org/html/2507.06134v1)、[GhostApproval](https://www.wiz.io/blog/ghostapproval-a-trust-boundary-gap-in-ai-coding-assistants)。本次是已评审案例的界面迁移，不新增论文结果或本机防护结论。
