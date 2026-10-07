# REVIEW：Agent 工作区与任务记录验收

日期：2026-10-07。范围：本机 /opt/agentscope-history-v1、Scope Demo 18003。结果：通过。

## 自动化检查

- backend/tests：326 passed，5 个既有 FastAPI/TestClient 弃用提示。
- frontend/src/taskPresentation.test.mjs：2 passed，覆盖任务搜索/阶段筛选、逐条 DSL 归属和类型化中文操作展示。
- Vite 生产构建通过；git diff --check 通过。
- 新工作区专项 14 项，覆盖管理员认证、执行端不可用、实际文件刷新、凭证排除、路径/符号链接拒绝、旧清单拒绝、独立快照、未经确认不批准不加载、陈旧候选/文件/配置拒绝、确认后加载前再次核验、目录缺失保留历史、读取已启动 Agent 的更新目录。

## 真实执行链

验收任务：3706103b84f64746（工作区流程验收：修复加法）。源目录 /s/workspaces/30d2ebf698f34c32；执行目录 /s/3706103b84f64746/r。项目含 README、main.py、测试与配置共四个文件。

1. 在浏览器连接 DSH，读取既有支付验证工作区的 19 个文件；新增独立工作区，放入四个实际文件，刷新后逐项可见。
2. 从工作区行进入新建任务，所选目录与文件清单正确带入。创建任务，Pi 完成生成，提交两条经校验的规则：保护 tests/test_main.py 与 config/app.json。
3. 确认前 phase=policy_review、gate=waiting_confirmation、version=0、Session=null。没有将候选生成误写成已加载。
4. 浏览器确认后实际加载 v1，DSH Session 建立。运行时进程、domain、cgroup 均核验通过，effective=true。记录在 after-confirmation.json。
5. 向验收会话发送继续执行请求，原生审计记录 read/edit/bash。Agent 修改 main.py；独立复跑 unittest 两项均通过；原测试、配置、README 哈希不变，源目录四个文件全部不变。
6. 结束验收会话，实际进程撤销，任务保留为历史。执行目录重新出现在 Agent 工作区清单；main.py 哈希反映 Agent 改动，与保留源目录区分正确。

## 浏览器验收

通过实际界面验证：工作区选择带入、文件刷新、创建任务、策略确认、执行跟进、返回任务列表、按 ID 搜索、旧支付任务结构化历史、文件证据、生成记录及版本记录。返回列表不会误跳到创建表单；历史默认不展开原始 JSON 或完整 DSL 文档。750 像素窗口无页面级横向溢出，较宽表格在自身容器滚动。

证据在 [evidence/agent-workspace-console-20261007](evidence/agent-workspace-console-20261007)：before-confirmation.json、after-confirmation.json、file-integrity.json、tool-records.json、agent-workspace-readback.json、after-close.json、task-history.png、agents-workspaces.png，以及测试/发布回执。

## 发布与范围审查

静态 UI 构建部署到 /var/lib/agentscope-scope-demo/ui；API systemd 单元在 20:15:04 CST 重启，Broker PID 810937 及其启动时间保持不变。重启前确认没有待运行或正在执行的策略分析作业。旧静态文件备份至 ui-before-agent-workspaces-20261007。

本次修改仅工作区/任务控制与界面，没有修改普通采购、销售、库存、财务 Java 业务，也没有调整 Pi 系统提示词来特判验收任务。仓库含其他会话既有未提交修改，本次未作整仓提交或远程推送。

## 已知边界

连接状态表述的是 DSH 执行适配器配置检查；实际在线性仍在工作台单独验证。仅管理或登记的 DSH 工作区可选择，不自动接管任意个人/远程 Agent。任务使用独立执行快照，源目录不自动回写。此验收证明新任务流程及小项目的真实执行，不宣称旧历史故障已被修复。
