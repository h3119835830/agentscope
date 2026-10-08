# REVIEW：工作区结构化记录界面

状态：修复及浏览器验收完成。

## 范围

仅修改 AgentScope 的 Agent 连接前端展示及纯数据投影。未修改后端、普通业务、DSH、Broker、策略审批或实际执行边界。当前模块去掉重复面包屑与可视大标题、顶部执行状态胶囊及连接状态标签，统一使用字段记录。

## 已验证

- 前端全部 130 项测试通过；关联、安全语句及回执边界专项包含五项新增测试。
- Vite 构建成功，独立输出后仅更新 18003 静态文件；API、DSH、Broker 不需要重启。
- 工作区关联读取真实注册表 session_ids，来源任务以 workspace_id 精确匹配；拒绝以同名、同路径或未知身份猜测关联。
- 保存的编译、加载、行为约定与当前生效分别表达。只读档案接口不转成实时保护结论。

## 浏览器验收

15 项检查通过，覆盖真实 RQ5 工作区的一条原生会话、两条来源任务，工作区搜索，刷新恢复，策略完整语句，12→24 游标分页，运行时空记录，任务切换后执行目录隔离，20 个文件按需读取与刷新，原有连接历史，关闭返回触发按钮，以及桌面、423px、320px 页面无整页横向溢出。

首次 320px 检查失败：document clientWidth=305、scrollWidth=320。原因是全局 body 固定 min-width:320px；去除此下限后列表和策略抽屉均为 clientWidth=scrollWidth=305。首次失败与复验结果保留在 browser-acceptance.json。423px 为 408/408，桌面无装饰性连接状态标签或重复顶部栏。窄屏记录表格在自身容器内滚动，所有字段仍可访问。

最终包：index-IxlFoFnC.js、index-DVPhj7iG.css；index SHA256 为 b49b9beecd262e6eda8faf4ca066ec07cfb328dbbc11a61dd3be88329808a3cb，与 18003 HTTP 返回字节一致。运行时实际静态目录为 /var/lib/agentscope-scope-demo/ui，已更新该目录并保留旧资产供既有页面使用。源码 frontend/dist 同步更新。API PID 1345616 未执行重启；本轮没有调用策略批准、装载或 Agent 任务执行。

证据在 REVIEW/evidence/workspace-record-ui-20261008，包含桌面、关联、策略及窄屏截图和 JSON 验收结果。本轮只验证前端记录呈现与只读关联，不作为新增内核 enforcement 的验收。
