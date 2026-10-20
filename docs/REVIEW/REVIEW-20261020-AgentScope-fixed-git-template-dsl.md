# REVIEW：固定 Git 命令与真实 DSL 预览（2026-10-20）

## 结果

- 六个可执行 Git 模板追加固定合同版本：git、commit/push 在模板中固定，程序不再是新模板的参数。模板和配置界面只读展示命令；API 拒绝固定字段及历史合同新建降级。
- 模板有真实 DSL 骨架；默认动作与参数通过实际渲染器生成预览。新建配置无需保存即可查看当前 DSL，编辑配置另有原版本 DSL。所有可执行模板也提供默认骨架给策略 Agent。
- block 可见但禁用，原因明确；实际仍为 notify/kill，未伪称事前阻断。四类未实现语义保持 null DSL 和禁止提交。
- 沿用现有样式，未改 DSH/ActPlane/Broker、导航、工作区和会话流程。

## 验收

1. 后端全量 1421 passed，前端 352 passed，Vite 构建通过；5 项既有弃用警告。
2. compatibility.json：74 个历史定义哈希不变，37 个 v2 materialize 完整返回值相同；新版本追加后历史自定义 v3 定义和审批仍可核验。
3. kernel-results.json：新固定合同生成的真实 DSL，在独立 pin root/合成仓库中进行 Git/BPF 13 项验证，检查成功放行，缺少/失败/写入后失效命中 kill；notify 仍允许继续。不能据此宣称副作用前阻断或完整 Git 治理。
4. service-results.json：独立 18169 数据库和真实模型，分别选择新版本 COMMIT/PUSH，只填写 effect；固定命令冻结在生成快照。
5. 浏览器：固定命令 readonly、block disabled；未保存时 notify/kill 规则正确；模板默认 checker/target/exit_code 修改实时显示 exits 2。保存模板新版本后新建配置继承规则，旧配置仍保持原版本。
6. 小屏实际 innerWidth=390，文档宽 375，保存栏 bottom=751，小于视口高 760；DSL 可读，临时视口覆盖已恢复。

预览不保存配置、审批或执行状态。只在隔离库保存验收模板和配置，正式发布仅追加授权的新模板定义；正式环境既有配置、审批和运行策略保留。发布与浏览器证据见 evidence/template-dsl-preview-20261020。

## 正式发布

已发布到 `/opt/agentscope-template-dsl-20261020-115515`，API 重启 1.219 秒。Broker 未重启，DSH PID 192987/193658、执行代次、域与策略哈希一致；13 个原有配置/审批表哈希与行数不变。policy_template_versions 仅追加 6 个授权的新模板定义及发布审计，旧定义和配置不覆写。正式页脚本 main-Bp6r5Vdv.js；实际打开固定命令/禁用 block 及未保存 notify DSL 预览，没有在正式环境新增配置、批准、加载或停用策略。
