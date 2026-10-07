# BUG：Pi 启动策略精确目标超出路径 ABI，结束错误掩盖业务诊断

状态：已复现、已修复部署、已完成真实同源新任务生成复验。原失败任务保留；人工审核与 DSH 执行尚未进行。详细评审见 [REVIEW](../REVIEW/REVIEW-20261008-pi-bootstrap-path-limit.md)。

## 现象与影响

任务 `0dae79b573f14bca` 的启动作业 `d5cb5fcc741848589eff12f2be82404c` 失败，界面暂停原因是 `ValueError: Pi settled without a server-validated submission`，没有保存可提交候选。错误本身只说明工作流没有服务器验证的提交，不能说明模型服务商故障。

影响范围是启动策略生成：该任务尚未生成有效策略版本、尚未建立 DSH 会话、没有执行凭据或策略加载。保护校验按预期拒绝了不可表示的目标，没有静默截断路径、扩大权限或启动执行。

## 已保存回执中的复现链路

1. 来源快照保留 `workspace/transaction-verification-service` 的嵌套路径。Pi 获得任务、能力、历史检索和来源材料。
2. 首次校验缺一个引用来源的读取回执；Pi 补读成功。这一步不是最终根因，未消耗语义草案修复预算。
3. 随后 3 次校验均被 `IR pattern 超过 64 UTF-8 bytes 或包含控制字符` 拒绝。6 个实际目标的长度如下，均为精确文件路径而非模型服务商错误：

| 项目内目标（含旧执行路径完整前缀后的字节数） | UTF-8 字节 |
| --- | ---: |
| `run_tests.py` | 77 |
| `tests/__init__.py` | 82 |
| `config/config.json` | 83 |
| `config/config.toml` | 83 |
| `tests/test_validator.py` | 88 |
| `tests/tests_rate_limiter.py` | 92 |

完整前缀为 `/s/0dae79b573f14bca/r/workspace/transaction-verification-service/`，完整目标见 [公开诊断回执](../REVIEW/evidence/task-replay-records-20261008/pi-bootstrap-diagnostic.public.json)。

4. 有效校验预算耗尽后，后续校验返回 429；RPC 仍进行了两次续接。状态中最后工具被记录为 `rpc_lifecycle`，只显示提交缺失和一般工具剩余数，未传播真实业务诊断及剩余校验次数。
5. 最终报出通用 settled 错误，掩盖了“精确目标超出执行引擎 ABI”的可行动根因。Pi 已实际完成了缺失证据的补读，不应通过任务特制提示词或模型能力评价来解释此故障。

## 修复

- 在新任务固定上下文前，对可识别的独立项目根采用确实缩短 UTF-8 前缀的无冲突别名。本例 `workspace/transaction-verification-service → p0`；所有来源字节、项目内结构和原始路径证据保留，旧任务上下文不改写。
- 将 64 字节 pattern 限制作为共享常量公开到能力合同；超限时返回结构化 `engine_pattern_limit_exceeded` 诊断，包含精确目标和字节数。执行引擎、服务器校验与拒绝字符限制保持有效。
- RPC 状态排除生命周期记录的覆盖，保留最后业务工具和校验错误。无已验证候选且校验预算耗尽才终止；已验证候选仍允许精确哈希提交。不得自动批准或绕过加载核验。

## 验收闭环与保留事项

真实同源新任务 `ad7c53a17c334c7b`、job `948e76e023fe480aa959a62a8d556eb1` 已 completed，候选 `8ed88d1cd02a4163805b0848ea794afe` 为 validated：2 个执行规则 atom、7 项指导。首次缺两个实际读取回执后自行补读，第二次 valid=true、compiled，并成功提交服务器验证的精确候选；测试目标缩为 42/48/52 字节。

2026-10-08 独立只读复核：两任务来源 manifest 一致、20 个来源资产哈希相同、实际冻结文件哈希均一致；原失败 context JSON SHA256 未变。新任务仍为 policy_review / waiting_confirmation，有效版本 0、policy_versions=0、session=null、执行凭据=0；Pi 临时凭据已撤销。当前 API 仍使用修复源码，未发现部署回退。证据：[真实复验](../REVIEW/evidence/task-replay-records-20261008/pi-retry.public.json)、[最终只读核对](../REVIEW/evidence/task-replay-records-20261008/pi-bootstrap-final-readonly.public.json)、[待确认实屏](../REVIEW/evidence/task-replay-records-20261008/desktop-pi-review.jpg)。

相关专项 109 passed，完整后端 563 passed / 52 skipped。完整回归曾发现测试 fixture 隐式采用 `/var/tmp`，使本应成功的目标长 66 字节；成功测试已显式使用可写短目录 `/tmp/a` 并断言符合 ABI，没有放宽生产校验或修改系统临时目录权限。

旧 `0dae` 作业仍是 failed 历史记录，任务固定上下文没有自动修复；不得把旧记录改成成功，或用旧任务重试冒充本次同源新任务验收。仍不可表示的长叶名等继续受 64 字节限制。当前完成的是生成、编译和待人工确认候选的闭环，不能声称已批准、已加载、已执行 DSH、已完成项目业务测试或本轮内核拦截验收。
