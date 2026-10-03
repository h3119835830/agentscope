# Pi 启动前策略生成：第二层 v1

固定 RQ5 场景迁移到 AgentScope/DSH 的扩展验收。源码模块 `backend/agentscope_app/bootstrap`，七工具扩展 `integrations/pi-policy-tools`，冻结公开任务与原 evaluator 在模块 fixtures 中。论文与制品差异、权限合同和实际验收见本目录 RFC、ADR、REVIEW、BUG。

## 本机使用

隔离 UI/API：<http://127.0.0.1:18001/>，使用已配置的本地管理员身份。原实例 <http://127.0.0.1:18000/> 与 721 条 RQ1 待审数据不参与实验。不要并行启动两个实例的任务域。

在“任务与启动审核”创建三个固定场景之一，启动 Pi，查看逐条候选、历史及参数来源、范围差异和编译诊断。选择 A 或 B 构建整包，再按界面展示的上下文与候选 hash 批准，沿用原启动按钮。needs_clarification 只能查看和重新生成，不能构建加载包。语义 no-op 的新增 DSL 为空，仍保留基础限制及指导项。

```bash
# 安装精确锁定的 Pi 依赖；当前本机已安装
cd /opt/agentscope/integrations/pi-policy-tools
PATH=/opt/agentscope/bin:/usr/bin:/bin npm ci

# 恢复或运行隔离验收，需要本机 root Broker、ActPlane 及模型服务
sudo /opt/agentscope/.venv/bin/python /opt/agentscope/scripts/rq5_run.py
# 新的六次真实运行：旧报告归档，旧工作区保留
sudo /opt/agentscope/.venv/bin/python /opt/agentscope/scripts/rq5_run.py --fresh

# 准备好证据后导出本机只读报告
sudo /opt/agentscope/.venv/bin/python /opt/agentscope/scripts/rq5_publish_local_report.py
```

`rq5_run.py` 顺序执行依赖环境核验、隔离服务、最小允许/拒绝探针、三场景 A/B、同批准版本独立探针、GitHub 手工任务回归、评测刷新和原实例隔离核查。默认恢复已有 journal；启动端拒绝非初始资产或配置漂移。执行中断后可以恢复观察，不能隐式修改批准策略。180 秒/40 工具/两次校验修订由生成器服务强制。

服务入口 `scripts/rq5_service.py start|status|restart-api|restart`。`--use-installed-admin` 仅在没有验收活动任务时采用现有管理员身份，不打印或导出凭据。当前实例已采用该身份。API 重启会撤销未完成生成作业；Broker 重启要求没有活动域。

数据库、私有 journal 与凭据在 `/var/lib/agentscope-rq5-v1`；任务根 `/r` 带独立所有权登记；Broker socket `/run/agentscope-rq5-v1/broker.sock`。不复制原生 DSH replay 至公开报告，不把 evaluator、checkpoint、参考 DSL、探针或历史执行结果登记为 Pi 证据。

## 自动检查与事实分层

```bash
cd /opt/agentscope
.venv/bin/pytest backend/tests -q -p no:cacheprovider
PATH=/opt/agentscope/bin:/usr/bin:/bin npm --prefix frontend run build
```

正式验收为六次自然结束的 DSH；链路和文件保护通过，37 次同版本独立违规探针拒绝并关联内核事件。语义场景 A/B 的原始 evaluator 均 unsafe=true。不要将退出 code=0、安全评分或保护 hash 未变替代任务功能正确性判断。没有 DSH 拒绝事件时只能报告主动行为，不能冒称内核效果。

浏览器报告 <http://127.0.0.1:18001/rq5-report.html>；Windows 原始交付在 `C:\Users\happy\Desktop\归纳梳理\技术文档\REVIEW\AgentScope-RQ5-v1`。公开 evidence.json 含完整候选、DSL、编译、批准回执、工具轨迹、实际事件、原评分、初始布局及独立文件检查。控制页面需要鉴权，只读合成基准报告不具备控制权限。

第三层只读交接：`GET /api/tasks/{id}/bootstrap/handoff`，返回冻结任务、批准版本/hash、绑定回执和事件基线；runtime_governance_enabled=false。
