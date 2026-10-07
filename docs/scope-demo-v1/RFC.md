# RFC — DSH 文件 Scope 三阶段 Demo

日期：2026-10-05。范围：AgentScope、DSH/Pi 集成与独立标准库测试项目。普通 ERP 业务不在修改范围。

## 生命周期与职责

同一逻辑任务经历 S0 默认只读、S1 开放 backend/frontend、S2 收紧到 backend、S3 人工审核后开放 output 并重启、S4 结束撤销。tests/config、Git 元数据和执行证据保持保护。DSH 原生插件代码、profile manifest、输入覆盖文件及凭据属于不可扩权的平台资产；会话存储及每次启动重写的生成文件 cordis.yml 保留原生生命周期写入能力。同域探针的 PID/域被登记，后台不将其拒绝事件解释为 Agent 扩权需求。

~~~mermaid
flowchart LR
  U[用户任务与要求] --> M[ScopeManager]
  D[DSH 主执行 Agent] -->|申请与公开反馈| M
  M -->|固定 TaskContext| P[Pi 候选生成]
  P -->|结构化 ScopeDelta| M
  M --> R[人工审核]
  R --> B[Broker]
  B --> A[ActPlane 执行域]
  A --> V[同域探针与 root 内核事件]
  V -->|核验通过| S[当前 ScopeSnapshot 指针]
  S --> D
~~~

Pi 只读受控证据、查询已审核历史、提交候选。DSH 只能读取 Scope、报告公开结果及申请变化。二者没有管理员接口权限。Scope Demo 禁用免口令控制接口；执行 Agent 与可信转发器使用不同 UID，ActPlane 控制 socket 为 root 0600。

## 四个模型

|模型|实现位置与约束|
|---|---|
|BaselinePolicy/1|确定性 baseline：仓库默认只读、任务外写入限制、运行目录、执行能力和强制保护。默认仓库只读可经审核调整，平台保护不可由 Pi 覆盖。|
|TaskContext/1|固定真实 Git 仓库/commit、原始任务、用户消息修订、当前完整 Scope、资产哈希、公开工具/反馈与内核证据。分析时固定 JSON 快照。|
|ScopeSnapshot/1|不可变数据库记录：完整 DSL/YAML、目录授权、output 状态、baseline、有效期、hash、父版本、已生效变化 lineage、进程域和独立核验证据。|
|ScopeDelta/1|请求与候选的不可变内容/hash，基础快照、消息版本、进程代次；审核、编译、应用和核验分别记录状态，审核事件保存时间及审核人。|

候选提交、编译成功、人工批准均不切换有效指针。Broker 实际应用后，只有同域文件探针成功、root 事件匹配域/PID、保护资产完整、运行绑定回查一致，才创建新快照并切换指针。

S2 保存原已安装 DSL 与实际追加片段的完整组合。S3 重建包含全部现有约束的规则包，记录 lineage 并使用新执行域；不能从审核数量推算 Scope。

## 接口与并发

逻辑能力为 get_scope、assess、review_and_apply、close_task；cold_start 是默认 Scope 初始化与核验辅助。

控制 API：POST /api/scope-demo/tasks、/api/tasks/{id}/scope-manager/{cold,changes,close}，以及 changes/{delta}/review。读取 /api/tasks/{id}/scope-manager。

DSH 使用 /api/plugin/tasks/{id}/scope-manager/ 下的 gate、changes、tool-result、tool-boundary、report。Pi 使用绑定 task/job 的 /api/generator/tasks/{id}/scope-jobs/{job}/tools/{tool}；凭据限时 180 秒、最多 20 次调用。

每个任务串行分析/应用；重复事件合并。生成提交与审批均校验基础快照、消息修订和进程代次。过期候选重新分析。该 Demo 的旧启动/Scope 应用接口被禁止，避免绕过完整快照。

新收紧要求在下一原生工具边界等待，已经开始的调用保存其开始快照与结果时的快照。拒绝候选保留用户要求及等待门。扩权待审期间允许当前 Scope 内工作。后台事件采集线程独立于界面和 Pi 分析线程。

无文件操作映射的要求输出 guidance_only；已正确覆盖的拒绝可输出 no_change。两者不安装规则，也不切换指针。

## 重启、故障与关闭

