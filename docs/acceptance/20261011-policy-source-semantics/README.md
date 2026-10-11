# 原文权限语义修复验收

2026-10-11。model-round-1.json 与 model-round-2.json 为配置中的实际模型和真实静态编译器两轮结果；kernel-results.json 为第一轮候选在独立测试引擎的实际操作和拒绝事件。所有项目文件为公开可复现的合成数据，无服务凭据或模型私有推理。

后端全量 1092 passed/11 skipped；前端 236 passed，Vite build 通过。6 组真实模型连续两轮通过；实际内核 6 组、65 项操作检查、41 条拒绝事件，测试 pin root 清理完成。候选在产品中始终 pending_review；权限表摘要未变。内核探针是用户授权验收中的独立测试加载，不是产品批准或应用。

复现入口：scripts/accept_policy_semantics.py（需已配置模型环境）、scripts/accept_policy_semantics_kernel.py /tmp/as-sem-.../model-results.json（显式 root，独立 pin root）。脚本只接收指定合成工作区结果，不触碰共享 Broker 或已登记真实 Agent。

浏览器在 18116 的 Agent → 策略助手验收旧候选失效、新候选只限制修改、详情与人工提交边界。18003 未部署本修复。截图和 ui-summary.json 记录本轮实际交互。

边界：身份映射为合成登记，内核运行程序为 semprobe；并非 DSH/RQ5 任务闭环、生产发布或完整攻击面测试。事件文件是本地测试反馈，非防篡改审计库。
