# 会话与进程呈现整改验收

日期：2026-10-09。基线：03ebc7d。实现提交：42564d0。分支：codex/session-processes-20261009。

## 范围与边界

修改 Agent连接前端、会话名称的只读 API 投影、隔离 Hermes 原生插件及相应测试。无策略生成、批准、加载、lease、拦截、Broker 生命周期或普通业务代码修改。原 process_ids 保持不变。

## 测试与候选验收

- 前端测试 160/160 通过，Vite 84 modules 构建通过。
- 后端定向回归 76/76 通过，覆盖原生地址边界、只读调用协议、白名单字段、会话和目录关联、名称失败退化、generation/PID 缓存隔离、Hermes 已保存/运行会话名称合并，以及现有实例权限、生命周期和连接合同。
- 候选页面 8 项浏览器检查通过。预览使用新元数据代码从实际 DSH 读取的只读快照：7 个会话、6 个原生名称、2 行共享执行 PID、5 行未运行。
- 初次响应式检查的视口落在另一个选中标签，测量无效，已撤销两项结果；已在正式选中页面重新验收，不计入候选通过数。

## 正式环境验收

18003 API 已加载新名称投影；GET sessions 返回 7 个实际会话，6 个名称非空，2 行关联 PID，其余没有 process_ids。正式页面 11 项检查全部通过：移除入口、新构建、会话名称数量、完整 ID 与 PID 对应、单一四字段表格、423px 和 320px 布局、刷新、安全配置与连接设置回归，以及无浏览器错误。

423px 下实际视口、页面和抽屉均为 423px，表格为 680px，在 392px 容器中横向滚动，完整 ID 可换行显示。320px 下视口、页面和抽屉均为 320px。最终截图保存在本地 session-processes-acceptance/live-sessions.png；真实名称与 ID 截图不纳入仓库。

测试仅执行读取、导航和刷新，没有新建会话、提交 prompt、启动/停止实例或修改策略。

## 部署核对

控制台 API 重启耗时 1.017 秒，新 API PID 为 44112。Broker PID 381、DSH PID 8401 及其 start_ticks 保持不变；未重启它们，未操作 18000/18004。

静态入口通过原子替换更新，旧入口摘要经部署前后双重检查。最终 index SHA-256：9ad81e84cb53acaa67b54c3a52d942162df7e0c2b80e911714674947d085255c。资源为 index-mYd7LBYJ.js（3a09dcdc7fece97f39af03a43a8ad189aadf0da240b86b627b4a84cab5a20f77）和 index-D6h7E5IB.css（061ee260fc89ccec8a0edd95a206b32f1c01ddbdb6bf7b982a2dd94a6a4865df）。旧入口保留在 /var/lib/agentscope-scope-demo/backups/session-processes-20261009/index.html。

## 限制

Hermes 当前未运行，只完成隔离插件源码的名称投影测试；当前运行 Broker 未重新加载此插件源码，没有启动 Hermes 做运行验收。会话名称是展示元数据，不构成内核拦截或进程域保护结论。此次修改已本地提交，未推送远端。

证据：[checks.json](../acceptance/session-processes-20261009/checks.json)。
