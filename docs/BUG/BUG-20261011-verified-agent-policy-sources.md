# BUG-20261011 DSL 来源仍使用通用符号或产品推断

状态：已修复，自动测试与真实 18003 页面验收通过；未应用策略。

## 复现与原因

打开系统/Agent DSL 导入编辑器，空草案的 placeholder 仍展示 source AGENT = exec "**"。模板前端与自由描述后端另有按 DSH/Hermes 产品名推断 **/node、**/python 的重复实现；这不能证明当前连接实际使用该程序。

修复初版直接读 /proc/PID/exe，在单元测试账号下通过，但真实 API 使用 agentscope-api 独立账号，目标 Agent 由另一身份运行，因此读取被拒绝。界面正确失败关闭，却仍无法给用户提供来源；这项部署权限差异已在真实验收中补齐。

## 修复

增加服务端共享运行来源读取；核验受控连接完整身份，读取实际 proc 执行程序。权限隔离场景通过受信任只读 observer 提供新鲜、身份匹配的最小事实。编辑器新草案、模板和自由描述上下文共享结果，移除通用占位及产品推断。旧导入保留原文，由用户显式更新本地 AGENT exec 来源，再走原有保存校验和确认。

## 验收闭环

当前 DSH 实际程序 /opt/agentscope/bin/node，编辑器和模板为 source AGENT = exec "**/node"；未连接 Hermes、身份变化和过期事实均阻止猜测。前端 218 项、后端 964 项通过，52 项按既有条件跳过，构建成功。真实页面已保存截图与只读 API 事实；发布前后 Agent、策略、proposal 与 Broker 状态未变。没有策略应用授权操作。

详见同名 RFC/ADR/REVIEW，以及 evidence/runtime-sources-20261011。

## 2026-10-11 关联隔离复核

用户追问 **/node 会否影响其他 Node。复核确认 basename 会重合，实例隔离来自连接 ID 编排及非零进程域绑定；未复现独立连接串用问题。新增同名/同程序/同工作区跨 DSH 与 Hermes、跨连接 confirm、实际 BPF C 域判定测试，69 项通过；真实两个域外 Node 不在 DSH 绑定内，现有草案目标仅为当前 DSH。详见 REVIEW-20261011-agent-node-isolation。未应用策略。
