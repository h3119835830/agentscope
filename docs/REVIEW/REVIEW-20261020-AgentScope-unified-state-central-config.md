# REVIEW：统一状态与集中配置验收

日期：2026-10-20。结论：本期源码实现与隔离回归通过；正式切换、真实受控 Agent 重启、远端推送未进行。

## 基线与隔离

- 工作树 `/home/happy/projects/agentscope-label-flow-20261020`，起点 `3e4e837f80faa6a5cba3dbcb17e789a5ba407db9`；初始工作树干净，已有集中 DSL 管理等提交保留。
- 后端测试使用独立测试数据库、非特权 UID/GID 1000 且清空附加组。严禁为测试通过放宽读取身份校验。
- 浏览器使用 `127.0.0.1:18174`、临时状态目录、两个同名合成 DSH、合成会话/回执；Broker socket 指向不存在地址，所有启动/批准/应用等写请求拒绝。
- 页面持续标明“合成记录，不连接 Broker，不代表真实内核加载”。截图验证布局/状态投影，不证明 OS 拦截、数据外发失败或真实 Agent 任务成功。

## 自动回归

| 检查 | 结果 |
| --- | --- |
| 全后端 `python -m pytest -q backend/tests` | 1497 passed，12 skipped，5 条现有框架弃用警告 |
| 前端 `node --test src/*.test.mjs` | 374 passed |
| 前端 `npm run build` | Vite 构建通过，148 modules |
| Git whitespace 校验 | `git diff --check` 通过 |

本轮新增/扩展覆盖：

- open/paused 但缺回执、8 秒过期、缺少 age、实际 hash 不匹配、PID 重用、出生身份/boot/host/domain/代次不匹配。
- 草案 v3 待审批与应用 v2 分开；新期望配置不修改旧加载名称；停止/历史不把旧回执列为当前加载。
- 实际不可变加载文档唯一匹配版本；相同内容多个版本不猜版本号。
- 未导入 DSL 的启动规则保留显式空 DSL hash 语义；非空 bundle hash 和完整身份仍须一致，缺失 hash 字段不能通过。
- 高级 DSL 记录也只显示服务端配置进度，不再用旧 active/loaded 拼接当前加载状态。
- 同名/缺名 Agent 稳定短标识、无 PID 时可区分。
- 客户端过期、失败失效；页面目标切换与响应序号隔离。
- 精确配置跳转、旧链接兼容、历史工作区范围不提升。
- 标签来源版本/归属、参数-only 文档、审批/应用隔离及既有授权回归。
- 信息流真实前驱/对象关联、缺口/乱序/重复与范围检查沿用原测试；新增实际 rule 映射命中名称、当前代次不因旧 active=false 误标历史、图内进程序号不展示 PID。

12 项条件跳过不计为通过，不将测试夹具解释为真实内核验收。

完整输出（仅规范化行尾空白）：[后端测试](evidence/20261020-unified-console/backend-tests.log)、[前端测试](evidence/20261020-unified-console/frontend-tests.log)、[前端构建](evidence/20261020-unified-console/frontend-build.log)。

## 真实浏览器检查

| 场景 | 实际结果 / 截图 |
| --- | --- |
| 同名连接与运行状态 | 两个相同名称/类型仍有不同稳定短标识；未运行显示“启动并打开”；默认无 PID。[connections](evidence/20261020-unified-console/connections.jpg) |
| 连接配置边界 | 连接/资源登记保留，嵌套策略编辑移除，准确跳转系统。 |
| 会话加载 | 三个页签，真实可读策略名称/对象/动作，旧生成按钮与执行方式列移除。[session-loaded](evidence/20261020-unified-console/session-loaded.jpg) |
| 加载详情 | 明确加载配置 v1，DSL/哈希/PID 默认折叠。[loaded-version-detail](evidence/20261020-unified-console/loaded-version-detail.jpg) |
| 集中配置与保存 | 从会话跳转到准确实例和子配置；隔离库保存新草案 v2 后，加载快照仍显示原名称，未批准/应用。[system-configurations](evidence/20261020-unified-console/system-configurations.jpg) |
| 最终构建复核 | 系统仍准确展开指定子配置；高级 DSL 只显示配置资料与进度，不恢复旧加载结论。[system-final](evidence/20261020-unified-console/system-final.jpg) |
| 全部范围不是授权 | 列表选择全部范围后新增，目标为“请选择范围”，保存按钮禁用。[explicit-target](evidence/20261020-unified-console/explicit-target.jpg) |
| 模板说明 | 默认只读，维护模板为高级入口；保留原版本编辑流程。[template-readonly](evidence/20261020-unified-console/template-readonly.jpg) |
| 运行事件 | 内核命中/工具调用切换，分别显示各自空状态，不合并为同一证据。 |
| 信息流 | 当前会话/共享域可切换，只有实际记录标签；无事件不画传播边，不再误标当前代次为历史。[flow-empty-shared](evidence/20261020-unified-console/flow-empty-shared.jpg) |
| 过期 | 回执超过 8 秒后当前加载表清空，提示未核验，不保留旧绿色行。[session-expired](evidence/20261020-unified-console/session-expired.jpg) |
| 控制接口故障 | 会话清空当前记录并显示失败，不把不可达当作停止。[session-unavailable](evidence/20261020-unified-console/session-unavailable.jpg) |

截图来自多次独立预览启动，合成实例 ID 不同是正常隔离重建，不是正式数据迁移。

## 评审结论与发布前边界

配置进度、运行、当前加载不再互相代替；系统是唯一配置管理入口，助手和会话保持各自职责。按界面 skill 保留记录表、明确人工确认与渐进披露，不做卡片墙。

ActPlane 引擎、Broker 采集行为、标签传播规则、旧 DSL/审批/来源版本均未迁移。本轮没有新的运行时生成、热装载、会话隔离或多人权限系统。

正式发布前需在获准的切换窗口核对实际 API/Broker/ActPlane 版本和现有运行回执字段；旧出生身份缺失时应显示未核验，不应为了绿色而伪造字段。真实 Agent 启停/加载仍需单独确认；本轮没有重跑真实内核外发实验或把合成图作为内核证据。

源码与文档可以本地提交；不得自动推送或替换正式服务。既有未知/不完整/采集失败提示继续保留。
