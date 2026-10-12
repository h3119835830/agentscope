# 第三步验收材料

源码：codex/agent-scene-step3-20261011，父提交 5e91372。独立页面：http://127.0.0.1:18116/?view=workbench&policyAgent=instance-0452a8e6340b4dfd 。入口：Agent → 策略助手 → 读取场景；提交后到审批查看。

测试命令：`node --test src/*.test.mjs`、`npm run build`、配置已安装 DSL adapter 后 `python -m pytest -q backend/tests`。扫描器和来源过滤复用旧工作区实现。

隔离环境使用合成 Agent 身份、真实项目文件、已配置模型和真实静态编译器，禁止批准和加载。截图中的保护服务不可用反映预览未连接 Broker，不是内核保护成功信号。未发布 18003，未推送远端。

权威状态对比窗口：生成后、提交审批前与提交后；authority-check.json 记录表摘要相同，未写生效配置或加载回执。后端测试另验证读取/生成全程无权限变更。

真实模型的只读语义扩大问题见 BUG GEN-SEMANTICS-001，未批准或加载该候选。截图与测试不能替代真实 DSH 内核闭环。
