# REVIEW：首页安全场景公告

日期：2026-10-09。状态：首页公告已实现、静态发布与真实页面验收通过；场景攻击验收不在本轮范围。

## 范围

总览接入 `SecurityNotice.jsx` 与 `securityNotice.css`。六个场景解释工具调用视角与真实安全边界的差异；扩展详情列出新增价值、验证依据与能力边界。公告无 API、审批、策略加载和执行操作。

发现共享源目录有另一项 Agent 连接界面修改，已将公告三个文件完整移到独立工作区 `/home/happy/projects/agentscope-home-security-notice-20261009`，并逐字核对共享 `main.jsx` 恢复为原基线；另一项修改保留。此前共享目录构建产物不作为发布物。

## 安全复核

已检查现有 BUG/REVIEW 中内核覆盖、已有句柄、可写映射和真实执行证据的限制。公告采用场景说明和防护目标，不将论文实验、编译通过、服务健康或历史记录记为当前保护效果。没有新增已复现内核漏洞，不新建虚假的 BUG 关闭记录，已有 BUG 状态保留。

## 验收

- 保留并集成已发布的 `b05ee34` 原生 Agent 打开入口，再从独立工作区构建；最终前端 Node 回归 152/152，通过。最初隔离基线的 145 项与后续 152 项不是新增公告测试数量。
- Vite 最终构建 77 modules，通过。入口引用 `index-m1hCfqCK.js` 与 `index-Bhc_AFoB.css`；通过 HTTP 回读确认与构建文件 SHA256 一致。现有大 chunk 提示保留，未调整打包策略。
- 浏览器检查 32/32，通过：六个场景与三类详情、默认折叠、整体收起/展开、方向键/Home/End 和焦点、有效页签/面板关联、仅首页展示、既有导航与四个指标保留、真实构建资源、无脚本错误。
- 实际视口 1280×720、423×900 均检查，无水平溢出。手机可切换场景与展开能力边界。临时视口已复原，首页标签保持可见。
- 发布采用入口哈希校验、保留旧哈希资源及原子替换入口。首次发布前检测到另一项界面正在部署，停止覆盖；待其提交后集成该基线，重新构建发布。
- 首页、health/status/dashboard/tasks/agent-instances 六个 GET 均为 200。API PID 8108、Broker PID 7613 保持，原生 DSH 页面仍报告原 PID 8401；本轮没有任何服务重启或 Agent 启动。
- 公告无 API、权限或执行调用；完整 diff 限定为首页组件、局部样式、两行总览接线、三份技术文档及公开验收证据，没有普通 ERP 业务变更。

页面验收只证明公告展示，不代表六种攻击已经执行或拦截。没有批准、加载或修改安全策略。

证据：[浏览器检查](evidence/home-security-notice-20261009/browser-checks.json)、[发布回读](evidence/home-security-notice-20261009/deployment.public.json)、[桌面截图](evidence/home-security-notice-20261009/overview-desktop.png)、[手机截图](evidence/home-security-notice-20261009/overview-mobile.png)。

关联：[RFC](../RFC/RFC-20261009-home-security-notice.md)、[ADR](../ADR/ADR-20261009-home-security-notice.md)、[已有 BUG](../BUG/BUG-20261007-DSL规则归一化与重叠校验.md)。
