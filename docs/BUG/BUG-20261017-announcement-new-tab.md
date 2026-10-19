# 阅读公告错误打开独立页面（2026-10-17）

已复现：ProductOverview.jsx 将“阅读公告”写为 /value-announcement.html 的 target=_blank 链接。用户要求当前页面小窗阅读。

修复：入口改用独立只读 ValueAnnouncement 组件的原生 dialog，静态正文单一来源、头部关闭按钮与内容独立滚动；支持 Esc 关闭并归还焦点。原安全亮点、旧公告地址、策略与执行逻辑保持。

闭环：323 项前端回归、构建及 18003 桌面 / 实际 390px 窄屏浏览器验收通过，确认无新增标签页、正文可读至末尾、关闭后回到原总览。证据见 REVIEW-20261017-announcement-dialog.md。
