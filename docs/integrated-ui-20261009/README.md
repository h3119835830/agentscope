# AgentScope 合并界面原型

日期：2026-10-09。状态：可点击的独立 HTML 原型，未接入真实运行时。

入口：`docs/prototype/AgentScope-合并界面原型.html`。支持直接打开或静态 HTTP 预览。

## 页面分工

| 入口 | 内容 | 配置归属 |
|---|---|---|
| 总览 | 当前连接记录、服务职责列表 | 点击记录进入具体会话 |
| 会话 | 安全规则、运行关系、工作区、执行记录、策略版本 | 继承只读，本地规则保存草案 |
| 审批 | 共用变更记录，支持按会话过滤 | 会话和审批引用同一提案 |
| 策略库 | 15 类模板与研究来源 | 跳到平台底线的同一个编辑器 |
| 系统 | 安全底线、服务与能力 | 平台默认配置与新基线草案 |

模块名只在导航出现。反馈、DSL、能力边界和证据放在详情。

## 演示路径

1. 总览在连接记录里点“查看会话”，进入该会话的 Agent 关系图。
2. 点“测试 Agent”，看进程内对象说明和目标 D-A1；点“查看约束”，进入同一张规则表。子 Agent 不虚构独立 PID。
3. 切换“Agent 关系 / OS 进程 / 策略域”。OS 图只展示共享宿主及工具进程样例；目标域继承不等于实际 OS 绑定。
4. 点“会话如何运行”，查看创建/恢复、消息执行、回复后空闲、停止/恢复；详情区分 Web 与一次性 headless。
5. 会话点“待处理”，进入统一审批；保存草案后两个入口状态同步。
6. 策略库查看 SSH 模板，再到平台底线配置；修改平台草案后，现有会话继承快照仍保持 v0.1。

所有连接、PID、域、工作区与会话均为样例；没有进程扫描。D0 是模型来源，不证明运行时存在全局 D0。连接、加载、实际保护分别表示；执行记录保持空状态。

## 会话是否一直开着

依据本机 DSH 0.2.0-rc.2 代码：Web 宿主通常常驻，Session 是 ID/历史及运行时 Agent 对象的逻辑关系，不默认拥有独立 OS 进程。发消息进入运行，回复结束进入 idle；后续消息可重用存活 Agent，也可从历史恢复。对象受宿主与运行时生命周期管理，不承诺一直驻留。关闭浏览器、取消本轮、停止宿主是不同动作。

一次性 headless 等待 whenIdle，保存会话后调用 exit；不能套用到 Web 会话。工具 shell/后台任务寿命需另查，不能因回复完成就推断全部退出。当前平台 managed controller 使用 native SessionController，不是 headless 替代会话。

如果多个会话/子 Agent 共用宿主 PID，就不能仅靠该 PID 实现各会话的 OS 策略隔离。正式接入需核验可信执行身份、工具调用归属、实际进程/域绑定及内核证据。本轮只修正设计表达，不实施新隔离机制。

代码核对是只读检查，不代表运行实验：

| 本机源码 | 行 | 核对事实 |
|---|---|---|
| /opt/agentscope/dsh/node_modules/@deepseek-ai/dsh-api-session-controller/lib/index.js | 208–233、372–388 | 查找 live Agent，必要时恢复会话 |
| /opt/agentscope/dsh/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js | 781–786、860–875、1851–1891 | idle/running、whenIdle、进程内 Agent 创建 |
| /opt/agentscope/dsh/node_modules/@deepseek-ai/dsh-headless/lib/index.js | 329–345 | followup → whenIdle → flush → exit |
| /opt/agentscope/dsh/node_modules/@deepseek-ai/dsh-subagent-in-process-driver/lib/index.js | 111–120 | 进程内一次性子 Agent driver |
| /opt/agentscope-history-v1/backend/agentscope_app/managed/controller.py | 365–366 | native SessionController admission |

## 构建与证据

执行 `python docs/integrated-ui-20261009/build_prototype.py`。构建器复用已验收规则表、编辑器、反馈校验与能力限制，嵌入同一 catalogue；新增壳层为 app.js 与 integrated.css。原有两个 HTML 保留。

首版 35/35 浏览器检查见 evidence/checks.json。连接列表与生命周期修订 25/25 项浏览器验收通过，记录单独存放 evidence/session-lifecycle/；不复用旧图布局结果。草案仅保存在内存，刷新回到初始样例。

未修改 React、后端、ActPlane 或正式服务配置；没有批准、加载、绑定或执行真实规则。正式接入不能用原型节点代替运行时证据。
