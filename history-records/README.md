# AgentScope 历史档案

每个任务只有一份完整 JSON 档案：目标与约束、来源 Agent 与工作区、文件证据元数据、策略生成和版本、权限变化、工具与内核证据、审核、暂停恢复及结束回执均通过同一 task_id 组织。

- [2026-10-07 快照：299 个任务、27,145 条公开事件](2026-10-07/README.md)
- [导出合同](../docs/RFC/RFC-20261007-AgentScope历史档案导出.md)
- [决策](../docs/ADR/ADR-20261007-AgentScope历史档案导出.md)
- [验收](../docs/REVIEW/REVIEW-20261007-AgentScope历史档案导出.md)

这是已保存记录的公开快照。快照中的 running 不证明现在在线；缺失证据保留缺失标记。凭据、数据库、原始文件正文和原生会话私有流不进入 Git。本分支用于查阅、追溯和复核，不提供会话重放或运行权限恢复。

重新导出需提供包含 archive 模块的部署源码及其 Python 依赖，用 `scripts/export_task_archives.py --help` 查看参数。私有 SQLite 快照必须保存在发布目录之外。`scripts/verify_task_archive_export.py` 可直接校验本分支现有档案，无需运行 Agent。
