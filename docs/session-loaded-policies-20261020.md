# 会话当前已加载策略视图

状态：源码与隔离验收完成；未发布至 18003，未推送远端。
基线：`0d0cd2d`（标签管理／信息流实施后的同一隔离分支）。

## 合同

`GET /api/agent-instances/{id}/sessions/{sid}/policies` 以及 console 投影新增
`loaded_policies`，schema 为 `SessionLoadedPolicies/1`。不改变已有候选审批 API。

- 只读 `instance_policy_receipts` 冻结的加载文档与编译映射；按文档聚合配置名、目标、操作、处置和标签来源。
- 加载证明须匹配当前实例、运行代次、PID、domain、DSL hash、bundle hash，以及运行时保存的 loaded artifact；当前 observer 必须连接且 verified，缓存未过期。已有进程出生身份、boot/host 身份亦须一致。Broker admission 启动方式还要求 protection_fresh。
- `controller.active` 包含最新期望配置比较，不被当作本视图唯一依据。未应用的配置改变不重命名已加载旧版本。显示“已加载”不表示工具准入 gate 已打开。
- 新加载回执额外冻结 start_ticks、boot_id、host_id；旧回执没有这些可选字段仍须通过当前 observer 和 runtime 身份核验。
- 正常状态 `verified`；无法证明当前加载时返回空记录与 `unverified`、`historical`、`observed`。映射不完整为 `incomplete`，仅可展示有完整映射的部分，数量不能称为总数。
- 只接受系统与当前 Agent 文档；缺失文档映射的 namespaced 规则不降级为启动规则。启动规则仅投影已知编译器生成的资源读写保护和 immutable-no-publish。挂载、工具准入、行为指导、网络模式文字不是内核规则。
- 原 `security` 投影保留旧客户端／候选请求的 basis_hash 等兼容信息；新会话页面完全不读取其 controls/status/pending_changes。
- `domains` 接口仅返回系统、Agent 两个节点，计数与本视图一致，不再包含 workspace/session 节点或假设的继承边。

## 界面

移除两项生成按钮、泛化核验横条、执行方式列和编辑约束操作。列表为
“策略名称／对象、归属、操作／处置、状态、详情”，筛选仅全部／系统／Agent。
DSL、配置身份和加载证据放在只读抽屉中按需展开；标签来源展示实际加载版本。
共享域说明始终可见，已加载不等于会话发生过命中。

## 验收

- 后端：1474 passed、12 skipped、5 warnings；前端：360 passed；Vite build 成功。
- 新后端用例覆盖：真实编译后配置聚合、双归属、旧加载名称冻结、历史与停止、无回执、运行代次／PID／domain／哈希失配、PID 出生身份变化、缓存过期、缺失映射、错误归属，以及仅 gate 关闭但加载保护仍有新鲜核验的区别。
- 浏览器真实加载验收：隔离 API 18173、隔离 Broker/DSH 与真实内核加载；`scripts/accept_label_e2e.py --keep-preview` 成功，使用合成秘密及本机接收端，未调用模型。
- 实际列表仅有“合成秘密禁止外发”和系统内置发布边界；两类筛选、来源 v1 抽屉、技术证据折叠、两节点范围、600px 布局均检查。阻断单一读取请求时清除旧列表并显示中文重试提示；恢复后重新显示；停止测试 Agent 后 `historical`、records=0。
- 测试实例 `instance-bc03d44900f748b6`；state `/var/tmp/lf-z_ae90wa`。隔离服务已停止，生产 18003 仍为原 PID 452。
- 截图与外部 RFC/ADR/REVIEW/BUG 位于 `C:\Users\happy\Desktop\归纳梳理\技术文档`。

## 限制

这是 observer 最近一次核验的当前加载快照，不是逐毫秒内核查询；页面沿用 7 秒刷新。未知／历史保护不猜测为当前状态。旧合成启动规则回执不能恢复原始配置作者，抽屉明确标记未细分原始归属。没有改变执行域隔离、内核 hook、网络覆盖、审批授权或实际处置能力。
