# 原版安全总览恢复验收

日期：2026-10-13，北京时间。用户要求先恢复旧版，再讨论应用层日志遗漏与内核观察的价值范围。

## 恢复与保留

以 db870f6 恢复原 SecurityNotice.jsx 和 securityNotice.css，保留两个分组、十二例、左右 trace、调用关联和案例过程；旧数据 securityNoticeCases.mjs 与该提交字节一致，SHA-256 `acbb44b19c46daaff2983a2c84ed1aa0e2c35632b226bbe873df9788ef8a1635`。默认恢复“没有工具调用，插件也在尝试外联”。

增加“示意案例”和页脚示意 PID/时序说明；既有示意图不冒充实测。移除后来增加的首页价值横幅。保留阅读公告入口、公告全文、真实状态读取/保护核验及可靠性整改。应用层可见性表述本轮不另作改写。

## 验收

259 项前端测试通过，Vite 构建通过；大包提示仍存在。本轮不改后端，未重复全量后端测试。

正式逐项切换执行组 script/link/integrity/revoke/plugin/dataflow 与治理组 isolation/approval/context/stale-receipt/snapshot/inactive，十二项标题和左右过程均恢复，示意标识均存在。默认非工具场景左侧为用户/应用事件，右侧为系统调用/内核事件。公告入口保留。

390×844 实测页面 scrollWidth 390；dialog clientWidth/scrollWidth 均 339，无横向溢出。Escape 关闭并归还“安全亮点”按钮焦点。临时 viewport 已恢复，原正式页保留在默认案例。

截图在用户技术文档 `research/security-overview-restore-20261013/screenshots/`：original-live.jpg、original-mobile.jpg；browser-checks.json 记录十二例和交互结果。

## 发布与运行

静态产物 `/opt/agentscope-value-guide-ui-20261013-113721`；备份及结果在对应 release-backups 目录。前后 API/Broker PID、start_ticks、三个实例 PID/generation/domain/策略、系统及 DSL 修订文档和 18000/18004 监听身份均保持。未重启服务或 Agent，没有策略变更、数据库回滚或 Git push。

发布后第 17 个观察样本，约 12.66 小时，issues 为空；三个保护均新鲜、队列及未完成调用为 0。24 小时观察仍为 observing，起止窗口保持 2026-10-12 22:57:30 至 2026-10-13 22:57:30。不能提前认定长期稳定性通过。

前一轮布局 RFC/ADR/BUG 已标为历史并指向本次恢复，避免文档与现行界面不一致。完整修改范围为前端和文档，普通业务与执行面未改。
