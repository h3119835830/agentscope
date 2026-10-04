# REVIEW-20261004：外部 Agent 通信第一版验收

状态：通信层验收通过；完整第三层运行时 Pi/Delta 生效闭环尚未验收。

## 已验证

| 项目 | 结果 |
|---|---|
| 后端完整回归 | 139 passed；5 条现有 FastAPI/Starlette 弃用提示 |
| 前端构建 | Vite 6.4.3，34 modules，`index-CN3XXlie.js` / `index-CjhfJXtF.css` |
| 新增接口测试 | 跨任务、无审批权限、TTL、撤销、任务结束、旧运行、幂等冲突、过期快照、批准包 hash、旧 Scope 申请不能批准、RQ5 guard、消息游标/重放、回执不降级、敏感格式遮蔽 |
| HTTP 客户端 | 远程 HTTP 被拒绝；HTTPS 入口不带 URL 凭据；实际 302 不转发 Authorization |
| 真实通信 | GitHub 固定 `0456086db8263c98fa4fd3c760cf3136c797afde`，ActPlane 编译及受管 DSH，HTTP/DSH 两端 Scope/反馈/消息/确认/审核拒绝回传通过 |
| 真实首次修复验收 | 任务 `9cb6ce0e51bc42f1`，模型工具实际执行；进程退出码 0 |
| 界面与持续通信验收 | 任务 `69f3e1ec536e4576`，页面发出第二条消息，DSH 接收确认；接入弹窗创建、密码遮蔽、Escape 关闭、焦点恢复通过 |
| 窄屏与键盘 | 423px 视口页面宽 408px，无横向溢出；键盘在 Scope 与 Agent 接入间切换保留当前 Task ID |
| 历史策略库 | 每次真实实验完整 strategies 表指纹一致，原 721 条 RQ1 保留；未转换、审批或删除原记录 |
| 隔离 | 仅 AgentScope 独立分支、18002 数据库与私有 profile；18000/18001 检查为串行空闲后启动；无普通 ERP 业务改动 |

证据目录：`C:\Users\happy\Desktop\归纳梳理\技术文档\REVIEW\AgentScope-agent-bridge-20261004`。
原始通信验收 JSON 在 `/var/lib/agentscope-history-v1/report/agent-bridge-v1`，包含
成功与 previous 失败记录、执行绑定、协议 hash、消息/回执、退出状态及策略库指纹。
导出文档证据只包含非敏感控制记录，不包含令牌、凭据文件、模型私有推理或原始会话。
最终发布回执记录源码提交与最后一次真实验收对应的插件 hash。

## 边界与后续整改

1. HTTP 适配器是在本机回环 API 上真实运行；未连接 OpenHands 等另一产品，
   未部署远程 HTTPS 代理。任意外部 Agent 必须接上自己的 session handler。
2. DSH 消息是主动工具拉取；不保证即时打断/上下文推送，也不声称 handled
   证明 Agent 遵从。UI 和协议均明确自报与内核事实的区别。
3. 运行时 Pi、事件聚合、严格快照、每任务作业/apply 锁与独立效果确认仍按
   新运行时技术方案实施。第一版没有自动使用反馈生成或加载 DSL。
4. Scope 审核复用既有实现；新增桥接申请增加运行/hash 的批准前检查。旧
   restrict 返回 delta_applied 是既有提交回执，桥接层不把它升级为 probe
   确认。全面并发更新合同与生效状态机属于下一阶段，不能以通信验收替代。
5. 实验只审批基础启动策略，所有扩权申请都拒绝，没有新增内核策略允许/拒绝
   探针，不能声称运行时增量策略的安全效果已通过。

## 已复现问题闭环

BUG：两次真实 DSH 调用出现 scheduler prepare 未定义。只统一隔离 profile 的
CLI 和插件依赖实例；修复后的真实工具通信通过。失败记录保留，未改模型提示
以规避错误。详见同目录 BUG.md。
