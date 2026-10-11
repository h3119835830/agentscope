# because 反馈实现与验收

本目录是主技术文档 `C:/Users/happy/Desktop/归纳梳理/技术文档` 中本组 RFC、ADR、REVIEW、BUG 的源码镜像，仅调整了相对链接。总体架构的跨组引用以主技术文档目录为准。

- [RFC：链路与实际字段](RFC-20261011-AgentScope-because-feedback.md)
- [ADR：决策和取舍](ADR-20261011-AgentScope-because-feedback.md)
- [REVIEW：真实结果及 T01–T19 覆盖边界](REVIEW-20261011-AgentScope-because-feedback.md)
- [BUG：复现与关闭证据](BUG-20261011-AgentScope-because-feedback.md)
- [真实验收证据](evidence/live-acceptance.json)；[会话关闭证据](evidence/quiescence.json)

两个真实 Agent 故障恢复场景通过，独立原始测试 13/13，通过全部 8 个保护原件哈希检查和 30 个独立 OS 操作检查。backend 回归 1049 passed / 11 skipped，DSH 回归 21 passed。受控写意图诊断不是自然攻击发生率实验；真实 kill/notify 与完整 A/B/C 扩样没有执行。

源码基线 `12c76464ee000bbae32346d8f3d74caca180e5ea`，运行在独立 18005；本任务未把修改切到共享 18003。两个验收任务已关闭，保留记录和工作区供复核。

## 复跑合同

仅在预先准备好的独立 because 实例运行；依赖现有 ActPlane、BPF/namespace 支持、DSH/Pi 安装和公开 task-python 运行时。`scripts/because_service.py` 会校验资源归属和依赖，拒绝覆盖已有 `/b`；restart 只允许本实例任务已关闭。不要用它操作共享实例。

以受控管理员身份调用下列验收客户端。create 会创建新的冻结场景副本；等待 status 显示两个任务 running 且原生 admission 已 idle 后，再执行 prompt。不要在旧修复工作区重新 prepare/prompt 后当成原始基线。

```sh
/opt/agentscope/.venv/bin/python scripts/because_acceptance.py create
/opt/agentscope/.venv/bin/python scripts/because_acceptance.py status
/opt/agentscope/.venv/bin/python scripts/because_acceptance.py prompt
# 等待原生任务完成，status 中 native_status 为 idle
/opt/agentscope/.venv/bin/python scripts/because_acceptance.py verify
/opt/agentscope/.venv/bin/python scripts/because_acceptance.py operations
/opt/agentscope/.venv/bin/python scripts/because_acceptance.py storage
/opt/agentscope/.venv/bin/python scripts/because_acceptance.py oracle
```

后台迟到探针由已鉴权的 `/api/managed/tasks/{id}/verify-deferred-operation` 触发，只允许登记保护对象的固定 `write_open` deny 检查；必须独立标记 native SDK probe。`scripts/because_evidence.py` 只导出允许字段和哈希，并核对 10 个关键运行文件；不会导出原生私有流。API 重启记录与关闭证据由实验编排器另行保留，不能伪造成每次复跑都自动执行过。

测试日志和历史设计基线保存在 evidence，设计阶段失败结果保留原样。验收结束应通过该独立实例的任务 close API 停止执行域，不手工删除共享运行资源。
