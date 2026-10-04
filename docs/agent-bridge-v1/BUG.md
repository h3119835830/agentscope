# BUG-20261004：外部 Agent 桥接验收的 DSH 依赖实例冲突

状态：已复现、修复后真实验收通过；最终回归记录见 REVIEW。

## 现象与复现

独立 18002 验收任务 `dae063d75e264e46`、`5de25b6402254196`：HTTP 适配器
收发成功，DSH 首次工具调用失败，诊断
`Cannot read properties of undefined (reading 'prepare')`，不存在 DSH 桥接连接。
失败验收 JSON 作为 previous 记录保留；未复制模型私有推理或原始会话到技术文档。

## 原因与修改

CLI 来自 `/opt/agentscope/dsh/node_modules`，headless/base 与新插件解析自
profile 依赖树。`dsh-tools` 的内部 scheduler 使用模块级 Symbol；跨树导入
得到不同实例，工具调度读取不到当前 registry 的 scheduler。

`scripts/history_service.py` 改为优先使用独立 profile 内 CLI；验收安装将
插件 peer 链接到同一 profile 依赖根。仅更新独立预览文件；共享原始依赖树
未修改。未修改 Agent 提示词来绕过失败。

## 修复验收

真实任务 `9cb6ce0e51bc42f1`：DSH 读取 Scope、反馈进展、接收并处理用户消息、
申请 Scope、收到拒绝通知并确认、反馈完成，进程退出码 0；HTTP 适配器同样
完成通信。结束后接入凭据撤销；历史策略库指纹不变。消息处理回执是 Agent
自报，本 BUG 的验收不证明新增内核规则拦截。
