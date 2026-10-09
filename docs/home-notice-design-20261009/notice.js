'use strict';

// Display-only examples. Nothing in this prototype executes a tool or a syscall.
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

const dialog = document.getElementById('security-notice');
const openButton = document.getElementById('open-notice');
const content = document.getElementById('scenario-content');
const seenKey = 'agentscope-notice-design-20261009-v1-seen';
const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
let previousFocus = openButton;

function renderScenario(index) {
  const scene = scenarios[index];
  document.querySelectorAll('.scenario-button').forEach((button, position) => button.setAttribute('aria-current', String(position === index)));
  const systemTitle = index === 5 ? '控制面 trace' : '系统侧 trace';
  const systemKind = index === 5 ? '可信审批 / 加载' : '系统调用 / 内核事件';
  const correlation = index === 5 ? '<code>call_a12</code><span class="link-arrow">→</span><code>P-17 / D-42</code><span class="link-arrow">→</span><span>审批与加载记录</span>' : `<code>call_a12</code><span class="link-arrow">→</span><code>PID ${index === 3 ? '5192' : '5186'}</code><span class="link-arrow">→</span><code>${index === 4 ? 'D-A' : 'D-42'} / ${index === 3 ? 'v4' : 'v3'}</code><span>· 关联同一次执行</span>`;
  content.innerHTML = `
    <h3 class="scene-heading">${escapeHtml(scene.title)}</h3>
    <p class="scene-task"><strong>用户任务</strong>　${escapeHtml(scene.task)}</p>
    <div class="trace-grid">
      <section class="trace-panel" aria-label="工具调用 trace">
        <header class="trace-header"><h3>工具调用 trace</h3><span>入口与返回</span></header>
        <div class="tool-trace">
          <div class="trace-step"><span class="time">+0ms</span><div><div class="step-title"><span class="tool-name">${escapeHtml(scene.tool)}</span><span>call_a12</span></div><pre class="code-box">${escapeHtml(scene.input)}</pre></div></div>
          <div class="trace-step"><span class="time">${index === 0 ? '+1.9s' : index === 3 ? '+3ms' : '+9ms'}</span><div><div class="step-title">工具返回</div><pre class="code-box output">${escapeHtml(scene.output)}</pre></div></div>
        </div>
        <p class="tool-insight">${escapeHtml(scene.toolNote)}</p>
      </section>
      <section class="trace-panel" aria-label="${systemTitle}">
        <header class="trace-header"><h3>${systemTitle}</h3><span>${systemKind}</span></header>
        <div class="system-trace">${scene.events.map(event => `<div class="system-event ${event[5] || ''}"><span class="time">+${Number(event[0])}ms</span><div><div class="event-source"><span>${event[1]}</span><strong>${escapeHtml(event[2])}</strong>${event[5] ? '<span class="verdict">拒绝</span>' : ''}</div><pre class="event-code">${escapeHtml(event[3])}</pre>${event[5] ? `<div class="event-detail">${escapeHtml(event[4])}</div>` : ''}</div></div>`).join('')}</div>
      </section>
    </div>
    <div class="correlation" aria-label="关联字段示例">${correlation}</div>
    <div class="value-line"><strong>新增价值</strong><span>${escapeHtml(scene.value)}</span></div>
    <details class="evidence-details"><summary>示例说明与能力边界</summary><p>本页所有调用、PID、域、事件、相对时序均为设计样例；不是本机历史记录或实时采集。右侧按发生过程组织关键事件，不是完整 strace。工具名称用于说明交互，正式接入须映射实际工具 schema。</p><p>链路说明：${scene.events.map(event=>escapeHtml(event[4])).join('；')}。</p><p>${escapeHtml(scene.boundary)}</p></details>`;
}

function openNotice() {
  previousFocus = document.activeElement;
  if (!dialog.open) dialog.showModal();
}

function closeNotice() {
  try { localStorage.setItem(seenKey, 'true'); } catch {}
  document.getElementById('unread-dot').hidden = true;
  dialog.close();
  if (previousFocus && previousFocus !== document.body && typeof previousFocus.focus === 'function') previousFocus.focus();
  else openButton.focus();
}

document.getElementById('scenario-buttons').innerHTML = scenarios.map((scene, index) => `<button type="button" class="scenario-button" data-index="${index}" aria-current="${index === 0}" aria-controls="scenario-content"><span class="scenario-number">${String(index+1).padStart(2,'0')}</span><span>${scene.label}</span></button>`).join('');
document.getElementById('scenario-buttons').addEventListener('click', event => {
  const button = event.target.closest('.scenario-button');
  if (button) renderScenario(Number(button.dataset.index));
});
openButton.addEventListener('click', openNotice);
document.getElementById('close-notice').addEventListener('click', closeNotice);
document.getElementById('understood').addEventListener('click', closeNotice);
dialog.addEventListener('cancel', event => { event.preventDefault(); closeNotice(); });
dialog.addEventListener('keydown', event => {
  if (event.key !== 'Tab') return;
  const controls = Array.from(dialog.querySelectorAll('button, summary')).filter(element => !element.disabled && element.getClientRects().length);
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus();
  }
});
renderScenario(0);
let seen = false;
try { seen = localStorage.getItem(seenKey) === 'true'; } catch {}
document.getElementById('unread-dot').hidden = seen;
if (!seen) openNotice();
