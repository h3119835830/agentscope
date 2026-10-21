# REVIEW：受审批短路径映射代码与隔离验收

日期：2026-10-21。状态：短路径映射代码与隔离验收通过；未部署，未执行主服务 RQ5 流程。

## 范围与授权

用户授权先完成代码与隔离测试，主服务维护另行确认。本轮不部署 API、Broker、前端或 DSL 适配器，不重启任何主服务，不通过脚本修改真实 RQ5 数据，也不将合成结果写入主页面。

修改仅在 AgentScope 权限/上下文/读取映射、Broker 沙箱、应用层 DSL adapter、相关前端、测试与文档。ActPlane 核心保持 a182291 树；没有普通 ERP 业务改动、破坏性数据库迁移或远端推送。

## 代码评审结论

映射、权限、批准和应用分离；新增映射强制人工审批。最小写范围仍是源码及产物叶目录，测试/父目录只读。资源身份、代次、策略哈希共同约束候选。原资源登记及宿主文件不变，旧执行路径唯一解析到规范挂载。Pi 的上下文/正文路径映射由服务端统一，无场景补丁提示词。

重点修复继承 fd、父目录重新 bind 绕过、会话前缀误判和跨挂载通配符四类问题，见本日 BUG。

## 测试记录

- 后端早期完整回归 1565 通过；补充边界后的完整回归 1567 通过（5 条已有弃用告警）。
- 一轮复跑因 /tmp/a 测试前置目录缺失产生 93 个初始化错误、1474 通过；没有将该轮算作通过。明确建立测试前置目录后重跑通过。
- 最终完整后端回归：1569 通过，0 失败，5 条已有弃用告警，181.98 秒。包含会话资源归属与缺失目录明确拒绝用例。
- 前端 node --test src/*.test.mjs：407 通过，0 失败、0 跳过；npm run build 通过，150 modules。项目没有 npm test 脚本，采用仓库实际测试命令。
- AgentScope Rust adapter：6 通过，release build 通过。
- ActPlane 原生 cargo test --workspace：145 通过、49 ignored、0 失败；ignored 用例未执行，不算通过。原生 C make -C bpf test：42 通过、0 失败；原生 CLI release build 通过。
- 重新构建原生 CLI 后再次执行隔离内核场景，通过；归档采用此次新报告。
- git diff --exit-code a182291 -- actplane 为空，git diff --check 通过。

## 真实原生隔离实验

执行 scripts/accept_resource_views.py，仅使用独立合成文件、独立 BPF pin，不访问主服务 API/数据库、不启动真实 DSH。先在无规则基线证明 8 个路径可写，再使用仓库原生 ActPlane 二进制运行策略：

| 对象 | 期望及结果 |
| --- | --- |
| 原资源根 /w/0 | 写入阻断 |
| 规范项目根 /v/... | 写入阻断 |
| 原路径及规范路径 tests | 写入阻断，指纹不变 |
| 原路径及规范路径 src | 写入允许 |
| 原路径及规范路径 acceptance-artifacts | 写入允许 |

保留原生 write 阻断事件、二进制 SHA256、编译前 DSL、基线与保护文件前后哈希。测试刻意绕过只读 mount 限制以证明内核本身阻断；另一个真实 bwrap 单测独立验证实际只读 mount、唯一规范路径和无继承 fd。

**此实验不是 RQ5 主页面验收、不是运行时自动收紧、不是独立会话执行域证明。**

## 隔离界面验收

使用实际 WritePermissionDialog 组件、合成 api/post 和临时 18241 页面。Computer Use 操作验证缺少 tests 保护时不可提交，填写精确目录后产生正确申请字段，关闭/ESC 恢复焦点，390px 窄屏无横向溢出；预览已关闭，不连接主服务。

界面按 agentscope-ui-design 的渐进披露、明确目标、审批与应用分离和独立滚动要求实现，未堆叠到主页面。

新证据目录：evidence/resource-views-20261021/。截图为隔离组件，不得当作正式审批或加载证据：
- isolated-mapping-dialog.png
- isolated-mapping-narrow.png
- native-kernel-report.json
- native-policy.yaml

对应测试输出同目录保存为 frontend-tests.log、frontend-build.log、adapter-tests-build.log、
native-c-tests.log、native-workspace-tests.log、native-build.log；最终后端结果归档为 backend-tests.log。
归档日志及 native-policy.yaml 仅规范化行尾空白，未改测试结果或 DSL 语义。

复验命令：

```text
# WSL 项目根目录；后端旧测试需要先存在 /tmp/a
/opt/agentscope/.venv/bin/python -m pytest backend/tests -q --basetemp=<本轮独立目录>
(cd frontend && node --test src/*.test.mjs && npm run build)
(cd backend/dsl-adapter && cargo test && cargo build --release)
(cd actplane && make -C bpf test && cargo test --workspace && cargo build --release -p actplane)
sudo /opt/agentscope/.venv/bin/python scripts/accept_resource_views.py
git diff --exit-code a182291 -- actplane
git diff --check
```

补充环境观察：本轮后段只读检查发现 WSL 启动时间和服务 PID 与早段不同；没有执行
WSL/服务重启命令，原因未在本轮归因。不能据此宣称主服务进程全程不变，维护前须重新
核对实际连接和进程身份。测试临时文件移到 /var/tmp 后归档到独立证据目录，不依赖 /tmp 留存。

## 发布门与未完成项

1. 主服务维护未获准，因此没有发布，本轮真实 RQ5 生成/审批/应用/拦截/任务结果均未覆盖。主页面已有数据没有被本轮验收清理。
2. 本版仅映射既有目录。此前场景缺少 acceptance-artifacts，必须先经受治理的精确目录准备；本轮不提供创建功能、不开放其父目录。
3. 原运行时 Pi 自动评估、单调 Delta 自动接纳/热加载未在本次实现；不能把人工生成或审批当自动运行时。
4. 维护获准后须同步发布 API、前端、AgentScope adapter、Broker；仅恢复经核验的 Agent。通过界面重新读取场景、生成新候选、人工审批、显式应用，读回加载绑定后再执行 RQ5 验收。保留错误历史候选而不批准它们。
5. 运行时未接通则保留 prompt 与“未通过”结论；不手工补造自动策略，不改测试求全绿。
