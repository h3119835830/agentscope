# REVIEW：启动失败恢复与运行前工作台收敛

状态：本轮恢复范围验收通过，2026-10-08。

## 结果

旧失败页面已可通过显式关联打开同源、同约束的新候选，保留原工作台子页和紧凑记录模式。旧失败不改写为成功，生成成功不显示为已加载；人工确认仍是独立操作。

真实浏览器从 0dae79b573f14bca 点击重新生成，得到 4ca8082805f74c6c。Pi 作业 768441504f1b4f228b4da7c8d32cf4e3 完成，候选 6022bcbb0e50464288208ac5f7f18caf validated 且编译通过，包含 2 条文件执行策略和 5 条任务指导。两条策略保护 tests 与 config，指导保留原任务要求。

旧、新 manifest 同为 014d1db9e3ccaffdabb5861c0a610963150dd19f0b9eef4e1da1f37b0a438323，全部 5 条 accepted_task_constraints 及规范化 requirements 一致。此前 ad7 同源复验的约束不同，不能作为本任务恢复候选，因此没有借用其结果。

## 安全与接口评审

GET 纯数据库读取，无模型、工具、连接核验和权限副作用。POST 校验固定 context/manifest、候选 hash、身份代次与阶段；初始化、入队失败及并发重复使用同一关联。声明目标按资产身份精确映射，澄清证据重建命名空间；来源变化和跨任务请求拒绝。

真实生成后发现 validation 摘要与候选正文分表的合同差异，已修复并用实际工具 issue/get_context/list/read/search/capabilities/validate/submit、complete_start 的落库链路回归，补充候选及摘要篡改拒绝。没有降低 hash、编译或人工审批要求。独立后端复审无阻塞问题。

旧 task/context/job 不变、新任务无策略版本/任务执行凭据/DSH 会话及 Pi 临时凭据撤销的只读核验，以 evidence/startup-recovery-20261008/final-integrity.public.json 为准。

## 验收

- 后端专项 33 passed；完整后端 596 passed / 52 skipped / 5 既有 warnings，耗时 16.60 秒。
- 前端 112 passed；Vite 构建成功；完整 diff whitespace 检查通过。
- 旧页面实际“查看恢复候选”进入 4ca；返回、刷新后保持 awaiting_review 关联。未产生新的生成任务。
- 只保留一份运行前策略列表，确认入口、文件证据、生成过程、工具结果和版本仍在。
- 选中 test 语句仅展示其 write/unlink 对应编译片段，未混入 config 或完整底线 DSL；指导显示实际短语句，完整内容在抽屉。
- Chrome 实际 innerWidth=423，页面及抽屉 scrollWidth=408 或423，没有横向溢出；Enter 打开指导详情，Escape 关闭并将焦点返回对应记录。IAB 的 viewport 设置未实际改变尺寸，故未将其误记为窄屏验收。
- 部署仅替换 UI 并重启 API 至 PID1270207；Broker966501 与原生 DSH870966 未变，未影响18000/18004。

UI index SHA256 为 5b1d86cb12c33be17cbceba5773aba974e8e6011e41489d9993dbe903c122fc1；JS index-B8HzGtqG.js、CSS index-B5Ij8QFp.css。截图、GET 回执、完整性及测试日志在 [证据目录](evidence/startup-recovery-20261008)。

## 验收边界

本轮证明旧启动失败的恢复生成、校验、关联和展示可用。未代用户确认/加载候选或执行 DSH，不能将本轮报告作为新任务 OS 拦截、功能测试或 S0—S4 全流程执行证据。此前真实任务证据继续独立保留。独立开发的 Hook 尚未合入本发布。
