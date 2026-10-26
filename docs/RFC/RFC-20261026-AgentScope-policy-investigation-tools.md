# RFC：策略生成 Agent 的调查与匹配验证工具

日期：2026-10-26。状态：实现与隔离验收通过；未部署到正式服务，不加载策略。

## 目标与边界
保留一套已发布模板和同一人工填参合同。模型自主调查已登记项目、调用 draft 工具、获得实际匹配反馈并修正候选；不接受模型自由 DSL、shell、审批或加载。原失败数据 acceptance/public-scene-baseline-20261025-v2 保持不可变，不手工修正模型结果。

## 接口
- search_project(workspace_id, query, mode, path, cursor)：模式为文件名或字面正文；经原有 reader UID、路径与现有策略检查。递归元数据限额、分批正文、累计预算和截断均明确返回。
- inspect_resource(workspace_id, paths)：返回可见对象类型、执行映射、有限目录样本及字面/递归语义。未见对象使用 unknown，不伪造存在性或把无权限当不存在。
- preview_policy_matches(configuration, workspace_id, checks)：仅接受本轮 draft 工具产物；服务端按冻结模板实例化，用实际编译器编译，并调用与编译器相配的 ActPlane taint.h 纯匹配函数。checks 包含动作、对象、object/tree、target/invalidation/source、预期匹配值。不得只用负样本声称通过。

## 生成循环与证据
Native Pi 保持同一 conversation；工具失败/漏覆盖作为实际 observation 返回。每条自动生成候选必须有对应内容哈希的成功预览，参数变更后旧验证不适用。请求仍绑定 Agent、工作区、资源映射、策略与模板版本，使用已有文件读取回执。调用在 runner 中串行化以保护累计预算。
路径依据仅接受明确的操作者路径或可见本地资源；资料中出现的外部逻辑对象 ID 不能自行变成本地路径。已通过正向校验的样本进入本轮覆盖账本，最终非空候选集合不能静默丢弃这些目标；无法完成时可返回空候选并说明缺口。账本不替代自然语言意图判断。
原生调查预算为 48 次调用、40 个文件、1 MiB 正文、180 秒；单次文件和 reader 通道原有限制不放宽。JSON 兼容流程保留原预算。扩充常见源码文本扩展名，不开放凭据、运行私有目录、链接或任意主机目录。

## 不作出的保证
预览只证明声明样本的编译后匹配，不证明全部自然语言意图、标签历史、执行链、检查时序或运行内核拦截。tree 使用明确标注的假设后代，不冒充真实文件。验证不授予任何访问能力。底层 ABI、hook、Broker 和 DSH 不改动。

## 安装与验收
构建组件：cc -O2 -Wall -Wextra -I actplane/bpf backend/policy_match_preview.c -o backend/dsl-adapter/target/release/agentscope-match-preview。运行环境需匹配版本的 ActPlane 编译器；仅使用 compile，不调用 run/watch/control。CI 已同步构建步骤。详见对应 REVIEW 与 acceptance/policy-investigation-20261026/e3/results/verification.json。
