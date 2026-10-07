# REVIEW：历史策略语句与对应 DSL

状态：已实施，后端与真实桌面验收通过。

范围仅档案只读后端、前端和测试文档。后端、前端、独立安全验收分工，主会话负责合同、真实历史核对、发布和文档；另一会话协助真实浏览器验收。原生 DSH、Broker 和权限执行器不应因查看历史而被重启或调用。

真实材料核对：ea902043e9174a528b9a370788853f11 保存六条语句，前四条为 semantic_only；21d660680b014c2c9cf06acf51d5386c 保存保护、output 授权和内容指导三条语句，整体扩权仅 output false→true。0ff64292b80d4d779e1207b850adad22 的文件收紧与现有 tests/config 保护保留是不同语句。不得把作业整体效果复制为每句新增权限变化。

验收已覆盖语句身份、对应子句与独立整包、内容指导无 OS DSL、缺失映射、扩权差异、失败作业保留、分页隔离及只读无授权变化。集成连接历史后完整后端 538 passed、52 skipped、5 warnings；该次前端 85/85。测试跳过项不作为实际内核验收证明。

真实 GET 核对 bef449047cd24af6 和 4821ac737a1a4f65，四组语句记录总数分别为 8/26 和 8/6；精确子项读取、output false→true、frontend 仅 write/unlink、语义指导不生成 DSL、失败和拒绝作业均通过。任务、受管任务、版本、凭据、工具/内核事件与生成作业表前后 hash 不变，原生 DSH PID 不变。证据：`evidence/policy-statement-dsl-20261007/policy-statement-live.public.json`。

独立桌面核对逐条语句、对应 DSL、整包默认折叠、保留规则与授权放行区分、任务→来源连接历史→原任务返回、刷新均通过。证据为同目录 api-acceptance.public.json、ui-acceptance.public.json 及截图。该次浏览器视口仍为 1280px，未把 viewport 命令成功当作 423px 验收；423px 在后续完整任务回放发布后独立验收，结果见 REVIEW-20261008-task-replay。

集成期间另一会话曾覆盖 API 工作目录，独立 GET 发现部署合同不匹配，保留 api-predeployment-mismatch.public.json。随后合并连接历史源码，统一 API 到本候选，复跑通过。旧部署回执保留为历史，统一版本回执为 unified-deployment.public.json（Cgg95WzE/CUPFpjOF）。后续任务回放构建另有回执，不能用旧资产 hash 冒充最终页面。

本次未重新执行 DSH/内核探针，使用旧任务留下的真实材料检验历史展示。缺失子项的安全行为由回归测试覆盖；未在生产库人为损坏材料制造浏览器样本。

2026-10-08 发布整理：`api-predeployment-mismatch.public.json` 仅将 CRLF 归一为 LF，JSON 数据保持一致。原始字节 SHA256 `396788e48b011fee48a9c1de6e766606db15ef916d9baeea7e02bbaa72844887`；归一后 SHA256 `17aad9df0fdb75cfed0d6c5e4827d325a6d0ec372a5a53b09e242981af4e76ea`。该证据仍只代表发布前部署不匹配，不能代表最终运行版本。
