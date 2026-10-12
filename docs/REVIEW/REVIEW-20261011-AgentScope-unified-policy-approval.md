# REVIEW：统一审批与未批准不变更权限

日期：2026-10-11。结论：第一步源码与隔离审批链路验收通过；可评审和演示人工审批交互，未声明已发布或完成新增内核验证。

## 审查结果

| 核对项 | 结果与证据 |
|---|---|
| 提议与应用分离 | instances.controller.proposals 不再调用 apply 或创建自动应用线程；两种 actor 均只提交 pending |
| 查看不获得权限 | 统一目录、详情、计数不调用 executor stop/start 或 managed install；读取前后状态有断言 |
| 人工控制权限 | 新路由位于受保护 /api/console；无凭据、Agent 凭据不能确认，严格请求体不接受 actor 或作用域替换 |
| 精确对象与防漂移 | 实例指纹含 instance_id 和冻结上下文；系统沿用目标计划；运行时核对 session、domain、runner 与项目证据 |
| 竞争与幂等 | 分派后由原控制器重新持锁校验；重复确认不能重复加载；已拒绝候选不能再次应用 |
| 继承与底线 | 未改 compose、canonical、install 的底线逻辑，系统约束、不可变启动底线和失败关闭测试继续通过 |
| 历史可靠性 | 类型化策略保存原始基线；运行时 applied 匹配作业与确认指纹的回执；缺字段不伪造当前事实 |
| 客户界面 | 表格目录、详情前后对照、影响范围、明确批准/拒绝；不展示原始 JSON、内部上下文或伪造 DSL；旧编辑器不再宣称自动收紧应用 |
| 改动隔离 | 仅 AgentScope 后端、前端、测试和文档；未修改 ERP/Hermes 普通业务代码，未替换共享运行服务 |

## 验收

后端完整回归：991 passed，52 skipped；前端：220 passed；Vite 构建成功。跳过项不视为验证成功。既有 FastAPI/Starlette 弃用告警与前端大 bundle 告警保留，不影响本次测试结果。

临时 18114 使用独立数据库和实际应用/UI，模拟特权 stop/install 与 Broker 状态。浏览器实际操作及数据库断言确认：查看不改变权限；运行时批准只把本任务 v3 更新为 v4；拒绝 Agent A 后原配置不变；批准 Agent B 不改变 Agent A；批准后详情保留原始差异。临时服务已停止，不连接真实 Broker，不产生内核加载声明。

## 发布前仍需处理

1. 本次分支基于 `b6b6fa2`，与共享环境及其他并发系统策略工作区分别存在；发布前合并、核对完整 diff 并重验，不覆盖其他工作区未提交改动。
2. 新增表为附加 schema，旧待审候选需按提示重新提交；不能回填当前环境冒充提交快照。
3. 真实 Broker、停止旧域、启动新域和内核动作验证需在明确目标环境进行。本次自动化使用真实 ActPlane DSL 编译器的既有合同测试，但特权 IO 使用替身。
4. 原 Scope Demo 实验接口与启动审核没有迁移到本次目录；当前产品 Managed Runtime 与实例旧收紧路径已迁移。

详情见[验收材料](../acceptance/20261011-unified-policy-approval/README.md)与[RFC](../RFC/RFC-20261011-AgentScope-unified-policy-approval.md)。
