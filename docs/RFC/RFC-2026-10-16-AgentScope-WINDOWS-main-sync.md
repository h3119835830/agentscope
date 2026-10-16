# RFC：AgentScope WINDOWS/main 同步范围

日期：2026-10-16。范围：本地源码整合与可复现验收；远端推送等待用户单独明确授权。

## 源码和运行版本

以当前 18003 发布对应的累计源码 `cd32860` 为基线，保留其领先 main/WINDOWS 的 67 个历史提交，补入未进入应用分支的架构修订、RQ5 诊断和独立实验材料。原工作树 121 个未提交文件的 blob 均已出现在该基线历史中，保留原文件和工作树，不用旧副本覆盖新源码。

本轮新改动为 CI、一个桥接测试的临时目录及文档/历史实验工具；应用运行代码保持已验收基线。两个目标分支采用同一完整提交，禁止强制覆盖远端历史。记录本地提交、远端推送和运行发布为三个独立事实。

## 当前架构合同

[Agent 基线与真实域运行时规则](RFC-20261014-AgentScope-agent-baseline-runtime-policy.md) 和 [执行绑定修订](RFC-20261014-AgentScope-execution-binding-rederivation.md) 是当前设计依据；旧四层材料保留历史与取代说明，不表示固定工作区/会话域已经交付。策略助手只能提出候选，人工批准与显式应用分开，实际保护必须检查当前执行绑定和操作证据。

## 验收及隔离

CI 先编译 ActPlane 和 DSL adapter，再运行隔离数据库/无正式 Broker 的后端测试；文件读取安全测试需要实际验证身份降权，不能删掉生产权限校验来迁就测试。前端 regression 纳入 CI，桥接测试使用系统临时目录。独立沙箱测试使用合成目录和测试身份。

18003 页面、health 和主资源均 HTTP 200，资源字节与整合构建一致；页面当前显示三个登记 Agent 均未运行，不能把控制台在线称为 Agent 已受保护。本轮没有应用策略或切换运行源码。

关联：[ADR](../ADR/ADR-2026-10-16-AgentScope-WINDOWS-main-sync.md)、[REVIEW](../REVIEW/REVIEW-2026-10-16-AgentScope-WINDOWS-main-sync.md)、[BUG](../BUG/BUG-2026-10-16-AgentScope-WINDOWS-main-sync.md)。
