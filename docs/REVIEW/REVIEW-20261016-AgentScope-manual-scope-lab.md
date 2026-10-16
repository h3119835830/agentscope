# REVIEW：四组合手工验收准备

2026-10-16。结论：准备检查通过，用户真实运行拦截与反馈验收尚未进行。

已检查 18003 API/Broker active，A/B 受控启动 verified 且进程/执行域独立；Windows HTTP 入口和真实浏览器原生 DSH 页面可访问；两边目录选择器通过编辑路径到达测试目录。4 项参数合同只读渲染通过，未保存配置、提审、批准或加载测试策略。宿主探针两边全允许，3 笔订单 340.00；不能将该宿主结果替代 DSH 受控域内执行。桌面与实际 Linux 文件哈希一致。

B 原有 /w/0/sales.csv 写保护保留；测试采用独立目录及只读操作。共提供 96 项待填写检查记录，初始全部未测试。会话关联和反馈送达须看实际回执，不能将模型口头拒绝、工具失败或缺少文件记为内核拦截。

[RFC](../RFC/RFC-20261016-AgentScope-manual-scope-lab.md)、[ADR](../ADR/ADR-20261016-AgentScope-manual-scope-lab.md)、[BUG](../BUG/BUG-20261016-AgentScope-manual-scope-lab.md)。[准备证据](evidence/manual-scope-lab-20261016/preparation.json)。
