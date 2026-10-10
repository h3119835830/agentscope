# REVIEW：ActPlane DSL 与独立会话实施验收

范围：18003 独立 Scope Demo，分支 codex/system-security-rules-20261010。本地实施并部署，无远端推送。关联同日 RFC、ADR、BUG。

## 自动回归

- 最终后端 `python -m pytest -q tests`：897 passed、52 skipped。52 项默认环境跳过不等同于通过；实际内核验收另列。全目录 pytest 会收集 RQ5 fixture 并发生重复模块导入，正式入口为 backend/tests。
- 前端 `node --test src/*.test.mjs`：173 passed；Vite 构建通过（86 modules），有 bundle 大于 500 kB 的优化提示。
- Rust ActPlane AST 适配器：5 passed，release 构建通过。最终解析及事件读取合同复测通过。
- 合同测试使用真实 ActPlane parser/compiler，覆盖三动作、多 rule、前序门控与失效、标签传播、特定 exec 谱系及 lineage、变换、原文、命名空间、locked 系统继承、连接局部配置、停止连接、过期候选、并发确认、失败暂停及凭据拒绝。特权生命周期使用替身，不作为真实内核证明。

## 实际加载与执行

- 独立合成连接 instance-bb171d3176b644a2，两个注册工作区、两个原生会话。首轮共用 PID 36521，代次 375a1ee1c744411cb950cc049b0213b0。保存状态与运行 PID 按原生适配器分别展示。
- 浏览器多规则文档导入、编辑及手动确认后，包 SHA-256：8b6322ca063c0be3672f739f223245c339e7f85cbcab208946d4a9c3d084cb45。文档包含前序测试门控、文件标签传播和三动作读取规则。
- 修正日志目录后，0af5dd37b4be4d99bb95f3a22adbe61a 与 566ddd5edaad438f9473d4ea08ec1cc1 两次运行分别验证三动作。各自初始采集 5 条事件全部完成版本／域／子句映射，包 hash 相同。
- 末次 block PID 57123 返回 EPERM、读取未完成；notify PID 57127 读取完成，内核 report 且未 blocked/killed；kill PID 57131 退出、外层返回 137，内核 killed=true。同时核对真实子 PID 已退出及命中子句，不仅依赖返回码。
- 原生 DSH 实际读取合成通知文件，产生 tool_start 与 tool_result(success)。无可信工具内核标签，内核事件未归属会话，反馈送达未取得回执。
- 系统测试策略实际覆盖 3 个受控连接，2 个原先运行的连接加载成功，停止的 Hermes 保持停止。两个连接均取得同一系统 source_ref 的 locked 编译／加载绑定；测试连接明确读取触发 1 条系统 notify 命中。原系统文档原样恢复。
- Agent DSL 仅修改指定连接；测试连接 blocked 时原 DSH 可独立恢复。失败候选、运行代次和未满足断言保留，详见 BUG。

## 浏览器验收

实际控制台完成：独立会话入口、连接跳转、产品与连接筛选、名称／ID 搜索、真实工作区和 PID、四个详情页、原文高亮／行号／复制、原文与加载 DSL 分开、命中详情、工具开始／结果、浏览器前进后退、直接链接刷新、返回目录保留筛选、历史代次选择。

含不支持文件 suffix 的导入文档保存为 invalid，确认按钮禁用；改成明确路径后重新校验、预览影响范围并手动应用成功。停止连接显示已确认待加载，明确启动后才显示当前绑定核验。Hermes 无可信会话／工作区映射时不展示工作区列，不制造数量或路径。

修正页签切换旧数据白屏和短暂误报未核验。最终构建未发现新的页面错误。默认视口可滚动查看全部字段；没有声称完成 423 px 专项验收。

## 交付与边界

- RFC、ADR、REVIEW、BUG 同步到 `C:\Users\happy\Desktop\归纳梳理\技术文档`。脱敏证据：evidence/20261010-actplane-dsl-sessions.json；截图为同目录 directory/kernel PNG。
- 私有原始证据位于独立实例 report：dsl-runtime-acceptance.json、dsl-trace-acceptance.json、dsl-system-acceptance.json、dsl-restart-acceptance.json。公开证据仅摘录合成数据和版本／进程元数据，不导出凭据、模型私有推理或用户会话正文。
- 收尾停止测试连接，保留原 DSH 受控运行，Hermes 保持停止；最终状态写入脱敏证据。18000/18004 未部署或重启。末次完整部署备份为 /var/lib/agentscope-scope-demo/deploy-backups/dsl-20261010-153838。
- 当前 pinned engine 不支持文件 contains/suffix matcher，候选阶段明确拒绝；可用明确资源路径／前缀。采集是匹配事件而非完整 syscall 流；没有 syscall 名、可信任务映射、原文或送达回执时明确缺失。
- notify 证明 report 与操作继续；kill 证明进程终止，不宣称事前阻断。Pi 替换、历史库复用与统一审批中心继续延期。没有修改普通 ERP 业务或 ActPlane 子树。

## 生产会话呈现修订验收

- 前端回归 176 passed，Vite 86 modules 构建通过；保留既有 bundle 大小提示。后端完整回归 897 passed、52 skipped；最终目录过滤修订后 DSL／会话合同 14 passed。
- 新增渲染断言：已知 DSH 产品统一 DeepSeek Harness，旧测试别名和内部 ID 不呈现；原生会话名称／路径照实保留；单一 Agent 省略进程筛选；详情没有运行代次选项；旧代次链接转为当前上下文并保留工作区与目录筛选。
- 部署只替换本次 API 模块与前端资源、重启 18003 API。DSH 当前 PID 54870、绑定及运行状态未改变，Broker／DSH 未重启；停止的 Hermes 和验收 Agent 未启动。18000/18004 未改动。部署备份见后续浏览器验收记录。
- 最终浏览器检查：Agent 连接列表使用产品名与当前 PID；会话详情及策略域无“运行代次”控件和旧登记别名。DSH 原生会话名称与路径保留；second-dsh 工作区精确筛选得到 3 条会话，进入详情后返回保留筛选。停止的 DSH 显示已保存／未运行且没有旧 PID；Hermes 未取得工作区映射时隐藏字段和多余进程选择。四页可访问，旧 sessionGeneration 链接参数被清除并正常显示当前绑定。
- 最终部署备份：/var/lib/agentscope-scope-demo/deploy-backups/session-presentation-20261010-160827。实际进程 PID 54870 和绑定状态保持不变，没有重启 Broker／DSH 或自动启动停止 Agent。截图：evidence/20261010-agent-workspace-session.png。此次验收验证界面和接口，不将自动回归重新宣称为新的三动作内核实验。