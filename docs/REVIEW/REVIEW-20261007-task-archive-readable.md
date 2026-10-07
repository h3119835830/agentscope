# 任务档案可读性验收

本次字段表改动位于 TaskArchive.jsx、TaskArchiveDetails.jsx、archiveRecords.mjs、archiveRecords.css、archiveRecords.test.mjs；档案列表主体保留。同步接入独立 ArchiveDomains 组件，并补充不完整 graph 响应的局部错误保护。未改任务源码、权限执行规则或普通业务。

前端 src/*.test.mjs 共 51 项通过，0 失败；Vite 构建成功（52 模块）。独立构建目录 /tmp/agentscope-archive-readable-20261007/dist，资源 index-C_B5QABt.js、index-CKbQv6NF.css。git diff --check 通过。其余主会话后端/DSH 的测试结论不计入这份 UI 验收。

浏览器读取真实 18003 API，并在独立 18023 静态预览验收最新构建：

- 原截图任务 4821ac737a1a4f65 的概览改为字段摘要、6 项约束表；中文译文、来源与作用对象分别列出，英文原文折叠。来源 native-dsh 与受管执行实例明确分列。
- bef449047cd24af6 执行阶段默认 15 条关键权限记录，包含早先 v3/v4 加载回执；不受最新 50 条普通记录影响。无需调整权限的评估仍在全部记录。
- 搜索 settings.json 得到 1 条操作效果核验；详情正确显示“操作效果已核验：否”“操作成功：否”，不把独立探针标成 DSH。原始 JSON 默认不可见。
- 详情返回恢复原行焦点。分页到第 2 页；继续载入由 50 增至 100 / 238 条，类型和结果筛选匹配 14 条。结束阶段的内核记录为 0 / 0，显示明确空状态。
- 历史域、进程与 DSL 展开实际 API；v4 任务域421785620 的 hash 核验与 4439 字符 DSL 可就地展开；历史 v3 可选择，图中的 PID 明确标历史。
- Escape 关闭恢复 html/body overflow；423×900 窄屏的页面、弹窗宽度均423，表格仅局部横向滚动，窗口尺寸已恢复。

子会话验收时的静态发布：主会话已把当时构建发布到18003。本 UI 会话随后独立重新打开18003，核验实际加载 index-C_B5QABt.js，原截图任务字段表无默认 JSON；多版本任务15条关键权限回执正常显示v4/v3。overview.jpg、records.jpg已更新为实际18003页面截图。临时18023预览已停止，验收页已关闭，窗口尺寸已恢复。本UI会话未重启后端/DSH，未提交或推送，整体本地提交由主会话负责。

风险与限制：搜索只覆盖已载入内容并显示数量；关键权限摘要最多20条，完整历史在全部记录；未知来源不猜测；历史加载不等于当前强制执行；固定约束词条译文不改变权限合同，任意模型文本保留原文。历史域接口未部署返回 HTML 的页面空白已复现并加结构校验，故障模拟通过：独立预览的 HTTP200 HTML 响应仅显示局部错误，字段和弹窗保持可读；恢复实际 API 后重试成功。

截图与来源哈希见 evidence/task-archive-readable-20261007/overview.jpg、records.jpg、narrow.jpg、ui-complete.json。RFC、ADR、BUG 同步更新，复制至用户指定技术文档目录。

历史域缺失材料如实展示 API notice 与 missing_sources；本次实际提示“底线域加载材料未记录”，仅画3个已记录域/进程节点，不补 D0 或缺失 DSL。组件4项测试在最后提示调整后通过。

## 主会话最终整合

后续统一构建仍为51项前端测试通过，最终资源index-BVZOdasf.js/index-CKbQv6NF.css。主会话补了直接URL刷新后的关闭焦点回退、审核行已记录收紧/扩展类型以及历史图短连线标签；18003实屏与423px、后退刷新、Escape焦点复验通过。最终截图和后端/真实权限闭环见REVIEW-20261007-agentscope-task-archive.md。本文ui-complete.json及既有截图保留为子会话当时版本证据。
