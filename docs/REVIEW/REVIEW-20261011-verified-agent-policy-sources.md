# REVIEW-20261011 实际运行来源与手动应用边界

范围：真实 18003 的来源读取、只读 observer、产品 DSL 编辑器与模板、自由描述环境上下文。未改原生 Agent、Broker 执行器或 ActPlane 语言合同。

## 评审与整改

- 复现旧编辑器 placeholder 仍为 source AGENT = exec "**"；模板/自由描述来源曾按产品名推断。已统一接入 verified-process-executable，当前实际程序 /opt/agentscope/bin/node，对应 **/node。
- 首次真实发布暴露 API 独立账号无法读取目标 /proc/PID/exe。保留失败截图 initial-api-permission-failure.png；追加只读 observer 后，真实 API、模板和编辑器均读到实际程序。没有扩大 API 账号权限或重启 Agent。
- 观察器能力限于已登记运行身份读取与最小 /run 快照写入，数据库以 mode=ro 打开。测试确认未导出任意 runtime 字段、未写数据库；API 拒绝可写/非 root 快照、过期/未来时间、跨 boot 和错配身份。
- 前后两次 proc 身份核验降低 PID/exec 变化误读；快照最多八秒存在观察延迟。它只用于草案上下文，应用权限仍由既有 Broker/CAS/环境复核把关。不能把快照直接当作批准或活跃内核绑定。
- 旧生成来源 basis/path 变化使环境 hash 改变。不会改写旧候选；用户需要重新生成/核验。旧手工 DSL 和已加载策略不自动改变。

## 自动测试

- 前端：218 passed、0 failed；包括真实来源新草案、无规则 stub、通用来源显式替换、保留其他 source、身份变化、未就绪来源不回退、目标切换与导入联动。
- 后端：964 passed、52 skipped、5 项既有弃用警告；34.00 秒。覆盖 proc/boot/start_ticks、执行程序变化、只读投影及隐藏连接、缓存权限/年龄/身份、只读 observer 和现有生成/应用回归。
- 测试环境显式使用已有 release 的真实 DSL adapter。初次缺省 adapter 路径不存在造成 setup 错误，修正环境路径后完整测试通过；未用替身绕过 ActPlane 编译检查。52 项按既有依赖/特权条件跳过，不能当作通过。
- Vite 构建通过，109 modules；保留已有单包大于 500 KB 提示。

## 真实验收

1. 当前 DSH PID 54870：API policy-context 与 console DSL source_context 返回 executable=/opt/agentscope/bin/node、pattern=**/node、basis=verified-process-executable；entry 保留 bin.js 启动入口。
2. Agent DSL 新草案正确预填 source AGENT = exec "**/node"，同时显示真实执行路径；仅来源 stub 的保存校验按钮禁用。
3. 导入通用来源文档后提示改用当前来源；替换仅修改本地候选，保留其他 source，未调用保存、proposal、confirm。测试候选均丢弃。
4. 模板 DSL 预览显示真实 **/node 和执行路径。切到未运行 Hermes 不沿用 DSH 来源且不能带入候选；系统存在未核验连接时明确列出，不猜测 Python 或 **。
5. UI 更新使用隔离备份；API 使用独立新 release，observer active。核对 API source manifest 与静态构建产物一致。只重启 API；Broker、连接 PID/代次/active/gate/policy_hash、所有 DSL scope revision/hash/phase、全部 proposal 状态逐项与发布前一致。

## 证据与限制

证据目录：evidence/runtime-sources-20261011/（用户指定技术文档目录）。主要文件为 agent-dsl-source.png、template-dsh-source.png、browser-acceptance.json、live-source-facts.json、runtime-invariance.json 及三份测试/构建日志。initial-api-permission-failure.png 是已修复故障的早期证据；rebound-local-candidate.png 仅为交互调试记录，不代表已保存策略。

本轮没有调用真实策略保存/编译/批准/应用接口，没有启动或停止 Agent，没有新生成或加载策略，不能宣称本轮候选已产生内核拦截或反馈送达。本轮验证自由描述读取的共享来源和既有生成回归，未再次发起真实模型生成。策略应用仍由用户确认。源代码可本地提交，未获推送授权，不推送远端。
