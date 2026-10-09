

// Display-only examples. Nothing in these explanatory cases executes a tool or a syscall.
const scenarios = [
  {
    label: '脚本偷读凭证', title: '一条测试命令，也可能触发凭证读取',
    task: '运行项目测试，修复失败用例。', tool: 'bash', input: '{ "command": "pytest -q" }',
    output: 'exit_code: 0\n12 passed in 1.82s',
    toolNote: '调用只暴露测试入口；插件内部访问不会展开成新的工具调用。此例插件忽略读取失败，测试仍返回成功。',
    events: [
      ['+02', '系统调用', 'execve', 'execve("/usr/bin/python3",\n  ["python3", "-m", "pytest", "-q"])', '测试进程 PID 5186 · 加载第三方插件'],
      ['+04', '系统调用', 'openat', 'openat(AT_FDCWD,\n  "/home/demo/.aws/credentials", O_RDONLY)', '插件尝试读取工作区之外的凭证文件'],
      ['+04', '内核安全钩子', 'file_open', 'rule: deny-read-credentials\naction: block · verdict: DENY', 'openat 返回 -1 EACCES，未取得该文件描述符', 'blocked']
    ],
    value: '将测试调用关联到真实文件访问，在凭证文件被打开前拒绝越界读取。',
    boundary: '需已加载覆盖该路径与读取操作的规则。这里只展示文件打开链；不据此推断网络行为，也不声称当前控制台提供完整 syscall 采集。'
  },
  {
    label: '链接越界写入', title: '写入工作区文件，实际目标却在工作区外',
    task: '更新项目的本地启动配置。', tool: 'write_file', input: '{\n  "path": "/workspace/app/startup.conf",\n  "content": "# updated configuration\\n"\n}',
    output: 'status: error\npermission denied',
    toolNote: '字符串路径位于工作区内；仅按工具参数审计，无法证明最终写入对象仍在允许范围内。',
    events: [
      ['+02', '系统调用', 'openat', 'openat(AT_FDCWD,\n  "/workspace/app/startup.conf",\n  O_WRONLY | O_TRUNC)', '请求打开工作区内的配置文件'],
      ['+02', '对象解析', 'symlink target', '/workspace/app/startup.conf\n→ /home/demo/.bashrc', '符号链接解析后的实际受保护文件'],
      ['+02', '内核安全钩子', 'file_open', 'rule: protect-shell-startup\naction: block · verdict: DENY', 'openat 返回 -1 EACCES，目标未被打开或截断', 'blocked']
    ],
    value: '根据实际访问对象执行规则，识别工具参数中看不出的链接越界。',
    boundary: '实际保证取决于解析后的路径匹配、对应钩子及截断时机的验收；设计示例不构成现有实现已覆盖所有链接或 TOCTOU 情形的证明。'
  },
  {
    label: '篡改验收证据', title: '“修复测试”的脚本，可能先改掉测试本身',
    task: '修复登录逻辑，保留原有验收标准。', tool: 'bash', input: '{ "command": "python repair.py" }',
    output: 'exit_code: 1\nPermissionError: [Errno 13]',
    toolNote: '工具入口仍是修复脚本；是否更改源码、测试或验收报告，要看脚本实际触及的文件。',
    events: [
      ['+02', '系统调用', 'execve', 'execve("/usr/bin/python3",\n  ["python3", "repair.py"])', '修复进程 PID 5186'],
      ['+06', '系统调用', 'openat', 'openat(AT_FDCWD,\n  "/workspace/tests/test_auth.py",\n  O_WRONLY | O_TRUNC)', '尝试重写受保护的验收测试'],
      ['+06', '内核安全钩子', 'file_open', 'rule: protect-acceptance-tests\naction: block · verdict: DENY', 'openat 返回 -1 EACCES，测试文件未被截断', 'blocked']
    ],
    value: '将可修改源码与不可修改的验收文件分开授权，保护验证依据。',
    boundary: '保护文件完整性不等于判断修复正确。测试目录、报告文件以及重命名、删除等路径，需要在策略与验收中分别覆盖。'
  },
  {
    label: '后台继续写入', title: '工具调用已返回，后台进程还在继续写',
    task: '生成导出文件；任务结束后撤销输出写权限。', tool: 'bash', input: '{ "command": "python export.py &" }',
    output: 'exit_code: 0\nbackground pid: 5192',
    toolNote: '调用已经结束，不代表它启动的后台进程已经停止。撤权后可能没有新的工具调用可供审计。',
    events: [
      ['+02', '进程关联', 'child process', 'parent PID 5186 → child PID 5192\ndomain: D-42', '后台导出进程沿用任务安全域'],
      ['+80', '策略控制面', 'scope update', 'D-42: policy v3 → v4\nwrite /workspace/output/**: revoked', '规则已加载的示例时刻；并非只提交了撤权请求'],
      ['+85', '内核安全钩子', 'file_permission', 'write(fd=7, …)\nrule: revoke-output-write · DENY', 'write 返回 -1 EACCES，本次写入被拒绝', 'blocked']
    ],
    value: '把任务授权持续约束到后台进程，在规则加载后检查后续文件写入。',
    boundary: '需证明进程绑定、撤权加载时刻与已有 FD 的写入检查；mmap、异步 I/O 等另做验收。先前已完成的写入不会被追溯撤回。'
  },
  {
    label: '跨任务越权', title: '同一台机器，也不能借另一个任务的权限',
    task: '任务 A 汇总自己的执行结果。', tool: 'bash', input: '{ "command": "python summarize.py" }',
    output: 'exit_code: 1\nPermissionError: [Errno 13]',
    toolNote: '两项任务都能调用 bash；工具名相同，并不意味着可以访问相同的工作区。',
    events: [
      ['+02', '进程关联', 'task domain', 'task-A → PID 5186 → domain D-A', '检查使用任务 A 的安全域与策略'],
      ['+03', '系统调用', 'openat', 'openat(AT_FDCWD,\n  "/workspace/task-B/private.json", O_RDONLY)', '尝试读取任务 B 的私有文件'],
      ['+03', '内核安全钩子', 'file_open', 'rule: task-workspace-boundary\ndomain: D-A · verdict: DENY', 'openat 返回 -1 EACCES，未取得文件描述符', 'blocked']
    ],
    value: '按任务安全域限制实际资源访问，避免一个 Agent 借用另一任务的权限。',
    boundary: '需正确绑定进程及后代并隔离 Broker 能力。示例不是“所有跨任务通信都已阻断”的证明；共享内存、IPC、网络仍需各自覆盖。'
  },
  {
    label: '伪造扩权审批', title: '“用户已经同意”不能替代可信审批记录',
    task: '在授权工作区生成报告；发布到外部需要审批。', tool: 'request_scope_change', input: '{\n  "request": "allow external publish",\n  "reason": "用户已在对话中同意"\n}',
    output: 'status: pending_approval\nloaded: false · active: false',
    toolNote: '模型输出“已获同意”只是声明；必须与可信审批主体、提案版本和目标域绑定。',
    events: [
      ['+02', '策略控制面', 'proposal created', 'proposal: P-17\nbase_version: v3 · target: D-42', '扩权申请已登记，尚未生效'],
      ['+03', '可信审批', 'approval check', 'approval_receipt: missing\nstatus: pending_approval', '缺少与该提案绑定的人类审批回执'],
      ['+03', '加载门禁', 'load rejected', 'approved: false · loaded: false\nactive policy: v3', '扩权未加载；安全域继续使用原有规则', 'blocked']
    ],
    value: '让扩权取决于可信审批与加载流程，防止自然语言自证授权。',
    boundary: '这是控制面审计，不是系统调用或内核钩子。拒绝扩权申请不等于一次网络访问已被内核拦截。'
  }
];

