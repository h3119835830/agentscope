# RFC-20261011 Agent 自由描述策略的环境适配与会话选择

状态：实现；继承 20261010 Agent 策略集成 RFC，闭合其中尚未完成的自由描述环境适配。

## 职责与数据流

用户在简洁策略助手中选择真实 Agent。服务端通过 Broker 已核验的连接、当前代次和原生会话映射取得执行目录；只有唯一当前会话可自动选择，有歧义时显示原生会话选择器。资源挂载不冒充原生项目工作区；此处核验的是该会话实际执行目录。会话目录继续不展示工作区页签、工作区字段或连接信息。

流程为：自然语言不可变输入 → 完整性复核 → 通用文件对象适配计划 → 服务端路径核验与不可变适配版本 → PolicyIR → 作用域检查与确定性 DSL 渲染 → ActPlane 编译 → 持久生成候选 → 对应会话选择 → 当前 Agent DSL 草案 → Broker 实际资源/运行后端校验 → 用户确认 → 既有加载流程。

模型计划中的每个文件对象必须以原始用户描述的逐字片段定位，服务端解析相对路径与已登记的宿主/执行路径映射。禁止越界、非规范路径、符号链接改指、客户端自报环境。不读取文件内容、凭证、环境变量或完整进程参数。不存在的明确目标标为 future_path，支持保护未来创建的文件，不能宣称已读取或已存在。

## 接口合同

- GET /api/agent-instances/{id}/policy-context?session_id=：会话选项、自动选定会话、环境摘要、context_hash；product GET 投影使用 /api/console/agents/{id}/policy-context。
- POST /api/history/inputs 增加 agent_context={instance_id,session_id,context_hash}。只接受选择凭据；workspace、runtime 等客户端自报字段被拒绝，不能同时绑定旧任务。
- GET /api/agent-instances/{id}/policy-conversation?session_id=：服务端持久关联的最近 12 轮生成；不依赖某个浏览器标签页的 sessionStorage。
- GET /api/agent-instances/{id}/policy-candidates/{artifact_id}：复核目标、环境、产物 hash、编译、完整性与拒绝/归档状态，返回带 generation_binding 的 DSL 候选。GET 不保存、不审核、不加载策略。
- DSL documents 的可选 generation_binding={artifact_id,context_hash} 由 canonical_documents 保留并约束。新增或修改的生成文档在 propose 与 apply 前重新检查。已应用的原文档不会因执行器正常重启而失效；手工编辑 DSL 会脱离生成关联，作为独立、仍需用户确认的 DSL 草案。

## 运行与安全边界

环境绑定记录精确实例、原生会话、执行目录与宿主映射、目录 inode/device、资源集、Broker 代次/PID/start_ticks/domain/host/boot、实际准入启动配置、权限 hash、系统与 Agent DSL 修订/hash，以及该后端能力事实。文件适配另外固定对象存在性和 inode/device。生成前后、选择、保存校验和最终确认前均检查环境变化。所有接口沿用现有管理员/本地开发认证，不扩权、不增加 Agent 自我批准能力。

2026-10-11 来源读取修订：DSL source 现由实际已核验进程执行程序产生，不再按 DSH/Hermes 产品名称推断 Node/Python。当前 DSH 的 /proc/PID/exe 为 /opt/agentscope/bin/node，故 source 为 **/node；离线连接等待核验，不猜测 **/python。进程域仍由 Broker/ActPlane 保证，exec 字符串不是独占实例证明。读取权限与只读观察器合同见 RFC-20261011-verified-agent-policy-sources。实例后端的 open/read/write/unlink 能力与旧任务说明分开。静态编译、运行后端校验、加载、活跃绑定、内核命中、反馈送达分别陈述。

## 会话与应用范围

生成候选精确关联产生它的 Agent 与原生会话。会话界面提供结构化记录式“选择生成策略”。当前原生会话共用执行器，所以选中后导入的是该 Agent 的共享策略；应用影响其所有会话，文件目标仍限制在已核验目录。界面在选择和应用预览中明确说明这一点，不能声称获得单会话独立内核域。

策略应用继续只由用户点击“确认并应用到当前 Agent”。本轮真实验收仅保存并校验候选，未执行确认、加载或内核拦截验收。


第三步修订：上述自由描述环境适配本身继续只核验路径；显式的 Agent 场景读取可将受限且清理的项目文本交给模型，见 [第三步合同](RFC-20261011-AgentScope-agent-scene-step3.md)。scene_id 绑定及批准前复核替代“任何路径都不读文件内容”的笼统表述。
