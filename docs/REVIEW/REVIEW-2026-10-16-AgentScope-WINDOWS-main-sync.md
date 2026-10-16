# REVIEW：AgentScope WINDOWS/main 整理验收

日期：2026-10-16。结论：累计功能、架构文档及独立实验材料已整理并通过本地验收，可同步两个本地分支；远端推送等待用户明确授权。

## 整理依据

main/WINDOWS 均为 90af640，最新累计分支 cd32860 领先 67 个提交。三个旧脏工作树共 121 个文件的 blob 均已在累计分支历史中，全部原样保留。补充整理 223 个文档/公开证据/历史实验源文件，来源与 SHA256 见 [source-files.json](evidence/windows-main-sync-20261016/source-files.json)。重合文档仅同步已取代旧设计的修订和验收说明；没有替换较新的前端设计合同或产品代码。

## 当前验收

- 后端：1354 passed，0 skipped，0 failed；使用独立测试状态及 root 测试进程，读取子进程按测试身份降权。
- 前端与插件：362 passed；Vite 134 modules 构建通过。
- 独立真实 namespace/文件 CAS 沙箱：4 passed，合成目录，无正式策略应用。
- ActPlane C：42 passed；Rust workspace：145 passed，49 ignored，0 failed；ActPlane 与 DSL adapter release 构建通过。
- 补入历史工具的 Python/JavaScript 语法通过；文档相对链接闭包无缺失，完整 diff 无普通 Java 业务/运行数据库/凭证文件改动。

[验收回执](evidence/windows-main-sync-20261016/validation.json)、[后端日志](evidence/windows-main-sync-20261016/backend-tests.txt)、[前端日志](evidence/windows-main-sync-20261016/frontend-tests.txt)、[ActPlane 日志](evidence/windows-main-sync-20261016/actplane-tests.txt)。

## 首次失败及整改

干净工作树未编译 DSL adapter 导致 217 个后端 setup error；补齐编译后，非特权测试进程因无法证明无补充组的读取身份，出现 31 个拒绝/连带断言失败。最终按服务身份模型运行隔离测试通过，未降低应用校验。插件初次缺少 DSH/Pi peer dependencies，使用本机匹配版本的测试依赖后通过；桥接测试依赖缺失的 /tmp/atf，改为系统 tmpdir。非交互 sudo 无授权时，独立沙箱测试改由 WSL root 入口执行，并在测试内降权到专用身份，4 项通过。

## 运行与发布边界

Windows 浏览器实际打开总览，18003 页面、健康接口和三个主资源均 HTTP 200，资源哈希与当前整合构建相同。登记 Agent 为 3，运行/保护核验均为 0；本轮不以控制台可达声称 Agent 当前受保护。服务路径保持既有 API/Broker 发布目录，没有源目录切换、策略批准/应用或普通业务改动。

未运行的特权 Rust eBPF 用例保留 ignored，GitHub CI 尚未运行；这些不计作正式 Agent 新增内核验收。远端 push 未执行。