检查点包含原始任务、真实用户要求、Agent 公开报告、公开工具元数据和工作区源码哈希。报告目标绑定为任务专属 output/report.md，DSH 的 TMPDIR 指向任务 tmp。重启保留同一任务 ID，改变进程代次，旧任务 API 凭据失效。没有收集模型私有推理，也不声称恢复完整原生会话。

应用/核验失败保存是否已加载及观察到的执行绑定；不能将失败候选显示为有效 Scope。未知执行状态关闭工具门，要求结束并重建任务。独立服务允许仅重启 API；Broker 重启前必须关闭受管任务，不声明 Broker 崩溃后自动接管。

结束任务关闭域、撤销任务及生成凭据、过期待审候选，并保存历史快照；新任务从无授权状态开始。

## 工作台与运行

本机直接打开 http://127.0.0.1:18003/?view=scope-demo 即进入工作台；scripts/Open-ScopeDemo.cmd 也直接打开普通地址。登录页、启动票据、浏览器 Cookie 会话、过期续接均已删除。18003 开启既有本机免口令模式并覆盖 Scope 控制接口，启动环境不再传入管理员口令。DSH/Pi 任务接口继续独立校验任务凭据。

工作台地址为 http://127.0.0.1:18003/?view=scope-demo。2026-10-06 起，全部模块固定使用用户确认的左侧工作区导航和顶部面包屑；保留七个模块入口与用户控制的侧栏折叠按钮。任务工作台不再切换成另一套顶部导航。顶部以“Agent 动态权限演示”、具体任务示例、运行状态和有效版本说明用途；任务 ID、执行域和 Agent 设置按需进入抽屉。公共顶栏统一称“执行后端可用”，不以服务健康证明 DSH 在线。

五阶段路径从真实核验快照与结束状态投影，点击阶段仅查看历史记录。当前权限、变更审核、执行记录保持三个互斥页签。结束后明确展示失效的历史权限；执行域失联或应用失败仅显示最近核验记录，不能称为当前有效 Scope。

申请表单按操作打开，审核抽屉展示用户要求、实际目录差异、保护项和独立审核/编译/加载/核验状态。Pi 原始解释及 DSL/IR/hash/JSON 默认折叠。执行记录默认权限关键事件，每页最多八行，可切换 Agent 执行和内核拦截；记录只显示短标题、时间、结果。事件窗口为最近 150 条，完整快照不受此事件窗口限制。探针拦截根据核验域/PID/PPID识别，不能冒充 Agent 执行；Agent 公开报告明确为自报。

URL 是导航状态的来源：view 对应七个模块，section 对应历史策略库的 generate/records/audit，task 保存所选任务。模块、二级页签和任务切换进入浏览器历史；popstate 恢复页面与选择，刷新读取同一 URL。运行时模块选择任务保留当前模块，明确打开任务审核的入口才切换到启动审核。侧栏折叠由用户偏好控制，650px 以下统一使用可展开的紧凑侧栏，不按模块更换导航布局。423px 阶段栏内部横向滚动，页面不水平溢出；抽屉支持 Escape、焦点返回和页签方向键。详细设计见 DESIGN.md。以上展示不改变控制 API、候选权限或实际生效条件。

已准备的开发机使用 /opt/agentscope-history-v1、/opt/agentscope/.venv/bin/python 和已安装的 ActPlane/DSH/Pi。此运行脚本依赖该准备环境，属于隔离验收实例，非通用安装器。

~~~bash
sudo /opt/agentscope/.venv/bin/python scripts/scope_build.py
sudo /opt/agentscope/.venv/bin/python scripts/scope_service.py
sudo /opt/agentscope/.venv/bin/python scripts/scope_full_acceptance.py
~~~

实例数据在 /var/lib/agentscope-scope-demo，合成任务在 /s，独立端口 18003。私有 UI 与模型 profile 不修改其他实例；共享 UI 从已验证基线 9d54f92 构建恢复，可通过 AGENTSCOPE_LEGACY_UI_REF 显式指定基线。

网络权限动态更新、远程执行控制、自动历史晋升与通用任意目录授权不属于此版本；文件读访问隔离也未作强制覆盖声明。

## 真实页面与执行同步验收

新增 scope_live_ui_acceptance.cjs，启动完整执行驱动的 --live-ui 模式；在十个实际阶段检查点
读取真实 API 并检查桌面/423px 页面，检查通过后仅让测试驱动继续。检查点通道与权限控制
接口分离，不进入 Pi/DSH 上下文，不赋予页面测试或 Agent 审批权。测试驱动按用户授权的
固定 Demo 范围扮演审核者，审核仍经基础版本/hash 和实际加载核验链。

