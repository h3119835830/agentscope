# 模板详情只读展示验收

日期：2026-10-26。范围：前端展示；未发布到正式 18003。

- `wsl.exe --cd /mnt/c/Users/happy/Desktop/agentscope/frontend bash -lc 'node --test --test-reporter=spec src/*.test.mjs'`：429/429 通过。
- 同一 WSL 目录 `npm run build`：Vite 构建通过。
- `node scripts/preview_template_details.mjs`：127.0.0.1:18177，只转发白名单 GET，写请求全部拒绝。
- 浏览器逐个打开 37 个详情与 DSL 入口；17 完整、16 缺参、4 暂不支持。检查记录在 browser-checks.json。
- desktop.png：默认值与说明；dsl-preview.png：服务端 DSL；narrow-top.png / narrow.png：640px 单列和滚动区域。
- Esc 关闭恢复入口焦点；显式维护检查保留 git commit 和退出码 0，未保存。维护态原有预览 POST 被代理拒绝一次；正式写请求转发为 0。

对应 RFC / ADR / REVIEW / BUG 位于 docs 同名 20261026-AgentScope-template-detail-readonly 文档，已同步至用户指定技术文档目录。
