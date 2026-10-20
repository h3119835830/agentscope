# BUG：Pi 工作区读取身份与正式 API 部署不一致

日期：2026-10-20。

## 复现和根因

主服务 18003 中，Pi list_directory 对两个已登记工作区均返回拒绝，
未读取正文；同一 RQ5 DSH 可以读取 task.md 与 README。
当前运行进程 /proc 状态核验：API UID/GID=999/985，附加组 985、986，
有效 capabilities=0。systemd unit 的 User=root 只是启动器身份：
scope_systemd_exec.py 在 exec API 前通过 initgroups/setgid/setuid 降权。

workspace_references.run_reader 要求读取身份 1000/986、无附加组；
非 root API 不满足且无法切换 UID，因此在启动读取程序前拒绝。
旧文档“API 虽以 root 运行”不符合正式进程事实。旧测试模拟当前身份、
或从 root 直接启动 helper，没有覆盖真实 API -> helper 的完整身份链。

这不是 Pi 推理拒绝，不是文件不存在，也不是 /w/0/** 禁止写入导致。
修改提示词、删除子配置、放开文件权限均不能修复部署身份合同。

## 修复与安全边界

采用 ADR-20261020-Pi-reader-inherited-channel.md 的私有继承通道；
保留原身份要求及全部资料守门。基础设施故障单独报错并终止生成。
不改 ActPlane、不改 Broker、不改变文件权限、Agent 策略或数据库合同。

## 验收状态

专门身份与现有读取/上下文回归第一轮 97 项通过；随后补充基础设施
失败不生成候选的回归。完整测试、发布、实际 Pi 界面结果见同日 REVIEW。
在界面正文读取与候选生成成功之前，不宣称生产闭环。
