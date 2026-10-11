# REVIEW：系统策略 UI 预览验收

日期：2026-10-11。范围：独立 UI 和确定性 DSL 生成；不包含生产部署/加载验收。

## 结果

| 验证 | 结果 |
| --- | --- |
| 模型测试 | 8/8；后缀/文件名/目录边界、三动作、多目标、标签依赖、无效字段、全体范围与能力提示 |
| 真实编译器 | 12 类 × 3 动作，36/36；真实 ActPlane compile JSON 支持；未加载 |
| 搜索与分类 | 无结果可清空；凭据分类 3 条；恢复完整 12 条 |
| 配置联动 | notify、kill、block 切换同步更新 DSL |
| 路径对照 | `.env.local` 不匹配 `.env` 后缀；文件名模式不匹配 production.env；后缀模式匹配 |
| 保存与刷新 | 配置在预览 origin 持久化，未配置项不可勾选 |
| 批量选择 | 两项已配置策略可选择；影响预览没有具体 Agent 勾选控件 |
| 全体范围确认 | 所有受控 Agent、停止实例后续继承；人工确认不绕过能力阻塞 |
| DSL 导入 | 两个 rule 和来源声明完整回读；保持待校验、不可载入 |
| 必填对象 | 未填写策略目录不能保存 |
| 跨事件 | 改变敏感后缀后，来源声明和 AGENT and SENSITIVE 条件均保留 |
| 布局 | 默认约 1024 宽、1280×900、600×800；无页面横向溢出；窄屏操作换行问题已修复 |
| 浏览器日志 | 当前预览无 error/warn；恢复默认视口；清除验收导入草案 |
| 实际运行快照 | 前后受控 PID、运行身份、gate、策略 hash、DSL revisions、API 服务均未变化 |

最终浏览器保留 `.env` 和网络审计的两项本地预览配置，均未向运行系统写入。截图：`evidence/system-policy-ui-20261011/`。编译证据：同目录 compiler.json。

## 评审边界与待办

- UI 预览通过，不代表 18003 页面已替换。没有真实策略加载或内核动作验收，不能据此报告生产完成。
- 当前引擎缺少文件后缀能力；应单独实现并在受控、隔离环境进行真实 block/notify/kill 验收，再接通此配置。此次未改动引擎。
- 预览的 runtime.json 是明示时间的只读目标快照。正式页面需实时聚合、按版本能力和当前连接重新校验。
- DSL 导入后续必须接真实 parser/编译器与命名空间映射，不能把草案声明检查升级为安全校验。
- 生产流程还需 CAS、过期候选、系统并发变化、继承不可解除、部分加载失败和停止连接行为验收。
- 未修改普通业务代码，未启动、停止或重启 Agent/18003 服务，未触及 18000/18004。

## 复现命令

```sh
node --test docs/prototype/system-policy-studio/model.test.mjs
node docs/prototype/system-policy-studio/verify-compiler.mjs
/opt/agentscope/.venv/bin/python scripts/agent_policy_runtime_snapshot.py /tmp/system-policy-ui-after.json --compare /tmp/system-policy-ui-before.json
```
