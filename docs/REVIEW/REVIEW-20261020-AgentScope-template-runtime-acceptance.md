# REVIEW：全模板真实运行验收（2026-10-20）

## 核验结果

- 当前 37 个模板全部纳入：31 个当前可执行模板、2 个历史兼容模板，真实执行共 164 项；4 个无执行能力模板，实际检查仅保存草案并拒绝单项/批量提交及重新校验。历史模板另验证新建与模板编辑拒绝。
- 文件读取、写入、删除、例外范围、生成程序执行链、程序启动、IPv4 新连接、敏感来源与网络来源的动作均核对命中和不匹配控制。检查模板核对前置缺失、成功、失败及写入失效；Git 操作使用真实本地仓库/本地 bare 远端。
- 各例核对 DSL、内核事件、子进程返回与文件/仓库/本机接收端的独立状态；notify 继续，block 返回 EPERM 且保护状态不变，kill 子进程返回 -9。kill 不证明副作用前拒绝，网络接收端已接受的反例保留。
- 原始 CLI 导出的事件文件 UID 为 1000，属于受控合成实验记录，不宣称其具备抵御恶意执行者篡改的 root 审计属性。当前 Agent 的保护仍应由正式执行域、策略哈希、运行回执及真实操作核验。
- 独立浏览器逐一打开 37 个模板详情：33 项运行记录、4 项已验证拒绝及各自能力边界可见；2 个历史模板无保存按钮且字段禁用，历史已应用子配置仍可请求审批停用。

## 可重跑证据

`evidence/template-runtime-20261020/runtime-results.json`、`rejection-results.json`、`manifest.json`、`cli-output.json`、`preliminary-results.json`。脚本为 scripts/accept_all_template_runtime.py、accept_template_rejection_paths.py、collect_template_runtime_evidence.py。两个执行脚本使用独立验收锁串行运行，不与正式 Broker/DSH 交互。

## 回归与发布

- 后端全量 `pytest -q backend/tests`：1426 passed，5 项既有弃用告警；前端 354 passed，Vite 构建通过。WSL 重启后既有短路径测试父目录 /tmp/a 缺失，建立测试夹具目录后全量复验通过，未修改无关模块。
- 已发布到 /opt/agentscope-policy-semantics-20261020-124843，API 重启 1.118 秒；Broker 的 PID/start_ticks/命令不变，受控 Agent 执行身份和策略哈希一致，18000/18004/18020/18021 监听不变。14 个配置、模板版本、审批与 DSL 表的行数及内容哈希均相同，没有在正式环境新建、批准、加载或停用策略。
- 正式页面已重新载入，核验网络 block/kill 的边界说明及不支持 Git 目标限制的拒绝说明；旧模板只读及审批停用在独立 18169 库验收。编译、API 健康或这次合成实验均不作为当前每个 Agent 已启用该策略的证明。

## 逐模板记录

| 模板 | 核验 | 运行用例 |
|---|---|---|

| RQ1-ENV | 真实运行实测 | 3 |
| RQ1-CONTRACT | 真实运行实测 | 6 |
| FILE-READ | 真实运行实测 | 3 |
| FILE-CHANGE | 真实运行实测 | 6 |
| WRITE-BOUNDARY | 真实运行实测 | 3 |
| RQ1-GENERATED | 真实运行实测 | 3 |
| RQ1-CHECK | 历史兼容实测；入口只读 | 8 |
| RQ1-DELETE | 真实运行实测 | 6 |
| RQ1-GIT | 历史兼容实测；入口只读 | 2 |
| EXEC-BLOCK | 真实运行实测 | 3 |
| EXEC-AUDIT | 真实运行实测 | 3 |
| NET-BLOCK | 真实运行实测 | 3 |
| NET-AUDIT | 真实运行实测 | 3 |
| SECRET-EGRESS | 真实运行实测 | 3 |
| REMOTE-EXEC | 真实运行实测 | 3 |
| SYS-env | 真实运行实测 | 9 |
| SYS-ssh | 真实运行实测 | 9 |
| SYS-cloud | 真实运行实测 | 9 |
| SYS-system-files | 真实运行实测 | 9 |
| SYS-policy-store | 真实运行实测 | 9 |
| SYS-audit-store | 真实运行实测 | 9 |
| SYS-privilege | 真实运行实测 | 3 |
| SYS-network-audit | 真实运行实测 | 3 |
| SYS-process-audit | 真实运行实测 | 3 |
| SYS-instructions | 真实运行实测 | 9 |
| SYS-secret-egress | 真实运行实测 | 3 |
| SYS-remote-exec | 真实运行实测 | 3 |
| GIT-COMMIT | 真实运行实测 | 2 |
| GIT-COMMIT-CHECK | 真实运行实测 | 8 |
| GIT-PUSH | 真实运行实测 | 2 |
| GIT-PUSH-CHECK | 真实运行实测 | 8 |
| GIT-LOCAL | 真实运行实测 | 6 |
| GIT-BYPASS | 真实运行实测 | 2 |
| GIT-CONTENT | 暂不支持，拒绝路径已核验 | 4 |
| GIT-PUSH-TARGET | 暂不支持，拒绝路径已核验 | 4 |
| GIT-PUSH-APPROVAL | 暂不支持，拒绝路径已核验 | 4 |
| GIT-MERGE-GATE | 暂不支持，拒绝路径已核验 | 4 |