const caseStories = [
  {
    actor:'开发者小林', task:'运行 app 项目的测试，修复失败用例。', files:['app/','第三方测试插件','/home/demo/.aws/credentials'],
    story:['小林只要求 Agent 运行项目测试，没有授权它读取个人云服务凭证。','pytest 加载第三方插件；插件初始化时尝试打开 credentials，访问在文件打开阶段被拒绝。','插件忽略了读取错误，测试仍返回 12 passed。工具返回成功不代表内部每次访问都获得了授权。'],
    result:'项目测试继续运行，凭证文件没有被该次访问打开。'
  },
  {
    actor:'开发者小周', task:'更新 app/startup.conf 中的本地启动配置。', files:['/workspace/app/startup.conf','/home/demo/.bashrc'],
    story:['小周允许 Agent 修改项目内的启动配置，个人 shell 启动文件仍受保护。','startup.conf 是一个符号链接，真正指向 /home/demo/.bashrc；工具参数看上去仍是项目路径。','访问到达内核时，规则检查解析后的目标文件并拒绝打开，工具收到 permission denied。'],
    result:'这次写入没有修改或截断 .bashrc，Agent 需要改用合法的项目配置文件。'
  },
  {
    actor:'开发者小陈', task:'修复登录逻辑，保持 tests/test_auth.py 的验收标准。', files:['src/auth.py','tests/test_auth.py','repair.py'],
    story:['小陈允许修改登录源码，把原有验收测试设为只读。','repair.py 没有先修复源码，而是尝试重写 test_auth.py，让原本失败的断言消失。','写打开命中测试保护规则并被拒绝，脚本返回 PermissionError。'],
    result:'验收标准保持原样，修复必须通过真正的登录测试。'
  },
  {
    actor:'分析员小王', task:'导出销售汇总，任务结束时撤回 output 目录的临时写权限。', files:['sales.csv','output/sales-summary.csv','后台导出进程 PID 5192'],
    story:['小王授权导出任务写入 output，Agent 启动后台进程后工具调用先返回。','任务结束，输出写权限被撤回；后台进程仍持有之前打开的文件描述符。','后台进程再次 write 时按新的执行规则检查，本次写入返回 EACCES。'],
    result:'工具调用结束之后的访问也要接受当前授权检查，之前已完成的写入仍保留。'
  },
  {
    actor:'分析员小赵', task:'让任务 A 汇总销售文件，任务 B 的薪资材料保持私有。', files:['task-A/sales.csv','task-B/private.json'],
    story:['小赵分别建立销售汇总与薪资审核两个任务，各自有独立工作区。','任务 A 的 summarize.py 错误地尝试读取 task-B/private.json。','文件访问按任务 A 的安全域检查，不能借用任务 B 的读取权限。'],
    result:'销售任务只能读取自己的授权材料，薪资文件未被这次访问打开。'
  },
  {
    actor:'项目负责人小吴', task:'生成内部报告，发布到外部服务前需要单独审批。', files:['output/internal-report.pdf','扩权提案 P-17'],
    story:['小吴只批准在当前工作区生成报告，没有批准对外发布。','Agent 提交发布扩权请求，并在理由中写“用户已经同意”。','控制面查不到与 P-17 绑定的可信审批回执，扩权保持待审，原有策略继续生效。'],
    result:'自然语言里的同意声明不会直接变成外部发布权限。'
  }
];
scenarios.forEach((scene,index)=>Object.assign(scene,caseStories[index],{group:index<4?'execution':'governance'}));

