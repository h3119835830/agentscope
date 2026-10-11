# REVIEW-20261011 Agent 自由描述环境适配与会话选用

实现边界：服务端环境/对象核验、不可变适配版本、真实 Agent 能力上下文、持久会话生成记录、记录式选择、关联 DSL 草案与最终确认前重核验。

## 风险与整改

- 路径或环境伪造：输入 schema 拒绝自报 workspace；服务端从连接、代次与原生映射取值，非规范/越界/符号链接路径失败关闭。
- 环境变化：目录/对象身份、资源、运行代次、系统/Agent 修订等进入 hash；生成前后、选择、propose、apply 重核验。apply 前失败不能停止进程或改变 revision。
- 跨 Agent/跨会话串用：持久查询按实例与原生会话，前端切换重置；候选 GET 以产物关联的真实实例为准。会话来源与 Agent 共享应用范围在界面明确区分。
- 错误能力事实：真实验收暴露旧任务 write/unlink 说明误导实例 read/open 转换，已分离后端能力。模型评审猜测不再混入用户要求。
- 适配目录却未绑定对象：已增加来源逐字定位的通用对象计划及服务端验证。future_path 不代表存在或内容已读取。
- 误应用：本轮仅生成、选择、保存并校验；没有调用 confirm/review。拒绝或归档候选不能选择，手工 DSL 与关联候选显式分离。

## 验收证据

详见 evidence/agent-policy-context-20261011/acceptance.json、真实页面截图与测试日志。真实模型输入“禁止这个 Agent 打开当前会话工作目录中的 .env 文件。”无需手填绝对路径，最终生成 block open file /w/0/.env，静态编译通过，Broker 校验通过，保持 pending_review 与 pending proposal。

验收中未成功的早期生成也保留在服务端：6e3d306c4d3d4ed8a783caa0efead190（旧能力说明），71bc4ccc0b804637b38fc949c2a531d4、97f178b7981f460a80e296586a555dc5（目录上下文未具体绑定对象）。成功批次 f0147808cd8e45e78c660933d0c452cd，产物 fe9e81649d154261bc7886d51786ef88。没有篡改旧结果或强制把 unresolved 置空。

API 首次切换用时 2.232 秒，采样不可达最长约 2.076 秒；后续经测试的 API 修订均约 1 秒完成。原生 DSH PID 54870、运行代次与策略修订保持原值。最终部署 API 切换 1.024 秒；按实例 ID 比较全部连接的 PID、代次、策略 hash、gate、connected/active，以及全部 DSL scope 的 revision/hash/phase，均与改动前一致。前后列表的返回排序不同，不作为状态变化。

限制：未确认应用，因此未加载本轮候选、未证明其内核命中或反馈送达；原生会话共享执行器。Vite 仍提示单包超过 500 KB；测试环境缺少的可选依赖/特权验收按已有条件跳过，不将跳过描述为通过。

## 最终验收结果

- 后端完整测试：940 passed、52 skipped（已有条件跳过）、5 项已有弃用警告；31.95 秒。
- 前端测试：206 passed；Vite 构建通过。生产 UI 所有 assets/index 与测试构建一致，11 个变更后端源文件与发布 manifest hash 一致。
- 真实页面：新页面从服务端恢复已生成会话；切换 Hermes 不显示 DSH 候选且不能发送；切换原生会话后不会出现其他会话候选；会话记录选择后带入对应 Agent 的 DSL 草案；1280×720 页面无横向溢出，输入框完整可见。
- 真实 API：context/conversation/candidate 返回 200；跨实例候选、未运行实例环境、错误会话返回 409。未连接状态提示先连接并核验，避免误报运行代次变化。
- 第二工作区批次 ba9d59bec9f04a92be46b31f56e21042、产物 927c3b21d6f5494db24cb152a6fe5c13：README.md 自动绑定 /w/1/README.md、适配 complete、静态编译通过。此项验证对象映射与隔离；模型候选同时包含 write/open，需要人工评审是否扩大操作范围，不将编译成功视为语义已批准。
- .env 候选 abc350357edc 对应 DSL proposal 校验通过，仍为 pending；原有 7df4ac16c8c5 草案保留。未执行 review/confirm，没有本轮 apply/load 记录，也没有停止/重启原生 Agent 或 Broker。

RFC、ADR、BUG 与本 REVIEW 同步到用户指定技术文档目录。未推送远端；本轮不合并其他分支。
