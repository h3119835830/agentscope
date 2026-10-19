# RFC：Git 模板语义拆分与执行能力合同（2026-10-19）

状态：已实现；验收及发布证据见同日 REVIEW。变更仅限 AgentScope，不改 DSH、ActPlane 内核或 Broker。

## 拆分原则

按用户要约束的动作与事件关系组织模板；commit 与 push 独立，提交前检查与推送前检查独立。文件路径、程序名、代码范围只作为同一模板的参数，不按资源名复制模板。旧 RQ1-GIT / RQ1-CHECK 保留版本和已有配置；没有子配置时不在主表展示，助手和新建选择器不再提供旧模板。不自动迁移、停用或加载任何已有策略。

## 新模板与参数

| ID | 语义 | 参数 | 实际能力 |
|---|---|---|---|
| GIT-COMMIT / GIT-PUSH | 独立的提交/推送执行事件 | program、effect | 有限支持：参数 token 命中后 notify / kill |
| GIT-COMMIT-CHECK / GIT-PUSH-CHECK | 独立的提交/推送检查事件 | program、target、checker、exit_code、effect | 有限支持：after exec … exits N since write … |
| GIT-LOCAL | 本地历史与清理事件 | program、tokens(reset/clean/stash)、effect | 每个所选 token 独立生成规则；不支持子命令与选项组合 |
| GIT-BYPASS | 显式跳过检查参数 | program、tokens(--no-verify)、effect | 字面参数匹配；不将 -n 的不同语义混同 |
| GIT-CONTENT | 提交内容限制 | repository、forbidden_paths | 暂不支持，只保存参数草案 |
| GIT-PUSH-TARGET | 推送目标限制 | repository、remote、branches、forbidden_updates | 暂不支持，只保存参数草案 |
| GIT-PUSH-APPROVAL | 单次推送授权 | repository、commit、remote、branch、ttl_seconds | 暂不支持，只保存参数草案 |
| GIT-MERGE-GATE | 保护分支合并检查 | repository、branches、checks、issuer、reviewers | 暂不支持，只保存参数草案 |

## 服务端合同

模板新增受限 choices 与 integer 参数类型。choices 必须非空且属于服务端固定选项，不允许重复；integer 严格拒绝 bool、浮点和越界值。模板版本编辑也使用同一校验，不允许客户端修改 renderer、能力事实、参数类型、选项或语义。Git 参数匹配模板只允许 notify / kill，不能将其保存为事前 block。

受支持参数通过 materialize 写入真实 DSL，再沿用真实编译器、人工审批、单独应用、运行回执和停用审批链。检查模板明确写入退出码与代码写入失效条件，不再把“启动过程序”表达为“检查成功”。其条件作用于已观测执行链，不证明暂存区/待推送 SHA 与测试代码一致。

暂不支持的模板 materialize 结果 document=null，保存的只是需求参数。服务端 verify_current 由不可变模板版本检查执行能力；单项提交、批量提交、重新校验及审批版本核验都经过此检查。参数草案没有 DSL，不能创建可加载的候选。API view 返回 can_submit=false；助手收到同一能力元数据，若选择这些模板，结果包含能力缺口，生成时快照保留能力事实。历史模板仅在投影时附加当前说明，不改历史定义的哈希。

## 执行能力边界

ActPlane 当前从 exec 后的 tracepoint 观察 argv，扫描前 128 字节、最多 16 个参数槽；按字面 token 匹配，不识别子命令位置、别名、环境变量及全部 Git 配置。kill 是命中后终止，不能保证操作副作用尚未发生。相同 token 出现在其他参数位置也可能命中。

program 不是仓库选择器；target 是使检查失效的代码路径。当前没有仓库/分支/远端过滤、可信 CI 检查身份、暂存区或提交 SHA 快照、一次性行为授权及托管平台合并保护集成。共享进程内会话共享执行域与观察结果，不宣称会话隔离。全部 Agent 与指定 Agent 的作用范围沿用现有合同，路径不会成为新范围层。

## 界面

保留主表列、展开箭头、拖动列宽、子表独立横向滚动和行内审批/停用。模板详情保留版本化编辑及参数定义，新增紧凑的能力状态与可展开的已支持/暂不支持/执行边界。子配置使用真实参数控件，数值 0 不得被显示为空；不支持配置的状态、提示、DSL 页与页脚一致。Agent 页继续只有自动配置对话入口。
