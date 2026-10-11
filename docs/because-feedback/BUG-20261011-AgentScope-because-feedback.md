# AgentScope 规则原因在 managed 反馈中被通用化

日期：2026-10-11。状态：已修复并关闭，两个隔离真实 DSH 场景验收通过。复现基线：当时运行目录 `/opt/agentscope-system-policy-20261011-161846` 的 managed 反馈 formatter；修复运行目录 `/opt/agentscope-because-feedback-20261011`。该记录描述与本轮 because 指导目标之间的缺口，不宣称既有完整恢复功能发生了回归，也不据此宣称可绕过 OS 策略。

## 复现

直接加载 `backend/agentscope_app/managed/feedback.py`，传入合成的已阻断事件，令 `raw.rule.reason` 包含标记 `BECAUSE_GUIDANCE_MARKER` 和具体实现修复建议。返回值中的 reason 固定为 `The execution environment denied this operation.`，alternative 也固定为通用建议，不包含标记或规则专属原因。

独立脚本只调用无副作用的 formatter，事件为合成输入。它证明格式化行为，不证明真实内核事件、实际投递或模型响应。复现脚本和源码哈希见 [design-checks.py](../REVIEW/evidence/because-feedback-20261011/design-checks.py)，结果见 [design-checks.json](../REVIEW/evidence/because-feedback-20261011/design-checks.json)。

## 影响与原因

旧即时和延迟反馈链路都调用 operation_feedback；因此即使规则包含 because，managed 视图仍会丢弃具体解释。旧 formatter 保留了任务路径脱敏，但没有关联获批规则快照和恢复元数据。该缺口可能妨碍 Agent 找到允许路径；本轮没有对原因丢失与任务成功率做统计因果实验。

设计阶段 collector 仅处理 blocked 事件、独立 integrity 子集与 protected registry 范围差异等另列为 RFC 的能力补齐项；未做真实漏洞复现，不在此伪造安全逃逸结论。修复版 collector 已采集支持的 blocked/killed/notify，并按实际版本固定反馈；真实 kill/notify 仍未执行实验。

## 修复与关闭条件

按 [RFC](../RFC/RFC-20261011-AgentScope-because-feedback.md) 接入获批 because、事件身份和 RecoverySpec；保留路径脱敏与来源等级。单元测试证明精确原因保真及错误来源拒绝；真实 RQ5 验收证明反馈入原生上下文、Agent 转入允许路径或提交必要且有证据的审核请求；独立检查受保护文件不变。

仅 formatter 单测、编译或 Hook offer 成功不关闭问题。关闭时附真实运行身份、策略/指导版本、事件、接纳回执、后续行为与功能/安全独立结果。

## 实施中复现并整改的问题

1. 子域运行时 rule_id 重排：清理实验 c34858494cc54296 对 output 的真实阻断编号为 50，离线子域编译编号为 3，导致原始精确编号关联失败并多余调用 Pi。改为校验实际 accepted append 审计中的 rule_provenance，包含真实编号、子句哈希与源哈希；原实验保留为诊断记录，最终验收使用新会话。
2. 冻结测试修复场景过度保护：实验 f4f2cdf76c5a49f6 的候选除五个测试外，还保护四个待修复源码和两个配置，父域加子域共需 140 个槽位，加载被 128 槽位限制拒绝，version 保持 0。根因是预授权自动加载合同未限制额外保护的适用范围。新增结构化 FrozenScenarioEnforcement/1 及校验；超出固定保护集合的候选需要单独评审，不静默裁剪、不因模型结果异常添加专用提示词。
3. 独立环境前置条件：初次试运行缺少 Pi package 链接，启动前即失败，没有加载策略。独立服务增加运行时依赖预检；全量回归补齐已有的 DSL adapter、ActPlane 构建和 DSH 依赖后重新执行。

## 关闭证据

修复在候选内容哈希前生成获批指导，并以实际加载 catalog、规则哈希、domain/engine 身份固定原因。即时 Hook 与后台 outbox 使用同一 canonical 反馈，只有原生 context 事件通过精确文本/session/epoch 校验才解除执行屏障；重复原生事件按 feedback_id 幂等，持久 ACK 与接纳分别记录。

- 测试任务 `cda3d1dd657c4789`：真实内核 551、原生接纳 556；Agent 转入 `rate_limiter.py` 实现修复，独立原始测试 13/13 通过；5 个测试原件及原始 launcher 保持不变。
- 清理任务 `651022bbd43c43d0`：真实内核 587、原生接纳 591；Agent 精确删除缓存，3 个配置/项目原件哈希不变。
- 后台固定 SDK 探针 710、原生接纳 718、持久 ACK 720；两会话磁盘中完整 canonical context 均独立核对。该探针不冒充 Agent 自主动作。
- 两任务 policy/version/epoch 不变，零 kernel Pi job；额外独立 OS 探针 30 项通过。backend 1049 passed / 11 skipped，DSH 21 passed。记录 API 同样返回 canonical because/指导，真实回读通过。

原始 oracle、完整保护检查、功能结果与未覆盖项分别记录在 [REVIEW](../REVIEW/REVIEW-20261011-AgentScope-because-feedback.md) 和 [真实证据](../REVIEW/evidence/because-feedback-20261011/live-acceptance.json)。本 BUG 的 because 丢失与两个场景恢复闭环已关闭，未将扩展故障矩阵或统计实验伪报为全通过。未推送远端，未切换共享实例。

## 2026-10-11 增量闭环：默认指导、Skill 加载与字段可访问性

1. 部分目录原因只有禁止或提醒，未指明下一步。已按 12 条规则补目的、允许路径及审核材料；真实页面逐条核对默认值，保存后 because 等于编辑原文，用户自定义不受目录变化影响，保存未应用。
2. 启动/运行时 Pi 原先 --no-skills 且未传入任何 Skill，单写 SKILL.md 不会被加载。已固定只读挂载、显式 --skill 和 /skill 调用；RPC 测试拒绝缺少发现和未展开正文的情况。原生 SDK 排除环境 Skill，两个真实启动作业均证明正文入上下文。
3. atoms[].reason 用于证据适用性，原用 statement 渲染 because，没有独立反馈位置。新增可选 feedback 接入 candidate_reason；测试确认适用性理由不误入 DSL、反馈变化改变候选哈希、旧格式兼容。
4. 页面首次按反馈原因精确定位超时，公开 DOM 证明包裹 textarea 的 label 混入初始化正文。已设置明确 aria-label 并增加可见行数；12 项打开/编辑、自定义持久化、DSL 预览和 423 宽度复验通过。

验收辅助首次以 root 创建场景，Broker 正确拒绝非服务用户，尚未排入生成作业；脚本改为读取本实例环境后降至 agentscope-api。Skill 校验首次 Windows Python 缺少 PyYAML，改用已有依赖的 WSL 虚拟环境后通过。未修改 Broker 身份边界、安全规则或添加模型专用纠错提示。
