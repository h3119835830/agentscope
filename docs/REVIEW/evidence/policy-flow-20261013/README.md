# Agent 长期基线真实闭环验收

日期：2026-10-13。源码基线 2a49d53，独立分支 codex/agent-policy-flow-20261013。真实页面 [Agent 助手](http://localhost:18173/?view=workbench&policyAgent=instance-2a90b4a7e84f4241&policyScope=agent&agentPolicyTab=assistant)，此前 57190 原型和 18003 发布不作为本轮运行证据。

- 后端：1176 passed，11 skipped；前端：262 passed；生产构建通过。
- 真实模型零会话生成 → 浏览器提交 → 批准不变权限 → 显式应用并加载 → 会话只读继承。
- 两个 DSH 共用仓库/执行程序。明确赋予合成目录写权限后，A 读取成功、写方式打开及截断 EPERM，B 同操作成功；匹配当前代次的编译引用和内核域。
- 工具拒绝结果持久化、模型 delivery-accepted 回执、后续工具结果及任务完成分别取证。
- 恢复验收仅暂停 B，不应用候选、不自动重试；A 继续运行。B 仍保持暂停，供查看失败状态。
- 工作区和原生会话独立应用仍禁用。没有可信会话标签的内核事件不冒充本会话命中；本轮没有声称结构化 ActPlane 反馈注入已完成。

## 证据

| 文件 | 含义 |
| --- | --- |
| runtime.json | 原生成、批准/应用前后、加载、内核与原生反馈/继续执行 |
| recovery.json | 持久化 applying 窗口故障注入和真实 API 重启 |
| deployment-manifest.json | 代码/制品摘要、远端分支和独立部署事实 |
| backend-regression.txt / frontend-regression.txt | 全量测试最终统计 |
| frontend-build.txt | 生产构建，现存 bundle 大小提示 |
| approved-waiting.png | 最终待应用 UI；用于截图的候选已撤回，从未应用 |
| agent-assistant-desktop.png / agent-assistant-mobile.png | 简洁助手及已应用记录 |
| agent-configured-desktop.png / agent-configured-mobile.png | 本范围配置表 |
| session-inherited-desktop.png / session-mobile.png | 只读继承，未产生会话独立约束 |
| offline-draft-restored.png | 未运行 B 保存草案/材料及刷新恢复 |
| foreign-session-error.png | 错误目标不会显示原会话策略 |

首次模型证据定位失败保留为失败版本；第二版暴露 truncate 动作 schema 缺口，修复后第三版通过。首次探针两边 EROFS 仅证明只读挂载，后续 EPERM/B 成功才证明 Agent 约束不同。不要把失败版本或预览截图当作当前加载状态。

## 复验入口

已有 ActPlane 和 DSL adapter 制品与起点代码一致，未改 Broker/BPF。使用 scripts/policy_flow_acceptance_service.py start 建立独立环境；已有状态更新仅用 start --api-only。完整测试使用 /opt/agentscope/.venv/bin/python -m pytest backend/tests -q，以及 frontend 中 node --test src/*.test.mjs、npm run build。root 采样器和独立缓存由实验服务管理，不能指向生产身份缓存。

scripts/collect_policy_flow_evidence.py 只从既有合成会话抽取固定测试 JSON、送达序号、编译匹配和运行身份，不输出原始会话或模型私有推理。scripts/accept_policy_flow_recovery.py 只针对该实验 B 注入中断，运行前要求两个实验实例已显式启动；不会自动恢复被暂停的实例。

本轮已实现并本地提交，未推送远端，未替换 18003 服务。RFC/ADR/REVIEW/BUG 与仓库界面合同已同步。
