# ADR-20261011 服务端环境绑定与会话候选的权限边界

状态：采纳。补充 ADR-20261010-agent-policy-integration。

1. 环境由控制面从已核验连接与可信原生会话映射读取。客户端只交实例/会话选择和期望 hash，不能把自然语言中的路径或浏览器 Agent JSON 当成 verified context。
2. 工作目录与文件对象适配分成两步。通用模型计划只抽取用户明确命名的对象，服务端逐字定位来源并解析、检查路径；生成不可变适配版本，保留初始输入和模型复核记录。不存在的目标可以作为明确未来路径，必须注明其存在性。
3. 复核模型的猜测、uncertainties/review_issues 保留在评审证据中；它们不是用户新增要求。独立 IR 翻译使用来源文本、已通过的完整性状态与核验环境，不能把上一阶段的猜测升级为新的策略语义。未完成的上下文和 IR unresolved 仍阻止 DSL 生成，没有强制清空缺口。
4. 能力说明跟随真实后端配置。旧任务仅列 write/unlink 的说明不能覆盖受控实例后端；open/read 支持来自既有 ActPlane 与 Broker AST/后端检查。policy because 解释与反馈送达回执区分，未证明的反馈不宣称成功。
5. 候选与 Agent/会话/环境绑定持久化在原有不可变语句版本与产物中。无需新并行数据库，不以 sessionStorage 作为权威。会话入口是选用入口；既有 Agent 共享策略的作用范围保持明确，不伪造单会话内核隔离。
6. 生成/选取/保存校验不是批准。已有 DSL proposal/confirm、CAS、受影响目标预览、Broker 重编译、加载闭环继续作为唯一应用路径。旧历史库的 review_status 不被自动改为 approved。
7. 18003 API 使用独立 release 目录和 systemd API drop-in。保留旧 release 与静态 UI 备份；只重启 API，不重启 Broker 或原生 Agent，不修改 18000/18004。

2026-10-11 补充：实际进程执行来源、API 账号隔离与只读观察器决策见 ADR-20261011-verified-agent-policy-sources。按产品名推断启动来源的旧实现已被取代，生成/选择/保存校验与最终人工确认的边界不变。
