# AgentScope 技术文档

整理日期：2026-10-07。分支：`技术文档`；仓库：`h3119835830/agentscope`。

本目录统一归档 AgentScope / ActPlane 的架构、决策、评审、问题闭环和原始规划。当前阅读顺序为：三层职责与 Scope 流程 → 受管 DSH 与隔离 → 工作区/逐句记录 → 本机入口与托管 → 未完成事项。按下表进入专题，不以文件日期单独判断有效合同。

## 当前职责和证据口径

外部 Agent / DSH 执行用户任务，AgentScope 负责观察、候选审核与治理，Pi 提出策略候选，可信 Broker / ActPlane 编译、加载和执行受支持规则。同域增量只追加限制；扩权重建完整策略包并更换执行域。

`compile`、`approved`、`loaded`、`active`、真实 OS 允许/拒绝、DSH 当前进程存活分别核验。历史测试通过不证明当前服务或任务仍有效；代码发布不等于重启部署，通信适配不等于通用运行时闭环。上述合同见对应 RFC，实际结果见 REVIEW 与 BUG。

## 专题索引

| 专题 | 架构合同 | 决策 | 评审验收 | 问题闭环 | 状态与范围 |
|---|---|---|---|---|---|
| ActPlane 研究环境 | [RFC](RFC/RFC-20260923-ActPlane本机eBPF研究环境.md) | [ADR](ADR/ADR-20260923-ActPlane采用WSL2与BPF-LSM启动配置.md) | [REVIEW](REVIEW/REVIEW-20260923-ActPlane本机研究环境验收.md) | 无独立记录 | 历史环境前置检查；未证明当时内核拦截 |
| 本机 Linux 部署 | [RFC](RFC/RFC-20261002-AgentScope本机Linux部署.md) | [ADR](ADR/ADR-20261002-AgentScope隔离安装决策.md) | [REVIEW](REVIEW/REVIEW-20261002-AgentScope安装验收.md) | [BUG](BUG/BUG-20261002-AgentScope本机运行兼容性.md) | 受管启动与 Scope 安装验收；按具体记录判断 |
| 历史策略库初版 | [RFC](RFC/RFC-20261002-AgentScope历史策略库.md) | [ADR](ADR/ADR-20261002-AgentScope历史策略库.md) | [REVIEW](REVIEW/REVIEW-20261002-AgentScope历史策略库.md) | [BUG](BUG/BUG-20261002-AgentScope历史策略库.md) | 历史实现及有限真实链路验收 |
| Pi 启动前策略 / RQ5 | [RFC](RFC/RFC-20261003-AgentScope-Pi启动前策略与RQ5扩展验收.md) | [ADR](ADR/ADR-20261003-AgentScope-Pi结构化候选与隔离RQ5验收.md) | [REVIEW](REVIEW/REVIEW-20261003-AgentScope-Pi第二层RQ5闭环验收.md) | [BUG](BUG/BUG-20261003-AgentScope-Pi候选提交与RQ5探针环境.md) | 链路与文件保护通过；语义场景安全评分未通过 |
| 策略输入与采集审计 | [RFC](RFC/RFC-20261004-AgentScope策略输入与采集审计.md) | [ADR](ADR/ADR-20261004-AgentScope策略输入与伪代码职责.md) | [REVIEW](REVIEW/REVIEW-20261004-AgentScope策略输入与审计验收.md) | [BUG](BUG/BUG-20261004-AgentScope转换输入与能力上下文缺口.md) | 后由第一版生成流水线更新 |
| 历史策略生成第一版 | [RFC](RFC/RFC-20261004-AgentScope历史策略库第一版.md) | [ADR](ADR/ADR-20261004-AgentScope历史策略库第一版.md) | [REVIEW](REVIEW/REVIEW-20261004-AgentScope历史策略库第一版.md) | [BUG](BUG/BUG-20261004-AgentScope历史策略库第一版.md) | 独立实例验收；保留后续拒绝状态 |
| 外部 Agent 通信 | [RFC](RFC/RFC-20261004-AgentScope外部Agent接入第一版.md) | [ADR](ADR/ADR-20261004-AgentScope外部Agent接入第一版.md) | [REVIEW](REVIEW/REVIEW-20261004-AgentScope外部Agent接入第一版.md) | [BUG](BUG/BUG-20261004-AgentScope外部Agent接入第一版.md) | 通信层验收；不代表通用运行时闭环 |
| 启动前工作台与原生 Pi 会话 | [RFC](RFC/RFC-20261004-AgentScope启动前工作台与Pi会话.md) | [ADR](ADR/ADR-20261004-AgentScope原生Pi会话与追加加载记录.md) | [REVIEW](REVIEW/REVIEW-20261004-AgentScope启动前工作台验收.md) | [BUG](BUG/BUG-20261004-AgentScope工作台会话接入与恢复闭环.md) | 专项验收；与 Scope Demo 区分 |
| 本机开发入口 | [RFC](RFC/RFC-20261004-AgentScope本地开发免口令.md) | [ADR](ADR/ADR-20261004-AgentScope开发控制台免口令.md) | [REVIEW](REVIEW/REVIEW-20261004-AgentScope开发页面展示验收.md) | [BUG](BUG/BUG-20261004-AgentScope开发入口与实验服务恢复.md) | 18000/18001 历史开关；18003 见删除登录 |
| 文件 Scope Demo | [RFC](RFC/RFC-20261005-AgentScope-DSH三阶段ScopeDemo.md) | [ADR](ADR/ADR-20261005-AgentScope-DSH三阶段ScopeDemo.md) | [REVIEW](REVIEW/REVIEW-20261005-AgentScope-DSH三阶段ScopeDemo.md) | [BUG](BUG/BUG-20261005-AgentScope-DSH三阶段ScopeDemo.md) | 登记场景验收；通用平台与公共 benchmark 未完成 |
| 受管 DSH / Pi / 审计隔离 | [RFC](RFC/RFC-20261006-Pi-受管DSH与审计闭环.md) | [ADR](ADR/ADR-20261006-Pi-受管DSH与审计闭环.md) | [REVIEW](REVIEW/REVIEW-20261006-Pi-受管DSH与审计闭环.md) | [BUG](BUG/BUG-20261006-Pi-受管DSH与审计闭环.md) | 安全专项通过；完整支付任务未通过 |
| 工作区绑定与策略记录 | [RFC](RFC/RFC-20261006-DSH工作区绑定与策略记录.md) | [ADR](ADR/ADR-20261006-DSH工作区绑定与策略记录.md) | [REVIEW](REVIEW/REVIEW-20261006-DSH工作区绑定与策略记录.md) | [BUG](BUG/BUG-20261006-DSH工作区绑定与策略记录.md) | 界面与绑定专项验收 |
| 逐句 DSL 与控制台 | [RFC](RFC/RFC-20261006-逐句DSL与控制台锁定.md) | [ADR](ADR/ADR-20261006-逐句DSL与控制台锁定.md) | [REVIEW](REVIEW/REVIEW-20261006-逐句DSL与控制台锁定.md) | [BUG](BUG/BUG-20261006-逐句DSL与控制台锁定.md) | 逐句展示与会话专项验收 |
| DSL 归一化与重叠分析 | [RFC](RFC/RFC-20261007-DSL规则归一化与重叠校验.md) | [ADR](ADR/ADR-20261007-DSL规则归一化与重叠校验.md) | [REVIEW](REVIEW/REVIEW-20261007-DSL规则归一化与重叠校验.md) | [BUG](BUG/BUG-20261007-DSL规则归一化与重叠校验.md) | 实施中；完整六会话验收未通过；默认 observe |
| Scope Demo 服务托管 | [RFC](RFC/RFC-20261007-ScopeDemo服务托管与恢复.md) | [ADR](ADR/ADR-20261007-ScopeDemo服务托管与恢复.md) | [REVIEW](REVIEW/REVIEW-20261007-ScopeDemo服务托管与恢复.md) | [BUG](BUG/BUG-20261007-ScopeDemo服务托管与恢复.md) | 历史现场恢复与异常恢复通过 |
| 本机浏览器自动会话 | [RFC](RFC/RFC-20261007-AgentScope本机浏览器自动连接.md) | [ADR](ADR/ADR-20261007-AgentScope本机自用自动会话.md) | [REVIEW](REVIEW/REVIEW-20261007-AgentScope本机免口令验收.md) | [BUG](BUG/BUG-20261007-AgentScope普通地址反复要求口令.md) | 已废弃；删除登录合同取代 |
| Scope Demo 删除登录 | [RFC](RFC/RFC-20261007-AgentScopeDemo删除登录.md) | [ADR](ADR/ADR-20261007-AgentScopeDemo删除登录.md) | [REVIEW](REVIEW/REVIEW-20261007-AgentScopeDemo删除登录.md) | [BUG](BUG/BUG-20261007-AgentScopeDemo删除登录.md) | 入口专项验收；不代表恢复历史任务 |
| WINDOWS 发布阶段 | [RFC](RFC/RFC-20261007-AgentScope-WINDOWS发布范围.md) | [ADR](ADR/ADR-20261007-AgentScope-WINDOWS发布范围.md) | [REVIEW](REVIEW/REVIEW-20261007-AgentScope-WINDOWS发布范围.md) | [BUG](BUG/BUG-20261007-AgentScope-WINDOWS发布范围.md) | 历史发布范围；被后续 main 阶段更新 |
| 本机新版发布 main | [RFC](RFC/RFC-20261007-AgentScope本机新版合入main.md) | [ADR](ADR/ADR-20261007-AgentScope本机新版合入main.md) | [REVIEW](REVIEW/REVIEW-20261007-AgentScope本机新版合入main.md) | [BUG](BUG/BUG-20261007-AgentScope本机新版合入main.md) | 固定源码发布验收；保留运行时和归一化未闭环项 |

