# Scope Demo 服务恢复验收

日期：2026-10-07。结论：页面连接、服务托管与 API 异常恢复通过。

## 修改范围

新增 scripts/scope_systemd_exec.py 和两份 scripts/systemd/agentscope-scope-demo-*.service；修改 scripts/Open-ScopeDemo.cmd 并同步桌面入口。运行环境沿用原实例，API 实际仍为 agentscope-api 用户。未修改普通 ERP 代码、业务接口、任务资产或凭据文件。

交接前 Broker active=[]，仅停止本次恢复创建、且已核验环境身份的两个进程。API 自动恢复与 Broker 生命周期分别托管。

## 实测

|检查|结果|
|---|---|
|Python 语法、systemd-analyze verify|通过|
|18003 health、静态入口|200|
|匿名任务读取|401|
|旧任务 eada0606a5014c9d|completed，effective=false|
|API 异常恢复|753710 → 753848，NRestarts=1|
|Broker|753707 保持|
|其他实例|18000/18004 PID 保持，health 均 200|
|浏览器客户端网络请求|原地址、票据兑换、页面数据均 200|
|完整 Git diff whitespace 检查|通过；未提交工作区原有其他改动|

数据见 [recovery.json](evidence/scope-service-20261007/recovery.json)。

## 限制

浏览器工具拒绝检查原错误标签页，理由为 URL 协议策略限制；没有新截图。因此客户端网络成功只证明资源、身份与数据请求恢复，不能独立证明全部组件显示正确。

未重启整个 WSL，仅核验 enabled 配置；Broker 不自动恢复或声明接管旧任务。服务健康不证明 DSH 在线，也不替代旧任务尚未完成的内核验收。WSL 反复重启的发起原因仍需另行取证。
