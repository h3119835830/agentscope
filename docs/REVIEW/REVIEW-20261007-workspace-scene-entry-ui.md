# 工作区场景读取入口前端验收

日期：2026-10-07。关联总体合同：[RFC](../RFC/RFC-20261007-workspace-scene-read.md)、[ADR](../ADR/ADR-20261007-workspace-scene-read.md)、[BUG](../BUG/BUG-20261007-workspace-scene-read.md)。

## 实现

选择 Agent 与工作区后，主操作是“让 Agent 读取场景”。文件清单默认折叠；任务名称由只读 Pi 生成，不再要求用户预先填写名称和目标。真实读取完成后按字段显示名称、目标、约束和来源。只有 needs_clarification 时显示“补充本次目标”；用户修改补充后旧草稿立即失效，重新读取生成新 read_id。采用草稿仅提交 read_id、draft_hash、expected_manifest_hash；后续生成策略仍等确认，本步骤不加载策略或启动 DSH。

长目标默认三行预览，展开显示完整原文；约束默认前两条，剩余项折叠；证据默认折叠。展示不截改后端原文或草稿 hash。用户补充的实际引用标记为“用户补充”，不混作场景文件，也不重复追加。

浏览器只保存 Agent、工作区、manifest、来源实例、补充和 read_id 恢复指针，不保存模型运行日志或凭据。刷新只 GET 原作业，不自动 POST。异步结果按工作区、Agent、manifest、实例及补充内容检查；仅当前已完成 ready 且尚未采用的草稿可继续。切换工作区的首帧不得把旧 inventory 传给新读取组件；过期文件/实例保留补充并清除旧指针。采用后的结果显示已有任务入口，不能重复创建。

## 自动化与审查

- 全部前端 node:test：65 项通过，其中 9 项读取合同/状态/来源测试、5 项摘要 SSR 测试。
- Vite 构建成功，56 modules；独立构建引用 index-D0rPDXgC.js / index-CFGRgZyl.css；主会话统一部署 18003 引用 index-DtEsCKQg.js / index-CFGRgZyl.css。
- git diff --check 通过；TaskHub 中 TaskRecord 导出函数及后续部分与改动前逐字一致。
- 独立只读审查发现并修复两项 P2：跨工作区首帧错误清除恢复指针；用户补充来源误标并重复。未发现重复采用或跨工作区权限绕过。

## 真实只读 Agent 验收

目标工作区 423a957c41f2b7be 只有 README.md（45 bytes）。未修改其文件。

| 操作 | 读取作业 | 结果 |
| --- | --- | --- |
| 空目标直接点击读取 | f4ee0751fe3a49f88bf6c74b712f4550 | completed / needs_clarification，goal 为空；只在此时出现补充框 |
| 补充“只读取并概括 README.md，用一句中文回答；不改文件、不执行命令”再读取 | b2bffb6afd4d4561997c4726f3d15917 | completed / ready；自动名称“读取并概括 README.md”；目标“只读取 README.md，并用一句中文概括其内容。” |
| 刷新页面 | 同一作业 | 恢复 ready 摘要，无再次点击读取 |

两次均从部署于 18003 的真实页面点击、经过真实 Pi 作业，不是 mock 结果。前端会话没有采用草稿、生成策略、确认加载或启动 DSH。主会话另验 RQ5/明确目标/不可信 README 及唯一采用和待确认策略，见总体 REVIEW；不能据只读 UI 验收宣称内核 enforcement 或 DSH 执行已通过。

最终部署后验收通过：

- 423a957c41f2b7be → RQ5 4b85c64874115f49：显示 20 个文件，无上一工作区草稿；切回原工作区恢复同一 ready 摘要，无新的读取请求。覆盖不同清单 hash 的切换恢复。
- 来源默认收起；展开仅 2 条：用户补充 / 本次输入与场景文件 / README.md，不重复。其余 2 条约束默认折叠。
- 原生 details 可用 Enter 展开、Space 收起，焦点保留在 summary；任务采用按钮未点击。
- 423 × 900 视口：body clientWidth/scrollWidth 为 408/408，scene-read 为 312/312，字段和操作区均无横向溢出；临时视口已 reset。
- 真实 UI 此次使用短目标，长目标三行及展开原文由 SSR 回归和 CSS 规则验证，没有为截图追加 RQ5 模型读取作业。

限制：既有 Agent 在线显示在轮询间曾短暂显示待检查，随后恢复；本次未改连接模块，已向主会话报告，不能把瞬时禁用按钮解释为 DSH 进程重启。

## 证据

用户指定技术文档目录下：REVIEW/evidence/workspace-scene-entry-ui-20261007。截图为本地 Demo 测试工作区公开目标，不含凭据、模型私有推理或原始敏感数据。
