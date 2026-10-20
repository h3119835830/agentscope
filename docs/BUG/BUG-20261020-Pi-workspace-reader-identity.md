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

状态：读取身份缺陷已修复并发布。
完整后端 1521 passed（含基础设施故障不生成候选），前端 403 passed、
生产构建通过。正式 API 身份未变，低权限读取进程实际身份正确。
界面第一轮成功读取 `/w/0/rq5-policy-read-20261020/task.md` 并持久保留来源。

不能据此声称 RQ5 全链路通过：第二轮澄清改用了旧根目录 task.md，
产生错误路径草案，已停止审批，另记后续对话场景绑定 BUG。详见同日 REVIEW。
