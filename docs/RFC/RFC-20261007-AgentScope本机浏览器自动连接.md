# RFC：AgentScope 本机浏览器自动连接

> 状态：已废弃。2026-10-07 用户要求直接删除登录流程，当前实现见 RFC-20261007-AgentScopeDemo删除登录.md。以下为历史方案及当时验收，不代表当前代码。

日期：2026-10-07。范围：18003 本机自用控制台入口。状态：已部署并通过入口专项验收。

## 问题与目标

一次性启动链接及 8 小时浏览器会话解决了启动器入口，但普通地址、新浏览器和会话过期仍落到管理员口令页。用户明确要求本机自用取消这一步。普通地址保留任务及导航参数，直接进入；会话过期后自动续接。

## 接口与边界

新增配置 AGENTSCOPE_LOCAL_BROWSER_AUTO_LOGIN，默认关闭；18003 的 scope-demo profile 显式开启，normalization profile 不开启，AGENTSCOPE_DEV_NO_AUTH 仍关闭。

GET /api/auth/mode 增加 local_browser_auto_login。POST /api/auth/local-browser-connect 仅在上述配置及原本机浏览器配置开启、请求 peer/Host 为 loopback、Origin 与服务完整同源、Sec-Fetch-Site 为 same-origin、自定义入口头为 1 且无 Authorization 时建立会话。跨源、非本机、携带任务或生成凭据的请求拒绝。

返回 HttpOnly、SameSite=Strict、/api 路径、8 小时会话 Cookie；数据库仅保存摘要，不向页面提供管理员口令。原票据入口兼容保留。控制 API 仍要求有效会话或管理员凭据；任务/生成 API 仍执行各自校验。

前端先读取模式；自用模式下自动连接，忽略已过期的旧启动票据并清理 URL fragment。普通控制请求 401 时仅在自用模式续接并重试一次，连接失败显示真实错误。自用模式显示“本机自用 · 免口令”，移除会让用户重新落入口令页的锁定按钮。

这是本机用户信任模式。Origin 和请求头防止其他网页跨源调用，不是对能够伪造 HTTP 的本机程序进行身份认证。DSH/Pi 的运行隔离与凭据边界继续独立承担其职责。

## 部署

仅替换 18003 私有 UI 并重启其 API；不重启 Broker、DSH，不恢复或执行已有失败任务，不修改数据库迁移、任务策略或普通 ERP 业务。RFC/ADR/REVIEW/BUG 同步维护。
