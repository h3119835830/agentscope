# 论文、源码和既有研究索引

审阅日期：2026-10-12。直接审阅主论文、固定版本源码及本机二进制，不将论文结果计入本轮实测。

| 工作 | 固定依据 | 能力与本轮比较边界 |
|---|---|---|
| ActPlane | [v2](https://arxiv.org/html/2606.25189v2)；[源码 404542899a2153af0952cbf0dc52aeab0b7c5034](https://github.com/eunomia-bpf/ActPlane/tree/404542899a2153af0952cbf0dc52aeab0b7c5034)；artifact 63db86945c9b8618a46aa68c8de214bc4b8343d9 | 将任务政策具体化为 DSL，在 OS 处约束系统操作，关联来源和事件，并提供语义反馈。不是已有 Linux 隔离技术的替代品。 |
| CaMeL | [v1](https://arxiv.org/html/2503.18813v1)；源码 f083b6b396399d3b3c7f2ddaf613a5945eaf32d8 | 分离可信计划与不可信数据，能力和数据流约束避免注入改变控制。需要相应解释器及标签管理；本轮未部署，不对其作胜率比较。 |
| Progent | [v3](https://arxiv.org/html/2504.11703v3)；源码 5be7b63fa96f70bc19b72fbcee81f1c0bcc1a565 | 工具及参数上的确定性权限规则，符号检查与权限收紧，扩权需要确认。不能将其等同于只检查工具名的弱对照。 |
| FIDES | [v2](https://arxiv.org/html/2505.23643v2)；源码 669c046c4adbc56ee49c9672fdd30c54937ea062 | 保密性与完整性标签、规划上下文及工具执行约束；信任 agent 配置。与 ActPlane 的重合是来源及信任边界管理，区别需结合实际执行接口判断。 |
| BPFContain | [2021 论文](https://arxiv.org/abs/2102.06972) | eBPF 容器约束已有先例，因此“首次把策略放进内核”不成立。 |
| Landlock | [Linux 官方文档](https://www.kernel.org/doc/html/latest/userspace-api/landlock.html) | 非特权进程可施加并继承访问限制。支持范围随内核 ABI 变化；不能用最新文档假定当前 WSL 全部支持。 |
| AgentDojo | [论文](https://arxiv.org/abs/2406.13352)；[正式发表](https://proceedings.nips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html) | 状态化工具与不可信内容注入提供攻击链设计依据。本轮未跑其完整评测。 |
| InjecAgent | [ACL 论文](https://aclanthology.org/2024.findings-acl.624/) | 外部工具内容诱导直接伤害和外泄；支持攻击者能力分类，不是本轮数字来源。 |
| OpenAgentSafety | [源码](https://github.com/Open-Agent-Safety/OpenAgentSafety)；[论文](https://arxiv.org/abs/2507.06134) | 多轮真实环境危险行为研究；既有 RQ5 冻结样例不能当业务正确性 oracle。 |
| OS-Harm | [源码](https://github.com/tml-epfl/os-harm)；[论文](https://arxiv.org/abs/2506.14866) | 用户滥用、注入及错误行为类别，用于负面案例分类，不是防护系统。 |

本机：Linux 6.6.114.1-microsoft-standard-WSL2；引擎二进制 SHA-256 `5e8d43c279d88bd4215f654746675debfd976e28426c9fabdabeca408865d6da`。本地 vendor 基线 `4c36aa54da2daf2b64de8782a38f77d5b76ec75a`，存在 AgentScope 已有集成差异，因此不能称本轮完全运行上游固定提交。主仓整合基线 `db870f6c2e3e42f4d921ea44b5c5c3e48136510e`。具体策略、命令、钩子配置和环境随每条原始记录保存。

本地源码核验的钩子包括 `actplane/bpf/process.bpf.c` 的 file_open、file_permission、mmap_file、path_rename 和 socket_connect；源码另有 sendmsg 相关路径，但本轮没有证明已有连接与各种 IPC 的完整覆盖。不能因没有做 send 实验就声称源码没有 send 支持，也不能因存在钩子就声称所有路径已保护。

既有讨论借鉴：技术文档 `research/20261012-four-layer-policy/source-lock.json` 与配套审计。该资料区分源代码、编译、加载、实际 OS 效果，指出 13 个说明不等于 13 个独立夹具；重命名为测试或 git 的可执行文件不能证明真实测试成功或真实提交。本文延续此证据标准，未复制其示例数字作为新实证。

结论：本轮证据支持更细地连接任务授权、真实执行对象和跨事件来源，并在控制面离线时维护已批准边界。不能支持“以前所有安全都做不到”“消除全部提示注入”“首次内核安全”或完整替代业务权限系统。
