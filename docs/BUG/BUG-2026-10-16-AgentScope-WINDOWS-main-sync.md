# BUG：发布分支落后与干净工作树验收准备缺项

日期：2026-10-16。

| 问题 | 复现 | 修复和验收 |
|---|---|---|
| 发布分支遗漏累计更新 | main/WINDOWS 停在 90af640，最新整合分支领先 67 提交 | 将完整验收提交快进同步到两个本地分支；远端更新另行授权 |
| CI 缺少 DSL adapter | 新工作树后端 1084 passed、53 skipped、217 setup error，明确提示需构建 adapter | CI 增加 release 编译；最终后端 1354 passed、0 skipped、0 failed |
| 文件身份安全回归的 runner 不符合前提 | 非特权进程带补充组，真实读取校验拒绝，31 个失败 | CI 使用隔离 root 测试 runner，由受测子进程真实降权；保留产品拒绝逻辑 |
| 桥接测试依赖开发机目录 | /tmp/atf 不存在时 mkdtemp ENOENT | 改用系统 tmpdir；前端/插件 362 项通过 |

原脏工作树没有新增未收录实现：121 个文件内容均在累计分支历史中。未清理或覆盖原工作树，不把历史脏状态当作本轮修复。

[验收闭环](../REVIEW/REVIEW-2026-10-16-AgentScope-WINDOWS-main-sync.md)、[范围合同](../RFC/RFC-2026-10-16-AgentScope-WINDOWS-main-sync.md)。
