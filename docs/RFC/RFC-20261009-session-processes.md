# Agent 配置中的会话与执行进程

日期：2026-10-09。范围：18003 Agent连接及隔离的原生会话元数据集成。

## 用户流程

删除“实例与进程”按钮、二级实例弹层及其专用样式。配置里的“会话与进程”仅保留一张表：会话名称、完整会话 ID、状态、对应执行进程 PID。移除该页资源映射表、新建会话控件与全实例进程表。其他配置页与控制接口保留。

同一 PID 对应多个会话时标记“共享进程”。仅保存、没有 process_ids 的会话显示“未运行”，禁止填入实例 PID 伪造一会话一进程。未命名会话显示“未命名会话”。不连接的 Agent 显示无法读取当前会话进程。

移除二级弹层后，主表保留每个受控连接的配置入口；只有无受控连接的同类产品才选取首选观测入口，避免多个受控实例被折叠而无法访问。

## 数据合同

GET /api/agent-instances/{id}/sessions 原有 sessions、process_ids、resource、mapping 和状态语义保持不变。DSH 增补 name、updated_at 和 names_available；只对原结果已有会话 ID 且工作目录一致的条目关联名称。名称读取失败不丢弃基础会话记录，不恢复或启动会话，不修改进程归属。

DSH 名称来自原生只读 session/list：服务端向 Broker 取得当前受控实例入口，在内存中完成原生 cookie 交换，调用固定 /api/session/list，随后只提取名称、工作目录和更新时间；不将认证地址、cookie、完整 projection、消息或模型私有推理返回给浏览器或写入证据。仅接受 http://127.0.0.1 的根入口，拒绝跳转到其他地址。缓存 5 秒，按实例、generation、PID 隔离，最多 64 项。

隔离的 Hermes 原生插件补充数据库会话 title，运行会话使用同一存储 ID 合并原生网关的待保存名称、状态与 PID；不改 Hermes 主项目或普通 ERP 业务代码。

前端只查询 sessions，不再为此页额外查询全部 processes。保留 5 秒刷新及手动刷新，异步失败清除当前进程列表并提供重试，不将过期进程显示为当前。

参见 [ADR](../ADR/ADR-20261009-session-processes.md)、[REVIEW](../REVIEW/REVIEW-20261009-session-processes.md)、[BUG](../BUG/BUG-20261009-session-processes.md)。

## 2026-10-10：会话工作区与连接界面简化

DSH 的“会话与进程”增加工作区列，展示目录名与完整路径。直接读取 GET /api/agent-instances/{id}/sessions 中逐会话 resource，不使用实例资源清单、进程 cwd、会话名称或默认目录推断归属；Broker 已将原生 workspaceRegistry 的隔离执行路径翻译为对应主机资源目录。execution_resource（例如 /w/0）仍保留接口原语义，不作为主路径展示。已保存会话同样保留其真实工作区，不因此显示执行 PID；缺失目录显示“未提供”。

Hermes 不展示项目工作区列；其运行资源目录不自动解释为 coding Agent 项目工作区。其他 Agent 若返回逐会话工作区目录，也可显示该列；没有目录数据则隐藏。DSH 自身支持工作区，因此加载中或暂未读取到目录时仍保留列头。

Agent连接及旧工作区关联界面移除连接历史页签、历史内容与任务技术详情中的连接历史跳转。旧 connectionsPane/connectionHistory URL 退回当前连接并在导航时清理；任务历史、运行记录及既有 append-only 审计存储/只读接口保留。本轮只修改前端，未改变会话、权限、执行或历史数据接口。

见 [本轮验收](../REVIEW/REVIEW-20261010-session-workspaces.md)。
