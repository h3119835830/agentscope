# 系统共享规则评审与验收

日期：2026-10-10。

## 代码评审

检查后端 policy store、有效策略组合、共享提案/确认、工具租约、实例启动/配置/提案、管理员身份和前端本层编辑。系统 deny 与 Agent allow 同时保留，复用原执行层禁止优先机制；系统 disabled 优先于 Agent model_only。行为约定只展示约定，不声明内核强制。

使用单 API 进程生命周期锁；工具结果释放租约不拿此锁，避免排空死锁。全局更新时新增租约被 SQLite 原子状态检查拒绝。原在线连接重新核验，原停止/暂停连接不自动启动。失败和中断不假报 applied/active。外部改表、多 API 写入进程不在支持合同内。

## 测试与在线证据

新增共享规则生命周期与权限回归，含真实 TestClient HTTP 控制鉴权；执行器适配器在隔离测试中替换为测试实现。前端静态渲染覆盖可编辑系统规则、汇总核验、加载失败、确认影响范围及本层隔离。前端 169 项通过，Vite 83 个模块构建通过；后端全量 880 项通过、52 项跳过，其中新增系统规则 21 项通过。文件组合测试同时验证继承 deny 被实际 Broker DSL 转换为精确 /w/0/secret 写入及删除禁止。既有 bundle 大小和 FastAPI 弃用提示保留。

第一次全量运行因既有测试所需 /tmp/a 目录不存在产生 92 项 setup error；补齐测试临时父目录后全量通过。失败日志与最终日志保存在本地验收目录，未改动相关业务测试。

在线验收只检查既有 Agent 状态、共享存储、规则编辑入口与取消；不为验收擅自确认新增运行规则。新增系统规则在真实内核中的加载/拦截没有因此获得新的验收证据。


## 在线验收与部署

18003 浏览器 6/6 项通过：系统可编辑规则替换固定说明；添加工具规则可填写并提供预览（随后取消）；系统网络可编辑（随后取消）；当前 Agent 既有文件规则保持独立；DSH 与 Hermes 展示同一系统存储和汇总核验；状态列加宽并通过实际 DOM 几何检查，汇总状态不再覆盖操作按钮。实际页面当前无自定义系统规则，没有为验收提交或确认新规则。

部署前以 SQLite 私有备份执行迁移及有效策略 hash 预检，通过后仅更新 API 的 4 个实例配置模块及哈希前端资产。API PID 496 → 9537，重启至健康 1.08 秒；Broker PID 407 未变化。DSH PID 1343、运行代次和有效策略 hash 不变，在线 active；Hermes 继续未连接/执行暂停，没有启动它。Hermes 数据库中的旧 runtime PID 仅为保存信息，不作为当前在线证据。系统 revision=0、phase=ready、匹配受控连接=2、active=1。静态入口 SHA256：ad86268d15f9c008c34f5266f3064c7d2f80a290eb884e964d3919527edcae3a。

未修改 Broker/原生 Agent/内核/普通 ERP 业务，未触碰 18000/18004。部署前后状态与取消编辑后再次检查均未改变现有有效策略或代次。本轮没有新增系统规则的真实内核加载、拦截验收声明。

[测试结果](../acceptance/system-security-rules-20261010/test-results.json)、[浏览器检查](../acceptance/system-security-rules-20261010/browser-checks.json)、[部署记录](../acceptance/system-security-rules-20261010/deployment.json)、[系统规则列表](../acceptance/system-security-rules-20261010/system-rule-list.png)、[规则编辑](../acceptance/system-security-rules-20261010/system-rule-editor.png)。代码完成本地提交，远端推送另需用户授权。

最终间距修复仅替换静态资产，未再次重启 API。截图以实际默认视口保存，未宣称窄屏设备验收。
