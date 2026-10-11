# 系统策略配置 UI 预览

日期：2026-10-11。实现范围：独立 HTML/CSS/JavaScript 交互预览，不是正在运行的 18003 控制台发布包。

启动：

```sh
python3 -m http.server 18141 --bind 127.0.0.1 --directory docs/prototype/system-policy-studio
```

打开 http://127.0.0.1:18141/ 。支持配置、动作切换、路径匹配对照、实时 DSL、保存、勾选、统一载入预览、多规则 DSL 原文导入。配置仅保存在该预览 origin 的 localStorage。确认载入按钮不调用加载接口。导航链接可返回 18003。

## 确认的产品层级

系统策略库 → 配置与保存 → 勾选 → 预览影响与人工确认 → 所有受控 Agent 根层。

Agent 策略位于下一层，继承系统约束并添加专属策略。系统页面没有选择部分 Agent 的入口。取消勾选仅改变本次清单，不隐式删除已经生效的规则。

## 候选库

候选不是默认启用策略；所有条目初始均未配置。执行、网络和跨事件规则需要按业务评估。

| 候选 | 保护对象或行为 | 依据及适用边界 |
| --- | --- | --- |
| 环境凭据文件 | 所有以 `.env` 结尾的文件 | RQ1 秘密配置约束提炼；不包含 `.env.local` |
| SSH 私钥 | 常见私钥路径后缀 | 平台扩展；不是 RQ1 原文逐字转换 |
| 云服务凭据 | AWS/Kubernetes 凭据文件 | 平台扩展；按实际凭据格式增补 |
| 系统身份与授权文件 | `/etc/passwd`、`shadow`、`sudoers` 写入与删除 | Linux 平台边界；不把它宣称为所有系统文件保护 |
| 安全策略文件 | 用户填写的真实策略目录 | 平台设计；空目录不能保存 |
| 审计记录 | 用户填写的真实审计目录 | 平台设计；保护写入与删除 |
| 提权程序 | `sudo`、`su` | 最小权限设计；不等同于消除所有提权途径 |
| 网络连接审计 | IPv4 连接 | ActPlane connect/notify；不是完整流量审计 |
| 程序执行审计 | Agent 派生的程序执行 | ActPlane exec/notify；关注事件量 |
| 安全约定文件 | `AGENTS.md` 写入与删除 | RQ1 契约文件约束提炼；允许 Agent 维护约定时不选 |
| 敏感信息外发 | 敏感文件标签传播后的网络连接 | ActPlane 信息流；会影响后续模型请求，需评估 |
| 网络输入后的执行 | 网络来源标签与后续指定程序执行 | RQ1 远程脚本约束启发；不是精确管道识别 |

测试前置、项目写入目录、指定生成器的文件维护流程等依赖项目上下文，留在 Agent / 项目层配置。

## 事实与边界

- `model.mjs` 生成规则片段，不伪造实际 Agent 启动身份；集成时由可信加载流程合成 AGENT source。
- `**/*.env` 在当前 ActPlane 编译器降低为字面后缀 `.env`；`**/.env` 仅匹配同名文件。不要用 `*.env` 替代，当前 lowerer 对其语义不同。
- 编译器支持不等于当前固定受控引擎支持。当前 adapter 检查会拒绝路径后缀能力；界面允许保存并明确阻止载入。
- `runtime.json` 是带采集时间的只读受控 Agent 状态快照，用于影响预览；不包含凭据。实际集成必须实时重新读取，不能将快照作为加载授权。
- 导入只保留原文草案，不把简单 rule 声明检查称为编译。未经过服务端真实编译的文档不可选择载入。
- 预览不提供真实应用、部署、内核命中或反馈送达证明。

## 验证

```sh
node --test docs/prototype/system-policy-studio/model.test.mjs
node docs/prototype/system-policy-studio/verify-compiler.mjs
```

第二条调用 `/opt/agentscope/actplane/target/release/actplane compile`，36 组只读编译，不调用 attach/load/Broker。编译夹具中的 Node 来源只用于静态语义核验，不代表真实运行身份。

相关文档：`docs/RFC/RFC-20261011-system-policy-studio.md`、对应 ADR/REVIEW/BUG。证据在 `docs/REVIEW/evidence/system-policy-ui-20261011/`。