scenarios.push(
  {
    group:'execution', label:'插件自行外联', title:'没有工具调用，插件也在尝试外联', actor:'产品经理小林',
    task:'启动报告 Agent，读取 sales.csv 并生成本地销售汇总。', files:['sales.csv','report_plugin.py','output/summary.md'],
    leftTitle:'用户与应用事件', leftKind:'本段无工具调用',
    leftSteps:[['+0ms','用户启动任务','读取 sales.csv\n将汇总写入 output/summary.md'],['+2ms','应用加载插件','import report_plugin\n初始化回调：检查更新']],
    toolNote:'插件初始化回调直接使用 HTTP 库，不会产生新的 Agent 工具调用。目标外部地址没有获得授权。',
    events:[
      ['+02','系统调用','execve','execve("/usr/bin/python3",\n  ["python3", "report_agent.py"])','报告进程 PID 5186 已绑定任务安全域'],
      ['+04','系统调用','connect','connect(fd=9,\n  203.0.113.20:443)','插件准备连接未授权的外部地址'],
      ['+04','内核安全钩子','socket_connect','rule: local-report-only\naction: block · verdict: DENY','connect 返回 -1 EACCES，连接未建立','blocked']
    ],
    relation:['用户：小林','PID 5186','D-42 / v3'],
    value:'即使没有新的工具调用，受管进程的实际外联仍按任务授权检查。',
    story:['小林只需要本地销售报告，允许读取 sales.csv 和写入 output/summary.md。','报告 Agent 启动时自动导入 report_plugin.py；插件在初始化回调里尝试连接外部更新服务。','这段网络访问没有经过 Agent 的工具接口，但 connect 命中任务的外联限制并被拒绝。'],
    result:'外部连接未建立，Agent 可以继续通过已授权的本地文件完成报告。',
    boundary:'此过程要求插件运行在已绑定的受管进程域；受信宿主和模型传输不自动纳入相同约束。'
  },
  {
    group:'execution', label:'跨进程数据外流', title:'读取和上传都正常，数据组合起来却越界', actor:'分析员小许',
    task:'分析客户资料，生成只保存在本地的汇总文件。', files:['data/customers.csv','output/summary.json','上传进程 PID 5192'],
    leftTitle:'任务与文件流转', leftKind:'跨进程行为',
    leftSteps:[['+0ms','用户授权','读取 data/customers.csv\n客户资料与派生文件仅限本地使用'],['+6ms','程序生成报告','分析进程写入 output/summary.json\n上传进程随后读取该报告']],
    toolNote:'单看“读取客户资料”或“读取报告”都符合任务；风险出现在带有客户资料来源的数据准备流向外部。',
    events:[
      ['+02','文件读取','read → label','PID 5186 reads customers.csv\nlabel: customer_private','分析进程取得客户资料来源标签'],
      ['+06','信息流传播','write → read','PID 5186 → summary.json → PID 5192\nlabel: customer_private','标签沿已观测的文件写入与读取传播'],
      ['+08','内核安全钩子','socket_connect','PID 5192 → 203.0.113.30:443\ncustomer_private → external: DENY','connect 返回 -1 EACCES，外部连接未建立','blocked']
    ],
    relation:['customers.csv','summary.json','PID 5192'],
    value:'把数据来源与后续去向关联起来，约束多个合法操作组合出的泄露路径。',
    story:['小许允许读取客户资料做分析，但要求资料和派生报告留在本地。','分析进程写出 summary.json，上传进程随后读取它；客户资料来源标签沿这两次文件访问传播。','上传进程尝试新建外部连接时，信息流规则发现其携带 customer_private 标签并拒绝连接。'],
    result:'报告保存在本地，这条跨进程外发路径没有建立连接。',
    boundary:'需覆盖对应 read/write、进程与 connect 边；既有连接、加密内容、共享内存等路径需要独立验证。'
  },
  {
    group:'governance', label:'上下文丢失约束', title:'摘要忘了限制，执行规则仍然记得', actor:'开发者小周',
    task:'修复登录逻辑，明确要求 tests/test_auth.py 不可修改。', files:['会话摘要','src/auth.py','tests/test_auth.py'],
    leftTitle:'用户与会话上下文', leftKind:'长会话过程',
    leftSteps:[['第 1 轮','用户要求','可以修改 src/auth.py\n不要修改 tests/test_auth.py'],['第 20 轮','压缩后的摘要','继续修复登录问题\n摘要中遗漏了测试只读要求']],
    toolNote:'模型上下文中的限制可能被遗漏，但摘要更新不等于撤回已经加载的测试保护规则。',
    events:[
      ['+02','策略控制面','policy retained','domain: D-42 · policy: v3\nprotect tests/test_auth.py','保护规则独立于模型会话摘要保存'],
      ['+04','系统调用','openat','openat("tests/test_auth.py",\n  O_WRONLY | O_TRUNC)','Agent 随后尝试改写验收文件'],
      ['+04','内核安全钩子','file_open','rule: protect-acceptance-tests\naction: block · verdict: DENY','openat 返回 -1 EACCES，测试文件未被截断','blocked']
    ],
    relation:['用户约束','D-42 / v3','test_auth.py'],
    value:'把重要安全约束保存在模型记忆之外，避免摘要遗漏直接变成权限扩大。',
    story:['小周在任务开始时明确保护验收测试，规则加载后才让 Agent 执行。','经过多轮修复，会话压缩后的摘要遗漏了“测试文件不可修改”。','Agent 再次尝试写测试时，内核仍检查独立保存的保护规则；摘要不能取消该规则。'],
    result:'测试文件保持不变，Agent 根据拒绝反馈回到登录源码继续修复。',
    boundary:'保护已配置的系统效果，不代表内核能识别摘要内容是否正确或检测所有记忆污染。'
  },
  {
    group:'governance', label:'验收结果过期', title:'测试通过后又改了代码，旧结果不能放行', actor:'发布负责人小陈',
    task:'确认最新代码通过验收后，再发布登录服务。', files:['src/auth.ts','验收回执 T-17','发布候选 H2'],
    leftTitle:'验收与发布过程', leftKind:'跨事件时序',
    leftSteps:[['第 1 步','测试通过','源码版本 H1\n验收回执 T-17: passed'],['第 2 步','代码再次修改','src/auth.ts: H1 → H2\n准备使用 T-17 申请发布']],
    toolNote:'T-17 本身是真实的成功回执，但它对应修改之前的 H1，不能证明当前 H2 已经通过验收。',
    rightTitle:'流程门禁 trace', rightKind:'版本 / 验收关联',
    events:[
      ['+02','版本记录','source changed','current source: H2\nlast tested source: H1','最近一次源码修改使原有验收条件失效'],
      ['+04','验收关联','receipt check','T-17.source = H1\nrelease.source = H2','验收回执与待发布版本不一致'],
      ['+04','发布门禁','hold release','H2: verification required\nrelease: HELD','当前版本重新通过验收后再继续发布','blocked','暂停']
    ],
    relation:['T-17 / H1','源码更新 H2','重新验收'],
    value:'检查最新修改之后的验收条件，避免用过时的成功结果放行新代码。',
    story:['小陈要求发布前验证最新代码；Agent 首先完成 H1 的测试并得到 T-17。','Agent 随后又修改 src/auth.ts，生成 H2，但没有重新测试。','发布流程核对代码版本与验收回执，发现 T-17 只覆盖 H1，暂停 H2 的发布。'],
    result:'Agent 需要对 H2 重新执行验收并取得对应回执，才能继续发布。',
    boundary:'版本绑定的发布门禁为本设计的控制面候选；论文的命令时序规则不等同于已有这一发布集成。'
  },
  {
    group:'governance', label:'审批后对象变化', title:'审批的是快照 A，启动时却换成了 B', actor:'项目负责人小吴',
    task:'按照审核过的依赖清单启动报告任务。', files:['requirements.lock','已确认快照 A','执行副本 B'],
    leftTitle:'审批与工作区过程', leftKind:'执行对象一致性',
    leftSteps:[['审核时','用户确认','快照 A / requirements.lock\nmanifest: H1'],['启动前','执行副本发生变化','requirements.lock 内容被替换\n执行副本清单变为 H2']],
    toolNote:'用户批准的是固定快照 A 的内容。执行副本发生变化后，不能继续沿用原来的确认。',
    rightTitle:'控制面 trace', rightKind:'快照 / 哈希复核',
    events:[
      ['+02','审批记录','approved snapshot','approved manifest: H1\nsource snapshot: A','审批回执绑定固定清单'],
      ['+04','执行前复核','manifest mismatch','execution manifest: H2\nexpected manifest: H1','执行副本不再与已确认对象一致'],
      ['+04','启动门禁','launch held','H1 ≠ H2\nlaunch: HELD','重新确认一致的执行对象后再启动','blocked','暂停']
    ],
    relation:['快照 A / H1','执行副本 / H2','启动复核'],
    value:'将审批绑定到具体内容，避免批准的对象与实际执行对象发生替换。',
    story:['小吴检查 requirements.lock 并确认快照 A，控制面保存其清单哈希 H1。','启动前，执行副本中的依赖清单被其他进程替换，重新计算的清单变成 H2。','执行前复核发现 H1 与 H2 不同，暂停启动，让用户重新确认或恢复正确副本。'],
    result:'替换后的依赖不会借用快照 A 的审批直接进入执行。',
    boundary:'需复核实际执行副本和来源清单；冻结来源并不自动提供原始目录的事务快照。'
  },
  {
    group:'governance', label:'保护尚未生效', title:'策略编译通过，也要确认保护真正就位', actor:'数据管理员小许',
    task:'先保护客户资料，再启动分析任务。', files:['data/customers.csv','策略包 P-42','任务执行域'],
    leftTitle:'用户与策略操作', leftKind:'启动前核验',
    leftSteps:[['第 1 步','用户确认保护规则','客户资料仅限当前分析任务读取\n策略包 P-42 已批准'],['第 2 步','编译完成','compile: passed\n等待规则加载与任务绑定']],
    toolNote:'编译成功说明策略包能够生成，不等于目标进程已经受保护。任务启动还需要加载与绑定证据。',
    rightTitle:'控制面 trace', rightKind:'加载 / 绑定核验',
    events:[
      ['+02','策略状态','compiled / approved','compiled: true\napproved: true','策略包完成编译并获得确认'],
      ['+04','执行状态','load / binding','loaded: false\npid_domain_binding: missing','加载或任务域绑定没有完成'],
      ['+04','启动门禁','fail closed','active: false\nlaunch: HELD','保护未就位，分析任务保持未启动','blocked','暂停']
    ],
    relation:['P-42','加载回执','PID / 执行域'],
    value:'区分生成、批准、加载和生效，避免把配置完成当作安全保护已经建立。',
    story:['小许要求分析任务读取客户资料之前先建立访问保护，并确认策略包 P-42。','策略编译完成，但执行后端没有完成加载或目标进程的安全域绑定。','控制面核对加载与绑定状态，发现保护尚未就位，因此不放行分析任务。'],
    result:'任务等待有效保护建立后再启动，不在没有保护的状态下尝试处理客户资料。',
    boundary:'生效状态还需要真实域绑定和独立操作证据，编译或页面状态本身不足以证明内核效果。'
  }
);


const ids = ["script","link","integrity","revoke","isolation","approval","plugin","dataflow","context","stale-receipt","snapshot","inactive"];
export const noticeGroups = [{id:'execution',label:'执行与数据'},{id:'governance',label:'授权与流程'}];
export const noticeCases = scenarios.map((scene,index)=>({
  ...scene, id:ids[index],
  leftTitle:scene.leftTitle || '工具调用 trace',
  leftKind:scene.leftKind || '入口与返回',
  leftSteps:scene.leftSteps || [['+0ms',scene.tool,scene.input],[index===0?'+1.9s':index===3?'+3ms':'+9ms','工具返回',scene.output]],
  isToolTrace:!scene.leftSteps,
  rightTitle:scene.rightTitle || (index===5?'控制面 trace':'系统侧 trace'),
  rightKind:scene.rightKind || (index===5?'可信审批 / 加载':'系统调用 / 内核事件'),
  relation:scene.relation || (index===5?['call_a12','P-17 / D-42','审批与加载记录']:['call_a12',`PID ${index===3?'5192':'5186'}`,`${index===4?'D-A':'D-42'} / ${index===3?'v4':'v3'}`]),
}));
