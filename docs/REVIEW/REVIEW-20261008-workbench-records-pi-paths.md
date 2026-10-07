# REVIEW：原记录形式恢复与 Pi 路径修复

状态：修复完成；真实 Pi、只读档案、桌面与 423px、完整回归验收通过。

范围仅 AgentScope 前端纯展示、只读档案投影、Pi 工作流诊断和任务快照映射。未修改普通业务、ActPlane ABI、原生 DSH 或 Broker。API 单独重启到 PID 1071142，原生 DSH 870966、演示 Broker 966501 未变。部署前建立私有一致性备份，备份和凭证不提交。

## 已通过

- 前端 104 项通过；Vite 构建通过。最终静态包 index-CjHDw2j5.js / index-BIy6ige1.css，index SHA256 15fdc2c6ac8fbe0ada3d2edba8e6af849c5afe135591a8d6982780e8919dfd0e，HTTP 字节一致。
- 后端完整 563 passed、52 skipped、5 warnings（无 TMPDIR 覆盖）。首次发现的 ABI 成功测试路径 fixture 已修，生产限制未改。
- 独立档案专项 78 项、Pi/共享驱动专项 109 项、快照布局与来源完整性 26 项通过。
- 真实旧库 pure view：f39 两句、d5 五句精确 child ID 与原工作台 DB-only strategy-records 一致，分页无重复；jobs 41/40、原 mixed 41/42 不变。22 张权威表行数/hash 及原生/Broker PID代次不变，不调用 Broker/current workbench。
- 原失败 0dae 上下文保持；新同源 ad7c53a17c334c7b 采用同一来源 manifest、20 个资产字节/hash 一致，项目根固定到 p0，测试目标为 42/48/52 字节，未调用审批/加载或启动 DSH。

真实 Pi 作业 948e76e023fe480aa959a62a8d556eb1 已 completed：2 个执行策略 atom、7 项任务指导，服务器 proposal_state=validated；第一次缺两个读取回执后 Pi 自行补读，第二次 valid=true、compile_state=compiled，并按精确哈希提交。phase=policy_review、gate=waiting_confirmation，version=0、session=null、policy_versions=0、执行凭据=0，Pi 临时凭据已撤销。原失败上下文 SHA、来源 manifest 和全部资产 bytes/hash 再核对不变。公开回执 pi-retry.public.json。独立真实 Chrome 14 项通过：桌面 innerWidth=1287，实际 423×900 窄屏 body/client/scrollWidth=408，无整页溢出；域图容器内部横滚。f39 首屏两句、d5 五句；生成记录默认闭合，独立 12→24 分页不改变语句行；四主栏目/两次级入口，抽屉默认语句与类型，键盘至 DSL 后仅 acceptance-temp 的 write/unlink 两条，不把折叠原始字段内的完整材料当主 DSL。OS/工具/控制记录分开、v1/v3 历史图、刷新/返回/任务选择及第二页筛选恢复通过。最终截图、hash 和公开回执见 browser-acceptance.public.json。只读历史的内核材料是旧任务真实保存记录，本轮不冒充新 DSH/内核执行验收。

真实新候选页面另有 7 项只读 UI 补验通过：ad7 任务选定、待确认、已校验尚未加载、会话尚未建立，2 条执行规则与 7 条任务指导及 p0/tests、p0/config 目标可见。1280×900 实屏截图 desktop-pi-review.jpg 与 pi-review-ui.public.json 保留；未点击批准、启动、检查或重试。
