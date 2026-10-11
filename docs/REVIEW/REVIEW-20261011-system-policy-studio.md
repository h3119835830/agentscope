# REVIEW：系统策略配置与 ActPlane 执行能力

2026-10-11。状态：代码、隔离验收与 18003 正式发布验收通过。

## 验收
- 已合并 b6b6fa2 及前置实际 Agent 身份/共享 Node 域隔离更新，保留并行修改。
- 后端全量 1024 passed、11 skipped；前端 220 passed；Vite 构建成功。审批结果展示收尾后，相关后端 40 项与前端全量再次通过。
- 编译器 43 passed、1 ignored；BPF 预留单测通过；C 匹配器 42 项通过 GCC ASan/UBSan。
- 12 类候选 × 3 动作 × DSH/Hermes，真实解析器与编译器校验。
- 9 组真实内核：block/notify/kill、文件名、63 字节后缀、深路径写入/删除、目录自身及内容、目标例外、来源标签传播。深路径超过 64 字节；非匹配及符号链接均检查。
- 独立 18143：DSH/Hermes 同时继承；三种动作核对操作、子进程、内核事件和加载产物。kill 不终止主 Agent。
- Agent 策略只影响当前目标，同名文档/规则不覆盖系统约束；新 Agent 首次启动继承。停止者不被系统更新启动。
- CAS、过期版本、目标/能力变化、幂等确认、部分失败暂停、原生凭据越权、跨文档标签隔离有后端验收。
- 浏览器：持久保存、完整 DSL 导入、逐规则显示/整文档选择、多选、全体目标确认、拒绝、过期刷新恢复、超长后缀拒绝、独立停用预览及窄屏。

## 证据
evidence/system-policy-e2e-20261011/kernel.json 与 service.json 为合成文件/进程及独立服务证据，不含凭据。deployment.json 为正式发布回执，rollback-check.json 为首轮回滚及保护核验。browser.json、production-*.jpg、editor-*.jpg、list-390.jpg、removal-review.jpg 记录桌面、窄屏与既有入口回归。

## 实际边界
现代 BPF 仅在 Linux 6.6.114.1-microsoft-standard-WSL2 验证，不代表 Windows 原生内核或其他内核已验证。32 层手工解析、4096 字节路径匹配上限有失败保护。审计目标短字段可能截断。notify 不宣称反馈送达，kill 不宣称事前阻断。

11 项跳过保留各自环境条件，不计通过；Vite 有大 chunk 提示但构建成功。未知平台目录需用户填写。预览配置不迁入正式系统，候选不自动启用。

## 正式发布与保护核验
- 发布目录：`/opt/agentscope-system-policy-20261011-161846`；备份：`/var/lib/agentscope-scope-demo/release-backups/agentscope-system-policy-20261011-161846`。API/Broker 使用同一版源码，已核对 UI 资源与引擎 SHA256。
- 只有升级前运行的 DeepSeek Harness 恢复，核验时 PID 615136；7 个原生会话保留。停止的 Hermes 与另一个受控 DSH 保持停止。
- 正式系统 DSL revision 6、0 个文档保持不变；12 类候选、0 项已配置。所有原有层级文档与哈希未变，没有自动选择或启用系统候选。
- 当前实际引擎后缀能力核验通过；已加载 feature mask 1022，包含文件后缀预留位。二进制 SHA256：`5e8d43c279d88bd4215f654746675debfd976e28426c9fabdabeca408865d6da`。
- 18000 原进程 PID 403 未变化；18004 发布前后均无监听，未对这两个环境进行启停。
- 首轮发布因 `ss` 输出尾部空格误判相邻端口变化，自动恢复旧应用、数据库、引擎并恢复原运行 Agent。比较改为端点、PID、进程启动时间后，第二轮发布通过；保留失败回滚回执。
- 正式浏览器核对策略库、三动作配置、匹配示例和原始 DSL；会话详情关联 PID 615136；审批保留 2 条需处理、6 条已处理记录；策略助手环境就绪，7 个会话与既有对话可回读。此回归没有提交正式策略。页面未捕获 console error。
- 内核结论来自隔离合成验收；正式环境只核对部署、能力与既有运行状态，不对现有 DSH 会话测试 kill。

- 隔离服务验收脚本已验证可重复执行（service-repeat.json）。验收结束关闭独立 API/Broker；关闭后正式 DSH PID 615136、后缀预留能力仍正常（post-cleanup.json）。
