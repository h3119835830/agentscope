# ADR：Pi 资料读取采用启动器预建的低权限私有通道

日期：2026-10-20。状态：采纳，发布与界面验收见同日 REVIEW。

## 决策

保留 API 的 agentscope-api 身份。仅在既有受信 root 启动器降低 API
身份之前，创建匿名 Unix socketpair，启动固定读取进程，身份为受控运行
合同规定的 happy UID、agentscope-task GID、无附加组。
API 通过继承的文件描述符使用它；没有监听端口、文件系统 socket、
新增 HTTP 接口、sudo 规则、setuid 程序或 capabilities 授权。

读取器仅调用固定的 reference_file_reader.py，不接受命令、解释器、
调用者指定身份或任意操作。API 仍先验证准确 Agent、登记资源、相对路径、
敏感类型、typed/DSL 拒绝规则；仍在读取后、生成后及应用前核对快照。
资料不是授权，Pi 不具有批准或加载接口。

## 为什么不改 API 身份

API 的实际 UID 999/GID 985 与资料读取要求 UID 1000/GID 986 不同。
删除身份检查、让 API 以 root 读文件、让 API 整体变成 Agent 用户，
都会混淆控制面与受控文件的权限边界，予以否决。
也不把正常资料读取接入特权 Broker，避免扩大其协议与重启影响面。

## 约束与取舍

- 启动器创建的匿名通道是控制面内部能力，不提供给 Pi 或 DSH。
- 握手报告实际 UID/GID/组；每次读取必须与原绑定一致。
- API 接收后清除描述符环境变量并设置 close-on-exec；子进程默认关闭 FD。
- 读取守护与实际读取进程均设置 no_new_privs、不可 dump、禁止 core dump。
- 旧 fd 锚定、O_NOFOLLOW、单硬链接、UTF-8、大小/数量/时间限制保留。
- API 最多接纳两个读取请求；单条通道串行，锁等待计入原期限。
- 通道超时/中断不可复用；读取失败不回退到 API 身份。
- API 退出关闭通道，读取进程结束。它不是 ActPlane 域，也不加入现有 Agent 域。
- 读取服务故障直接终止本次生成，不能伪装为文件政策拒绝或无资料生成成功。

不修改 ActPlane 源码、DSL、BPF、事件 ABI、运行时或预编译对象。
本决策不修复 RQ5 启动基线只读问题，也不新增运行时策略能力。
