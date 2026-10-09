# REVIEW：ui-redesign 样式接入实际 Demo

日期：2026-10-09。

## 改动与来源

将本机 `C:/Users/happy/Desktop/projects/agentscope-ui-redesign` 的 `frontend/src/prototypeTheme.css` 接入实际运行的 `/opt/agentscope-task-archive-20261007`。该样式来自 ui-redesign 分支的 `8056794ef77c2936aed399e498fc393bfe33c7db`，当前本机源分支 HEAD 为 `34f2e85`。本次使用现有样式，不使用 frontend-design skill。

实际入口只增加样式导入和根元素 `prototype-theme` 类。移除这两个视觉接入点后，main.jsx 与原提交 `ef612de` 逐字相同。其他业务组件、内容、导航、事件处理、请求接口和后端均没有修改。DeepSeek Harness / Hermes 名称和 PID 列保留。没有合并 ui-redesign 分支较旧的业务代码或静态原型示例数据。

## 验证与部署

| 核验 | 结果 |
| --- | --- |
| 源样式一致性 | CSS 与 ui-redesign 源文件逐字节一致；SHA256：8dc9781af4eddadc24a6f2cd7f119f66a5771f25a0e86283e8f67d8b552388fe |
| 内容保留 | main.jsx 去除两个视觉接入点后与 HEAD 原文完全相同，改动仅有样式文件与两处视觉接入 |
| 前端回归 | node --test src/*.test.mjs：130 passed，0 failed |
| 构建 | Vite 71 modules，构建成功；保留原有大 bundle 提示 |
| 实际静态资源 | 18003 的 index.html 和构建产物逐字节一致，引用 index-_VyB5nR7.js / index-DSLHCQMK.css；部署文件与构建文件逐字节一致 |
| 服务可用性 | API 与 Broker 均 active，18003 首页 HTTP 200 |
| 部署范围 | 只替换独立 Scope Demo 的静态资源；没有重启 API、Broker 或 Agent，没有改动普通业务代码 |
| 浏览器验收 | 未通过工具完成：浏览器安全策略拒绝访问当前本机页面，理由为 URL 协议不被允许；没有绕过该限制，没有生成本轮实际页面截图，不宣称窄屏、六模块或弹窗已完成视觉复验 |

## 限制

此次可确认新样式已进入真实 Demo 的构建与部署产物、原有业务内容和代码行为未改。当前版本仍需用户在已有标签页刷新检查实际视觉效果，浏览器工具限制解除后才能补充本轮桌面、320/423px 与抽屉的视觉验收。此前 ui-redesign 独立预览的截图和检查结果不能代替此次实际运行版本的浏览器证据。


## Windows 持续访问补验

用户随后报告打不开。补验确认：WSL 没有前台驻留会话时退出，Windows 18003 被拒绝；短时 WSL 命令运行期间的 active/HTTP 200 不足以证明后续可达。已在受工具管理的前台会话保留 WSL 驻留，并重新检查 Windows 首页、JS、CSS 和状态接口。完整复现、处理及生命周期限制见 [BUG：WSL 驻留与 18003 访问](../BUG/BUG-WSL驻留与18003访问-20261009.md)。这是运行环境访问修复，没有改变样式、内容或业务代码；不新增运行时安全生效声明。
