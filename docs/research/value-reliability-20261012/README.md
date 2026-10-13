# ActPlane 价值实证与 AgentScope 可靠性交付索引

日期：2026-10-12。正式实现及短时验收已交付，24 小时观察待完成。总览入口：http://localhost:18003/ 。本目录不存真实凭证、数据库备份或模型私有推理。

## 阅读与复核顺序

1. [对外公告成稿](announcement.md)：已按导师与外部读者改写，并接入本地产品阅读页 `/value-announcement.html`，未向外部渠道发送。
2. [论文、固定源码及比较依据](sources-and-comparison.md)：分别锁定论文版本、源码提交和部署二进制，承认既有 OS/信息流研究。
3. [十二类场景、攻击配方与路线](scenario-matrix-and-roadmap.md)：任务、攻击者、现有防护、机制、未覆盖路径和验收条件。
4. 六项核心确定性实验：[凭证](experiment-plugin.md)、[验收完整性](experiment-integrity.md)、[路径变体](experiment-path.md)、[派生来源新连接](experiment-flow.md)、[后台后代](experiment-descendants.md)、[资源对象隔离](experiment-isolation.md)。72 次四组执行对照不是提示注入成功率评测。
5. [真实 DSH 任务与平台边界](native-tasks-and-boundaries.md)：真实工具输出、后续合法任务、挂载/网络隔离效果与不能推导的能力。
6. [正式评审与部署结果](../../REVIEW/REVIEW-20261012-execution-independence-and-value.md)、[RFC](../../RFC/RFC-20261012-execution-independence-value-evidence.md)、[ADR](../../ADR/ADR-20261012-broker-liveness-and-measured-claims.md)、[BUG](../../BUG/BUG-20261012-console-liveness-and-overview-timeout.md)。

## 原始证据与复现入口

证据目录：`../../REVIEW/evidence/value-reliability-20261012/`，保留成功、失败和中间性能结果。`scenarios-final.json` 为 72 次报告；`execution-independence-final.json` 为控制台离线/watch/Broker 故障；`native-tasks-final.json` 为可观察 DSH 工具及公开回答；`revocation-final.json` 为真实双实例平台换代撤权。deployment-result、deployment-performance-result 分别对应首次更新和 API 性能更新；deployment-startup-first-failure 保留补充脚本的 systemd 依赖错误及恢复，deployment-startup-final 为最终 Broker 启动顺序修复及 API 重启回归。最终软件回归在 backend-tests-final.txt、frontend-tests.txt；最终 22:57:30 观察启动快照在 observation-start.json，旧窗口单独保留。

复现实验需可信 Linux/eBPF、root 与独立隔离前缀。脚本位于仓库 scripts：value_acceptance_service.py、accept_execution_independence.py、accept_value_scenarios.py、accept_value_dsh.py、accept_value_revocation.py。实验脚本只能操作其专用 18163 服务、合成目录及独立 BPF pin 根；正式部署脚本另有运行基线与目标冻结检查，不能把隔离脚本直接改端口用于正式服务。

原报告网页已按用户要求从前台移除，`/value-evidence.html` 现与 `/value-announcement.html` 显示同一篇公告。[旧报告 HTML](experiment-report.html) 原样归档为技术附件，build_value_evidence.py 后续仅在技术附件目录生成 HTML，不覆盖公告。原始报告和二进制哈希继续保留。已有本机验证标签仍需完整证据，缺失时降级为待验证。源码与产品 UI 不包含示意 PID/trace 冒充真实结果。

24 小时后续脚本 observe_value_stability.py 只核验、记账和报告；不自动重启、不恢复旧授权。2026-10-13 已按用户要求取消“AgentScope 24 小时稳定性验收”自动跟进，没有因此将稳定性项标为通过。

归档的文本日志仅清理了行尾空白；实验 JSON 内容未作结果修饰，页面中的原始报告哈希可直接校验。

2026-10-13 阅读入口更新：[安全总览与公告阅读说明](../value-guide-20261013/README.md)。安全总览恢复工具/系统行为图解，全文公告已接入 `/value-announcement.html`。本次仅静态发布，原稳定性观察窗口和实验结论保持。

随后已按用户要求[恢复原安全总览](../security-overview-restore-20261013/README.md)；当前仅将[公告改为外部阅读版本](../public-announcement-20261013/README.md)，具体说明应用日志遗漏的行为及内核执行可审计、可反馈、可监控的价值。
