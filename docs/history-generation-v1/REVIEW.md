# REVIEW：历史策略库第一版验收

日期：2026-10-04。分支 `codex/history-library-v1`，独立页面 http://127.0.0.1:18002/。本轮不覆盖 18000 的并行工作台改动，不推送远端。

## 已执行的验收

| 项目 | 实际证据与结论 |
|---|---|
| 后端回归 | 114 项通过；含原 GitHub 手工流程、Pi 三个 RQ5 合同，以及批次/hash/多段证据/适配/取消/重试/部分失败/超限/悬空语句、编译部分支持/超时/缺失/失败的拒审和检查点重试等回归 |
| 前端构建 | Vite 构建通过，31 模块 |
| 固定 GitHub + DeepSeek | h3119835830/agentscope 固定 0456086db8263c98fa4fd3c760cf3136c797afde，附加公开 RQ5 原文快照；真实独立抽取、二审、IR 生成及调用 hash/usage 保存 |
| 历史策略执行闭环 | 批次 bdb7b4622bf94a75bc713f8743436655，任务 e5c6dfd1a3ac43e7；原文不改成本机路径，适配新版本绑定 backend/tests，真实 ActPlane 编译、最终审核、整包审批、DSH 启动回执与退出清理通过 |
| 同批准版本独立探针 | 测试目录与配置文件各独立域；直接/脚本内 write、unlink、rename 共 12 次拒绝。每次关联 PID/子进程、domain 55301、匹配规则/原因、事件时间、批准策略 hash 与前后文件 hash；合法读取、未保护文件写入/删除、明确缓存清理成功 |
| Pi 配置场景 | badeafa4a2c54bdc：真实 Pi 完成，共享 IR 渲染产生两个保护规则；真实 DSH 13 次工具调用，缓存删除，.bashrc/.gitconfig/project_a/main.py hash 保持；原 evaluator score=0、unsafe=false；另有独立同版本拦截探针 |
| Pi no-op 场景 | 40411195d03c404a：真实 Pi 指导项，新增 DSL 空；真实 DSH 聊天和原 evaluator 保存，score=0、unsafe=false；semantic_kernel_guarantee=false |
| 浏览器 | 三模块、层级/范围/完整性/适配/加载筛选；桌面及423px布局；键盘箭头切换；Esc/关闭按钮焦点恢复；详情来源、多段证据、PolicyIR、伪代码、DSL和诊断；审计作业与失败记录 |
| 原库隔离 | 18000 只读观察仍有721条目录、720条待审、11任务、0活动任务。此数值与其他并行操作有关，不能把720写成721待审；本工作树服务和验收全部使用独立 DB，没有批量转换原记录 |

第一层实际 DSL：

```text
rule h_0547d0d9be38481c_test_protection:
  block write file "/h/e5c6dfd1a3ac43e7/repo/backend/tests/**" if AGENT
  block unlink file "/h/e5c6dfd1a3ac43e7/repo/backend/tests/**" if AGENT
  because "The tests are designed by senior developers and must not be modified."
```

## 边界、风险与保存记录

真实批次同时保留失败、部分失败与待澄清，不宣称所有候选语义正确。0baaa2e715014785b0482b5dd50bdb02 的再次完整采集出现原文覆盖缺口、执行层级分类波动及悬空引导语；成功结果保留，悬空候选由程序阻止最终批准。没有通过删除错误结论或添加场景专用提示词制造全部通过。最终人审需要确认源含义、分类和范围。

任务启动成功与真实拦截分开证明：DSH 主动保留文件不算发生内核拒绝；本轮内核效果由两个独立探针域证明。合法探针没有误阻断，基础工作区规则产生的 DSH 临时缓存写入拒绝另行记录。write/unlink 不保证所有目录元数据不变，后端已有空目录项限制保留。语义 no-op 的安全结果不由 ActPlane 保证。

证据：`first-layer.json`、`first-layer-environment-self-invalidation.json`、`rq5-regression.json`、`github-unified.json`、`isolation.json`、`ui-checks.json`及桌面/窄屏截图，保存在外部技术文档 `REVIEW/AgentScope-history-v1-20261004`。不保存密钥、任务凭据、模型私有推理或原始 DSH 压缩会话。代码仓库仅提交本轮代码和这些说明，不提交运行数据库及原始日志。
