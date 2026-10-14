# BUG：启动配置、逻辑会话与执行边界混为一层

- 日期：2026-10-14
- 状态：已复现/确认边界缺口，未修复；本轮仅研究与设计。
- 关联：[RFC](../RFC/RFC-20261014-AgentScope-agent-launch-adapter-research.md)、[ADR](../ADR/ADR-20261014-AgentScope-agent-launch-adapter-research.md)、[REVIEW](../REVIEW/REVIEW-20261014-AgentScope-agent-launch-adapter-research.md)。

## B1. 启动命令可配置，但产品执行拓扑仍被硬编码

证据：launch.py 限制 Node/Python/Hermes 可执行入口，DSH 被限定为 Web；instance_runtime.py 按产品准备状态目录、安装接入插件和启动原生程序。

影响：添加命令不能自动获得多 Agent 的原生会话、工作区、取消接口和真实执行绑定。仅配置成功或网页打开，不可称为完整接入。

整改：后续在 AgentScope 内分离 launcher、native adapter、capability 和 execution binding；不修改 DSH 安装源码或原生流程。本轮未改应用代码。

验收门槛：至少 DSH、Hermes 和一个命令型 Agent 的启动/附着/打开/停止所有权有真实证据；能识别共享服务与启动器退出，不误杀其他连接。

## B2. 共享执行器不能承诺工作区/会话独立强制执行

证据：当前实例观察返回 executor_shared=True，policy_targets.capability 拒绝局部加载；已安装 DSH Web/SDK/ACP 和 Hermes ACP/compute host 都有同进程逻辑会话路径。

影响：目标范围可以是工作区或会话，但现有进程域上的加载仍是实例范围。移除某一下层候选不应影响其他会话，当前尚无完整执行闭环。

整改：先核查原生 I/O 和生命周期拓扑，再复用已有执行边界或评审其他入口；不按 sessionId/cwd 伪造独立域，也不把局部规则升为 Agent。未发布工具拆分草稿已撤回，不作为修复结果。

验收门槛：A1/A2 同属 A、B1 属 B，另一个 Agent 作为控制组。工作区变更仅影响 A1/A2，会话增量只影响 A1，停止/停用不误伤其他目标，并保留 OS 结果、可信绑定和句柄撤销证据。

## B3. 私有接入 profile 改变原生运行设置，边界说明不足

证据：prepare_home 复制 AgentScope 插件并改私有 cordis.patch.yml；现有插件将 sandboxPolicy.resolve 返回的 mode 覆盖为 danger-full-access，依赖外部 namespace/ActPlane 保护。

影响：虽然没有改 DSH 安装源码，但不能说接入完全没有影响 DSH 的运行配置；与用户要求的通用外部适配存在耦合。

整改：后续明确外部监督与原生运行配置的职责。研究阶段不再增加注入，不静默删除旧配置造成保护断档。是否迁移、如何验证保护连续性需在具体实现方案中评审。

验收门槛：原生 workspace/session/tool/sandbox 行为保持原义，AgentScope 能证明其负责的执行保护范围；不能靠移除工具或定制提示词得到表面通过。

## B4. 截图只出现 tmp 被误解为 Linux 不支持桌面项目

证据：现有 runner 的 HOME 是受控 state，资源以 /w/N 暴露；当前老 DSH 连接 launch=None、只绑定旧资源，不自动包含新的桌面测试目录。

影响：用户在原生选择器默认 HOME 视图看不到桌面路径，容易把授权映射问题误解为原生 Agent 被改坏。

整改：在 AgentScope 的连接详情展示宿主环境、原生 cwd/文件视图及已授权目录，给出真实可选路径；不得为改善目录可见性静默扩大授权或重新指向旧 workspace ID。

验收门槛：用户按原生目录选择方式添加授权目录后，AgentScope 显示同一个 native workspace ID 和文件夹；未授权目录有明确状态，Windows/WSL 路径映射不冒充身份。

## 本轮关闭的过程问题

独立工具进程方案在未核查多 Agent 启动方式前被提前推进。用户纠正后，本轮草稿从工作区撤回，隔离服务停止，未部署到 18003；该过程问题已纠偏。B1–B4 的运行能力缺口仍保持未关闭，不以研究文档代替修复验收。
