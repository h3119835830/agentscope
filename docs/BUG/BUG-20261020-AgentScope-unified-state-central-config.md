# BUG：统一状态及集中配置验收闭环

日期：2026-10-20。本轮修复均在隔离源码/数据库验收，正式服务未切换。

| 问题 | 复现依据 | 修复与回归 |
| --- | --- | --- |
| 执行门、期望配置与加载混用 | open/paused 缺回执、过期或哈希错配；新期望版本令旧 active=false | `product_status` 严格匹配身份/哈希/TTL；product_status 与 session_loaded_policies 参数化测试 |
| 高级 DSL 页仍推断当前加载 | 记录表与详情使用旧 active/loaded，可能与统一加载视图口径冲突 | 改用服务端 configuration_status；当前加载在专门核验视图查看；DSL 详情及前端渲染回归 |
| 无导入 DSL 的有效启动包被误判 | 严格核验初稿要求非空 DSL hash，但现有启动合同明确允许 null | 保留显式 null 合同，强制非空 bundle hash 与完整身份；新增显式 null 通过、缺失字段拒绝测试 |
| 页面过期/失败残留绿色 | 时间越过 expires_at；API 失败/目标切换 | 共用降级组件，加载行清空；单测及浏览器 expired/failure 模式 |
| 同名未运行 Agent 无法区分 | 同类型、同名、无 PID；会话目录漏传 display_name | 服务端稳定短标识；会话侧栏沿用相同身份；浏览器双 Agent 截图 |
| 老编辑链接进入生成记录 | 旧 agentPolicyTab=policies 同时携带 section=generate | 显式归一 System/policies，保持实例与配置 ID；导航测试 |
| 参数-only 模板使标签目录读取异常 | 不支持模板保存的 document 为 null | 标签来源按空文档处理，不把 None==None 当作已应用；label_sources 回归 |
| 当前信息流误标历史 | 当前 generation，但期望配置不匹配令 legacy active=false | 改用 session.historical 和 generation；专用回归 |
| 配置范围请求可能乱序 | 原系统连接轮询间隔 7 秒，读超时 10 秒，可重叠 | 完成后再调度下一次，清理时不接纳旧响应；失败不保留可操作目标 |

## 验收中非产品缺陷

- 首次全后端测试 32 失败：31 项与测试进程带 sudo/docker 等附加组、严格文件读取身份拒绝有关；1 项旧测试仍用 active 推断已核验。保留生产身份检查，改用 `setpriv --reuid=1000 --regid=1000 --clear-groups` 执行测试；旧断言改用 product_status。
- 合成预览回执最初缺少 `effective_dsl`，旧会话只读接口返回 500；补齐预览夹具后恢复。不把合成夹具问题写成内核缺陷。
- 隔离环境一次连接目录请求暂不可用时，保存按“目标失效”拒绝；没有扩大到全部 Agent。连接恢复后，同一目标保存成功。

具体测试数、截图与交付边界见 REVIEW。
