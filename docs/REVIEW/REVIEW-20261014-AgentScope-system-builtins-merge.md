# 系统内置保护归入第一层系统策略

日期：2026-10-14。状态：源码、后端 43 项定向回归、前端 280 项回归、生产构建及隔离真实 DSH/浏览器验收通过；18003 发布进行中。

用户指出“第一层应是系统策略”。复现：安全面板后端将保护控制目录/执行凭据以及 immutable 启动规则投影成 scope=platform；domain_view 独立画 platform 节点，形成五层。它是本次读模型的错误归类，实际没有单独 platform 策略数据库、审批控制器或加载入口。

改动将内置记录归为 scope=system，控制目录记录标记 kind=system_builtin，不可变启动证据附加 system_builtin=true。系统过滤与计数包含这些只读记录，关系固定为 system→agent→workspace→session。删除独立 platform 标签和样式，现有权限/资产页面的描述统一称系统内置保护。

Broker/ActPlane 的隔离挂载、非特权身份、固定 no-publish 规则及原始 source_ref=platform.no-publish 保持。该名称只是兼容的执行证据引用，未生成第五个策略域。系统和 Agent 权威配置、审批与加载逻辑不改，内置保护不可配置或停用，用户规则仍走现有审批。

回归核验四层数量与面板记录一致、系统筛选包含内置/用户规则、内置规则在 system 和 agent 提交配置/停用均被拒绝、读取不产生运行变更、原始 immutable 记录未被改写、未知计数不变成零。构建通过。没有把归属纠正当作工作区/单会话独立执行能力完成。

本次独立运行验收使用隔离目录与 18189，不在已清空的正式实例中创建会话。首次隔离启动失败记录保留，失败原因和最终验收补记如下。

较长隔离目录导致 ActPlane watch 的 Unix socket 路径超过 SUN_LEN，首次运行失败。未改变 Agent 提示词或策略逻辑，缩短测试批次名为 b 后，新批次实际读取拒绝、另一 Agent 不受影响、审批不提前执行、停用恢复全部通过。两项系统内置保护均在真实 API 的配置/停用尝试中返回 409，运行身份和策略不变。

浏览器真实会话显示四个节点：system=2、agent=3、workspace/session=0 且局部独立应用仍标不支持。系统筛选只列两项内置保护，无配置或停用入口。证据：[核验摘要](evidence/session-security-20261014/system-builtins-acceptance.json)、[四层关系](evidence/session-security-20261014/system-layer-domains.jpg)、[系统筛选](evidence/session-security-20261014/system-layer-panel.jpg)。
