# AgentScope GitHub 分支发布与主分支合并验收

日期：2026-10-04。结论：通过。用户明确授权先推送对应 GitHub 分支，再合并主分支。

发布仅操作 WSL `/opt/agentscope`，远端 `https://github.com/h3119835830/agentscope.git`。未操作丰安途的 Hermes、Java、Web、AI-Brain 仓库。

| 项目 | 已核验结果 |
|---|---|
| 开发分支 | WINDOWS，0456086db8263c98fa4fd3c760cf3136c797afde |
| 主分支 | main，3519f8c06e5768b968a3fa29bcbbddb3b0f802f5 |
| 合并入口 | https://github.com/h3119835830/agentscope/pull/3，closed / merged=true |
| 合并范围 | 7 个尚未进入 main 的功能提交；132 个文件，仅 AgentScope 与固定公共研究制品 |
| 发布前本地检查 | 92 项后端测试通过；前端生产构建通过；实现源码 whitespace 检查通过，冻结制品原字节不重写 |
| PR CI | python、frontend-and-plugin、actplane 全部 success |
| 合并后主分支 CI | 同三项全部 success；https://github.com/h3119835830/agentscope/actions/runs/37181542069 |
| 本地同步 | WINDOWS 与 origin/WINDOWS 一致；main 与 origin/main 一致，工作区干净 |
| 内容一致性 | origin/main 与当前 WINDOWS 的文件树无差异，合并仅新增合并提交 |

本次不修改架构合同，也不重跑 DSH 场景；既有运行验收和语义安全限制继续按原 RFC/ADR/REVIEW/BUG 报告。GitHub CI 是源码和构建验证，不替代内核执行证据。运行数据库、凭据及模型私有推理均未发布。

公开 GitHub API 回执保存在 `AgentScope-history-20261004/github-release.json`。此前验收记录中“未推送”是该次验收结束时的状态，本次授权发布与合并以此记录为准。
