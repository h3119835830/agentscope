# REVIEW：AgentScope 本机免口令验收

> 状态：已废弃。2026-10-07 用户要求直接删除登录流程，当前实现见 REVIEW-20261007-AgentScopeDemo删除登录.md。以下为历史方案及当时验收，不代表当前代码。

日期：2026-10-07。状态：本机入口修改已部署，专项验收通过。

## 范围

后端 config/local_browser/main、前端入口及 local-browser 模块、scope-demo 本机配置、相应身份测试和技术文档。已有工作区存在其他 ActPlane/managed/DSL 改动；不得混入本次提交或回退。

## 已完成

- 身份边界专项 26 passed：默认关闭、同源自用连接、过期重连、跨源/跨端口/远端拒绝、任务凭据不提升、Cookie 与原票据边界。
- 前端续接 4 passed：有效会话不重连、401 后原请求仅重试一次、默认部署保留认证、并发连接及错误反馈。
- 18003 私有前端候选构建通过，38 modules。普通用户在 /tmp 的候选输出目录创建被拒绝；改用实例私有状态目录构建成功，未改变目录权限。

## 完整回归与现场结果

- 完整后端 326 passed、3 skipped、5 项已有弃用告警；git diff --check 通过。首次回归为 325 passed、1 failed、3 skipped，失败是既有测试在 /var/tmp 下形成超过引擎 64 字节限制的路径；改用用户专属短临时目录 TMPDIR=/tmp/a 后全量通过，没有修改该测试或引擎限制。
- 18003 私有静态 UI 已部署，仅重启 agentscope-scope-demo-api.service。Broker PID 未变；保留旧 UI 备份，没有更新其他实例静态目录。
- 用户当前普通任务地址直接进入，显示“本机自用 · 免口令”，无口令输入和启动票据；刷新保持同一任务，运行时策略和执行审计可读取。截图为 evidence/local-browser-self-use-20261007/browser-direct-entry.jpg。
- 真实接口 12 项检查全部通过：匿名控制请求拒绝、跨源拒绝、Bearer 不提升、自动连接、控制读取、认证写请求到达参数校验、会话关闭、关闭后拒绝、重新连接、任务 API 仍需凭据、原任务状态不变、Broker 未重启。写接口使用无效治理请求返回 422，不创建策略或治理记录。
- 原任务 d5e21e674b464d16 在修改前已为 failed/gate=failed、策略 v7；修改后 phase/gate/revision/version/session/policy_hash/baseline_hash 全部一致。未恢复任务、未执行模型、未重新声明 ActPlane enforcement 验收。
- 18000、18003 health 为 200；18001、18002 当前不可达，本次未操作其服务。没有普通 ERP 业务文件或数据库迁移变更。
- 接口结果保存在同目录 api-acceptance.json；不含会话 Cookie、管理员口令、模型凭据或模型私有推理。

现有工作区包含其他未提交修改，scope_service.py 的 normalization 支持和其他 ActPlane/managed 改动均予保留；本次没有混合提交或推送。

## 风险与取舍

自用入口显式信任本机用户。HTTP 请求头仅约束网页跨源，不作为本机程序身份保证。默认配置关闭、远端拒绝、执行网络隔离及任务凭据校验独立保留。
