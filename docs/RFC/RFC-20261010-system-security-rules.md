# 用户配置的系统共享安全规则

更新：用户界面与 DSL 管理已由 [ActPlane DSL 与会话 RFC](RFC-20261010-actplane-dsl-sessions.md) 替代。本文的通用权限表仅保留为资源挂载与工具准入的底层兼容合同，不再作为 ActPlane 策略展示或编辑界面。

日期：2026-10-10。范围：18003 的受控 Agent 连接。取代 RFC-20261009-security-config-scopes 中系统页只读设计说明。

## 产品与作用范围

系统配置是用户添加、编辑、删除的共享规则，不再展示运行隔离、控制面访问、审批和心跳等功能设计说明。当前 Agent 配置单独保存此 instance_id 的规则；本连接所有工作区、会话、子进程共享最终策略，但文件限制只匹配对应资源内的准确目标。

系统规则作为共同限制，不提供 allow 授权。支持文件 read/write deny、原生 tool deny/confirm、IPv4 deny、行为约定，以及 model_only/disabled 网络上限。行为约定不构成强制执行声明。具体授权仍在当前 Agent 内配置，并受系统禁止约束。文件目标必须是已有受控资源内的规范主机绝对路径，不能使用 /w 别名；不匹配某连接资源的文件规则不会扩展其挂载权限。仅观测连接及未接管的原生入口不在强制执行范围。

## 数据与接口

system_security_policy 保存独立规则、hash、revision、ready/updating/blocked；instance_local_policies 保留各连接自己的规则。agent_instances.policy_json/hash 保存两层合并后的有效策略，沿用 Broker/原生 Hook/ActPlane 合同。新建受控连接及修改其资源时也必须合并系统限制。默认迁移为无新增共同限制，回填原实例策略为 local，不改变现有有效 hash。

控制 API：GET /api/security/system；POST /api/security/system/proposals（policy、base_hash、revision、request_key）；POST /api/security/system/proposals/{id}/confirm（proposal_hash）。沿用管理员/本机控制身份校验，Agent 凭据不能读写这些接口。

实例详情另给 local_policy/local_policy_records，编辑只提交本层配置。原生 Agent scope 仍返回有效策略，Agent 候选不能删除继承限制。实例提案记录系统 revision；系统更新使旧待确认提案失效。共享提案绑定全体受控目标的身份、资源、代次、原 hash、本层 hash、gate 及最终 hash，重试幂等键必须对应原候选；确认前目标变化必须重新提交。

## 确认与应用

所有系统变更均先预览，包括收紧。确认后：全局 phase=updating，受影响入口 gate=updating；拒绝新增工具租约，最多等待既有租约 8 秒；终止所有受影响旧执行器后才提交新共享版本和有效策略；仅重启变更前确实在线且通过独立观察核验的连接，原来停止/暂停的连接保持未运行。重建继续使用现有启动隔离、加载和核验流程。全部要求的重建核验完成后才设 ready/applied。

停止或加载失败置 blocked/failed，拒绝启动、登记、Agent 规则修改与工具租约，不显示 active。API 在 updating 中退出后，下次初始化置 blocked；恢复必须重新预览并确认，停止不确定执行器后收敛；恢复不自动复活已暂停连接。系统页按匹配目标统计实际 active 数量，不把单个连接 active 或数据库保存当作全系统生效。

18003 采用一个 Uvicorn 控制进程，生命周期 RLock 序列化系统及实例修改；SQLite BEGIN IMMEDIATE 排序工具准入与 gate 更新。当前合同不支持多个 API 写入进程或外部直接改表。Broker 不新增共享配置解释器，只接收已有格式的合并有效策略。

参见 [ADR](../ADR/ADR-20261010-system-security-rules.md)、[REVIEW](../REVIEW/REVIEW-20261010-system-security-rules.md)、[BUG](../BUG/BUG-20261010-system-security-rules.md)。
