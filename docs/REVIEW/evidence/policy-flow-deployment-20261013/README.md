# 18003 新策略链路发布（2026-10-13）

用户授权运行新内容，更新既有 18003 API/UI。未推送远端。

- deployment.json：API 发布目录、UI 摘要、读取检查和受控实例身份前后相等；私有 DB/UI 备份不入库。
- frontend-regression.txt / frontend-build.txt：262 项通过、生产构建成功。
- agent-18003.png：Agent 长期基线与工作区入口。
- approval-impact-18003.png / approval-impact-mobile-18003.png：原待审批记录的产品名/PID、新独立批准按钮。

本次发布没有批准/应用现有策略，也没有用现有实例执行探针。真实模型、两阶段操作、OS 阻止及反馈继续的证据保留在前一份 20261013-agent-policy-flow 验收，不把两者混为一次运行。

- session-18003.png：既有会话默认新增约束，继承规则默认折叠；浏览器错误日志为空。
