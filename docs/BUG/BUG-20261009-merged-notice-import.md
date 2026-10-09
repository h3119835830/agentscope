# 自动合并产生重复公告导入导致构建失败

日期：2026-10-09。状态：已修复并通过构建验收。

复现：把 main 的公告发布提交与当前控制台功能分支合并，frontend/src/main.jsx 同时保留文件首行和样式导入后的 SecurityNotice import。Git 不产生文本冲突，但 Vite/esbuild 报 The symbol "SecurityNotice" has already been declared。

修复：仅删除文件首行重复 import，保留功能来源已有的单一导入和公告组件。未更改公告交互或首次访问行为。

验收：163 项前端测试、17 项脚本测试、Vite 生产构建通过；后端全量 859 通过、52 跳过。最终 JS/CSS 资源名与此前通过在线验收的构建一致。参见 [合并发布评审](../REVIEW/REVIEW-20261009-main-windows-publication.md)。