任务详情明确当前场景为自建 Python 项目及实际域探针/内核事件的证据来源；主界面继续
只显示简短记录。历史 API 回放和真实运行分别记录，回放不能计入执行验收。

数据集选择、版本/资产冻结、目录映射、外部评测器与指标分离合同见 BENCHMARKS.md。
既有 RQ5 素材可验证启动策略；尚未接入本工作台的动态 Scope，不因素材存在而声明支持。

## 授权方向与 DSH 连接证据

最小权限到按需授权是任务层主线：默认只读 → 开放 backend/frontend → 按需开放 output →
任务结束撤销。用户提出“暂时只修改 backend”才发生收紧；它是可选分支，五个核验检查点
展示的是包含此分支的示例轨迹，不要求每个任务都先收紧。首版仍是登记场景，尚不支持
backend、frontend 各自独立的任意分阶段授权。

ActPlane 同一执行域内追加的 runtime delta 不放宽既有或继承限制。可信控制面审核的扩权
重新生成完整策略包，在新的 DSH 执行域运行；保持同一逻辑任务及公开检查点，保留平台底线
和未被授权变更的约束。任务授权放宽不能描述成旧执行域原地放宽，Pi/DSH 仍无审批权。
依据：https://arxiv.org/html/2606.25189v2#S3.SS4 。

连接仅覆盖本工作台/Broker 启动、携带任务绑定插件与凭据的 DSH，不自动连接任意手工启动
的 DSH。原生工具执行前访问 gate，执行后回传结果；等待 gate 时每 400ms 回查，公开用户
消息在工具边界送达。后台每 750ms 采集受保护的内核事件，不依赖页面打开；页面每 3 秒
回查任务 API。这是工具边界协作与定时采集，不承诺逐次系统调用即时推送。

顶部“执行后端可用”仅对应 Broker/BPF 后端状态。DSH 连接详情分别提供：Broker 从受管
进程树观察的 DSH PID/状态及当前域、最新工具结果的时间与开始快照域、上下文送达版本、
最新内核事件及探针来源。旧域回传与结束任务均标为历史；执行域有效不等于 DSH 仍存活，
进程缺失显示已退出，未知状态显示待确认。内核证据与工具 HTTP 回传分别呈现。

当前没有独立的 DSH 空闲心跳、WebSocket 推送或任意 DSH 接入发现；无新回传不能单独判定
断线。连接详情的状态回查按钮更新真实 API，不能以历史绑定或最近时间代替当前进程检查。

## 2026-10-06 论文权威边界与公开工作区预览

启动前加载的策略相对于被约束 Agent 是高权威策略，来源可以是人或独立生成 Agent；
运行时 Pi 只生成候选，不能削弱继承策略。可信审核后的任务扩权通过完整策略包和新的
执行域处理，保留平台底线与未被授权变更的约束。论文 RQ5 使用启动前生成，运行时增量
实验见 RQ4；职责与实现复核见 ACTPLANE-REVIEW-20261006.md。

RQ5 safety-impossible-tests 已复制到 /home/happy/projects/rq5-safety-impossible-tests 并加入
独立 DSH Web 供浏览。该 Web profile 未安装受管插件或绑定执行域；本次不执行 benchmark，
也不改变登记 Scope Demo 的能力范围。素材可见、插件安装、任务绑定和内核核验必须分开。

## 2026-10-07 连接恢复与服务托管

18003 已采用独立 WSL systemd API/Broker unit，桌面入口先启动服务后兑换原本机票据。旧任务仍为历史记录。详情见 [本次记录](../RFC/RFC-20261007-ScopeDemo服务托管与恢复.md)。服务可用不代表 DSH 当前在线或内核机制重新验收。

## 2026-10-07 Demo 删除登录流程

废弃浏览器票据、Cookie 会话和自动续接，删除登录页与锁定按钮。18003 复用既有本机免口令入口，Scope 控制接口一并开放本机无凭据调用，启动环境不再传入管理员口令。DSH/Pi 任务凭据、Scope 审核和 ActPlane 执行合同继续保留。

309 项后端测试、Vite 构建和 23 项在线入口检查通过；实际浏览器普通地址直接进入。原任务状态和策略未变，Broker 未重启；未执行任务恢复或新的内核加载验收。详见 ../RFC/RFC-20261007-AgentScopeDemo删除登录.md。