## 当前未完成事项

- DSL 归一化的六会话最终验收及完整页面回归尚未通过，默认仍为 observe；误拦截、漏拦截、反馈关联及进程域清退按该模块 REVIEW/BUG 记录，不能宣布功能完成。
- 受管 DSH 的安全专项结果不等于完整支付任务修复通过；RQ5 固定场景、素材预览和公开 benchmark 复现分别统计。
- 浏览器自动会话及票据方案已废弃；18003 当前入口采用删除登录方案。18000/18001 的历史开发开关不据此改写成相同部署状态。

## 规划、研究和发布记录

- [四份原始技术规划](plans/README.md)：保留目标接口、目标 VM 环境与当时设计，不作为已实现证明。
- [工作台设计](REVIEW/DESIGN-20261005-AgentScope任务工作台.md)、[数据集与验收范围](REVIEW/BENCHMARKS-20261005-AgentScope数据集选择与真实验收.md)、[ActPlane 论文与 Pi 职责复核](REVIEW/REVIEW-20261006-ActPlane论文与Pi运行时职责.md)。
- [2026-10-04 提交准备](REVIEW/REVIEW-20261004-AgentScopeGitHub提交准备.md)、[分支推送回执说明](REVIEW/REVIEW-20261004-AgentScope分支推送验收.md)、[GitHub 发布](REVIEW/REVIEW-20261004-AgentScope-GitHub发布.md)。这些记录中的授权和“未推送”等文字只对应各次操作。
- [Linux 安装说明](install-linux.md)、[历史独立验收材料](acceptance/)、[公开 Scope/DSH 证据](REVIEW/Pi-DSH-验收证据-20261006/)。原始会话、数据库、凭据和未筛选日志只在本机保留。
- [本次整理验收](REVIEW/REVIEW-20261007-AgentScope技术文档整理验收.md)、[来源与哈希清单](catalog.json)、[文档检查结果](documentation-check.json)。

## 维护方式与本次快照

RFC 记录总体架构、职责和接口；ADR 记录采纳/废弃的决策；REVIEW 区分实测结果、风险与待办；BUG 只记录已复现问题及修复验收。没有独立 BUG 的研究环境不编造问题闭环。更新安全边界、运行时或跨服务接口时同步对应记录。

本分支从远端 main 的 `c045784` 建立，只整理文档与所引用的公开证据，不修改普通业务或 AgentScope 实现，不切换开发工作树、不重启服务。文档还收录本机后续验收记录；其中本地 main 合并记录不表示已经推到远端。本次源文件副本保留原处。

同一专题正文集中在 RFC/ADR/REVIEW/BUG 分类目录；旧模块路径保留为跳转入口。不同版本、不同实例、方案和验收各自保留，不因内容相似合并测试结果。新增证据限于已引用的公开检查、合成任务结果及截图；仅本机保存的材料明确标注，不留下无法打开的本地超链接。来源优先采用集中技术记录；Scope Demo 采用源码工作树中已更新删除登录说明的版本，差异和哈希见清单。
