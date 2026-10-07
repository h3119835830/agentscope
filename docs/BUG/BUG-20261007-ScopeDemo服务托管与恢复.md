# Scope Demo 18003 拒绝连接与启动托管缺口

日期：2026-10-07。状态：连接恢复与 API 异常恢复通过。

## 复现与原因

原地址 http://127.0.0.1:18003/?view=scope-demo&task=eada0606a5014c9d 报 ERR_CONNECTION_REFUSED。Windows/Linux 两侧均无 18003 监听，WSL Running，18000/18004 正常。旧 API/Broker PID 不存活，/run/agentscope-scope-demo 不存在。

旧 api.log 最后写入为当天 12:05:57；journal 记录对应 WSL boot 约 12:06 结束，随后多次启动，当前 boot 约 15:01 开始。原脚本只派生后台进程，systemd 没有该实例的 unit。已确认的缺口是 WSL 重启后没有恢复配置；现有证据不能确定 WSL 重启发起者，也不能将先前平台提示归为停服原因。旧日志末尾的 401 不解释端口无监听。

## 修复与验收

先沿用原入口恢复，确认 Broker active 为空，再核验新进程身份并交接给独立 systemd unit。两个 unit 已 enabled/active，桌面入口先启动服务后兑换原票据。

18003 health 与静态入口均 200，匿名任务读取仍 401。模拟 API 主进程异常退出后，PID 753710 自动恢复为 753848，NRestarts=1；Broker PID 753707 保持。18000/18004 的 PID 385/425957 保持且 health 均 200。

浏览器请求日志显示原地址、票据兑换及页面数据读取均 200。自动浏览器检查因 URL 协议策略限制被拒绝，未取得新的可视截图。旧任务仍 completed、effective=false；没有执行旧任务或重新验收其内核机制。

WSL 反复重启原因及完整 WSL 重启验证仍未关闭。详见同名 REVIEW 与 recovery.json。
