# RFC-20261011 已核验 Agent 运行来源与策略草案

状态：已实现并更新至独立 18003。补充 RFC-20261011-agent-policy-environment，取代其按产品准入启动配置推断 source 的实现。

## 目标与职责

DSL 编辑器、系统配置、Agent 模板与自由描述生成共用服务端核验的运行来源。当前连接 DeepSeek Harness 的启动入口为 bin.js，实际进程执行程序为 /opt/agentscope/bin/node，因此生成 source AGENT = exec "**/node"。不以产品名、入口脚本名或进程显示名称替代实际执行程序，也不自动写入通用 "**"。

exec 字符串仍是 ActPlane 的程序匹配条件，不能证明某个实例独占 Node；精确实例、运行代次与进程域继续由 Broker 和既有应用校验约束。本变更不扩大策略应用范围，不改变会话共享执行器的事实。

## 只读来源合同

新增 instances/policy_sources.py。source_for 仅接受受控、已连接、runtime.verified 的行；generation、pid、start_ticks、domain_id、host_id、boot_id 必须在连接和运行身份中逐项相等且完整。直接读取本机 /proc/PID/stat 与 /proc/PID/exe，前后检查启动 ticks 和执行路径，拒绝 PID 复用、跨 boot、执行程序变化及无法准确表达的 basename。

API 账号 agentscope-api 无权读取另一个身份的 /proc/PID/exe。为维持此权限边界，新增独立只读 observer：以 SQLite mode=ro 只取受控、gate=open 的已登记运行身份，核对代次、boot 与 verified，再读取对应进程。每两秒原子输出固定 /run 路径的最小事实快照，不读取 argv、environ、凭证或业务文件内容，不写数据库、不调用 Agent、Broker 或策略接口。

快照由 root 持有，0640 只供 API 组读取。API 以 O_NOFOLLOW 打开，核对常规文件、root 所有权、不可组/全局写、大小限制；接受本 boot 且 monotonic 年龄小于八秒、精确运行身份相符的事实。只有直接观察因权限隔离失败时才使用快照，PID/boot/程序变化的失败不得回退。观察器不可用、过期或身份不符均返回未核验状态，不能猜测来源。

## 产品读取与草案行为

- GET /api/console/agents 的行增加 policy_source，含 ready、instance_id、核验身份、实际 executable、启动 entry、pattern 与 basis=verified-process-executable；未就绪只返回具体提示，不提供 pattern。
- 既有 GET /api/console/security/system/dsl 与 /api/console/agents/{id}/dsl 增加 source_context={scope_id,ready,sources,unavailable,message}，保持管理员鉴权及已隐藏连接的过滤。
- Agent 草案只读取对应连接。系统草案列出全部可见受控连接；存在未核验连接时，不生成假设已完整覆盖的 source。相同程序的 source 声明去重，连接事实保留各自身份。
- 新建空草案预填真实来源；只含来源尚无规则的文档不能保存校验。模板预览显示实际执行路径。自由描述环境上下文调用同一 source_for，来源进入既有不可变环境 hash。
- 旧文档和导入文件保留原文。通用 AGENT exec 声明在产品编辑器提示并阻止保存校验/确认；“使用当前运行来源”仅修改本地候选的 AGENT exec 声明，保留其他 source 和规则，随后仍须用户保存校验、确认应用。手工编辑清除 generation_binding，与既有行为一致。
- 编辑器在收到新的配置读取结果且运行来源变化时提示重新读取并阻止旧草案校验/确认；最终后端仍执行既有 CAS、关联候选环境复核和 Broker 校验。

## 应用与兼容性

没有新写入、批准或加载接口。保存校验、approved、loaded、active 与内核命中仍分开。旧生成候选的来源事实/hash 可能不再匹配当前环境，应重新生成或按既有流程核验；本次不改写历史候选，也不自动升级其批准状态。原始手工 DSL 的服务端语言合同不因本次 UI 改动而删减。

## 发布

API 独立发布 /opt/agentscope-agent-sources-20261011，前一版本 /opt/agentscope-agent-context-20261011 保留。70-agent-policy-sources-20261011.conf 切换 API；新增 agentscope-policy-source-observer.service。发布前验证无运行中的生成任务、无 applying proposal、scope 均 ready，核对显式文件 manifest 后仅重启 API。

观察器限制文件系统写入为固定 /run 目录，禁用网络，仅保留所需 capabilities。没有提高控制台 API 权限，没有重启 Broker 或原生 Agent。回退时移除新增 API drop-in 后重启 API；确认已回退到旧 reader 后可 disable --now 新 observer。UI 使用已保存备份恢复。不会操作 18000/18004。

验收及证据见 REVIEW-20261011-verified-agent-policy-sources。

## 2026-10-11 作用范围复核

source 的 basename 条件本身不能隔离实例。Agent scope 仅向对应连接编排，规则/标签由 ActPlane 绑定非零运行域；同连接受控子进程继承，独立连接属于其他域。系统 scope 仍明确覆盖全部受控连接。真实 cap_task/cap_policy/ts_rules 只读核验、两个域外 Node 对照及 69 项测试见 REVIEW-20261011-agent-node-isolation；未应用新策略。
