import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import HistoryLibrary from './HistoryLibrary.jsx';
import BootstrapPanel from './BootstrapPanel.jsx';

const api = async (url, options = {}) => {
  const token = typeof sessionStorage === 'undefined' ? '' : sessionStorage.getItem('agentscopeAdminToken') || '';
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `请求失败 (${response.status})`);
  return data;
};
const post = (url, body = {}) => api(url, { method: 'POST', body: JSON.stringify(body) });
const short = (value, n = 12) => value ? `${value.slice(0, n)}…` : '—';
const HISTORY_MODULES = [
  {page:'generate',title:'策略生成',icon:'⌘'},
  {page:'records',title:'策略记录与加载',icon:'⇥'},
  {page:'audit',title:'采集与审计',icon:'▦'},
];
const when = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';

function App() {
  const [loginToken,setLoginToken]=useState('');
  const [authenticated,setAuthenticated]=useState(false);
  const [loginError,setLoginError]=useState('');
  const [authReady,setAuthReady]=useState(false);
  const [developmentMode,setDevelopmentMode]=useState(false);
  const [page, setPage] = useState('overview');
  const [sidebarCollapsed,setSidebarCollapsed]=useState(()=>{
    try {
      const saved=localStorage.getItem('agentscopeSidebarCollapsed');
      return saved===null ? window.matchMedia('(max-width:650px)').matches : saved==='true';
    } catch { return false; }
  });
  useEffect(()=>{try{localStorage.setItem('agentscopeSidebarCollapsed',String(sidebarCollapsed));}catch{}},[sidebarCollapsed]);
  const [historyModuleIndex,setHistoryModuleIndex]=useState(0);
  const [status, setStatus] = useState(null);
  const [dash, setDash] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [strategyQuery, setStrategyQuery] = useState('');
  const [strategyStatus, setStrategyStatus] = useState('');
  const [tasks, setTasks] = useState([]);
  const [selected, setSelected] = useState('');
  const [context, setContext] = useState(null);
  const [versions, setVersions] = useState([]);
  const [runtime, setRuntime] = useState(null);
  const [requests, setRequests] = useState([]);
  const [governance, setGovernance] = useState([]);
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState(false);

  const notify = useCallback(message => { setToast(message); setTimeout(() => setToast(''), 4200); }, []);
  const connect = async event => {
    event.preventDefault();
    sessionStorage.setItem('agentscopeAdminToken',loginToken.trim());
    try {
      await api('/api/auth/check');
      setAuthenticated(true); setLoginError('');
    } catch (e) {
      sessionStorage.removeItem('agentscopeAdminToken'); setLoginError(e.message || '管理员口令无效');
    }
  };
  const lock = () => { sessionStorage.removeItem('agentscopeAdminToken'); setAuthenticated(false); };
  const refresh = useCallback(async () => {
    if (!authenticated) return;
    try {
      const [s, d, t, g] = await Promise.all([
        api('/api/status'), api('/api/dashboard'), api('/api/tasks'), api('/api/governance'),
      ]);
      setStatus(s); setDash(d); setTasks(t); setGovernance(g);
      if (selected) {
        const [c, v, r, q] = await Promise.all([
          api(`/api/tasks/${selected}/context`), api(`/api/tasks/${selected}/versions`),
          api(`/api/tasks/${selected}/runtime`), api(`/api/tasks/${selected}/scope-requests`),
        ]);
        setContext(c); setVersions(v); setRuntime(r); setRequests(q);
      }
    } catch (e) { notify(e.message); }
  }, [selected, notify, authenticated]);

  useEffect(() => {
    let active=true;
    (async()=>{
      try {
        const response=await fetch('/api/auth/mode');
        if (!response.ok) throw new Error(`连接失败 (${response.status})`);
        const mode=await response.json();
        if (!active) return;
        if (mode.development_no_password) {
          sessionStorage.removeItem('agentscopeAdminToken');
          setLoginToken('');setDevelopmentMode(true);setAuthenticated(true);
        } else {
          const saved=sessionStorage.getItem('agentscopeAdminToken') || '';
          if (saved) {
            try {await api('/api/auth/check');if(active)setAuthenticated(true);}
            catch {sessionStorage.removeItem('agentscopeAdminToken');}
          }
        }
        if(active)setAuthReady(true);
      } catch(error) {if(active)setLoginError(`本地服务未连接：${error.message}`);}
    })();
    return ()=>{active=false;};
  }, []);
  useEffect(() => { if (!authenticated) return; refresh(); const timer = setInterval(refresh, 7000); return () => clearInterval(timer); }, [authenticated, refresh]);
  useEffect(() => {
    if (!authenticated) return;
    api(`/api/strategies?q=${encodeURIComponent(strategyQuery)}&limit=200${strategyStatus ? `&status=${strategyStatus}` : ''}`)
      .then(setStrategies).catch(() => {});
  }, [strategyQuery, strategyStatus, authenticated]);

  const withBusy = async fn => {
    setBusy(true);
    try { await fn(); await refresh(); }
    catch (e) { notify(e.message); }
    finally { setBusy(false); }
  };
  const selectTask = id => { setSelected(id); setPage('task'); };

  if (!authReady) return <div className="auth-gate"><div className="auth-card"><div className="brand-mark">A</div><h1>正在连接 AgentScope</h1>{loginError ? <><p>{loginError}</p><button className="button primary full" onClick={()=>window.location.reload()}>重新连接</button></> : <p>正在加载本地工作区…</p>}</div></div>;

  if (!authenticated) return <div className="auth-gate"><form className="auth-card" onSubmit={connect}><div className="brand-mark">A</div><p className="eyebrow">本地策略管控</p><h1>连接 AgentScope</h1><p>输入虚拟机本地配置的管理员口令。任务级 DSH 凭据不能执行审批操作。</p><label>管理员口令<input autoFocus type="password" value={loginToken} onChange={event=>setLoginToken(event.target.value)} placeholder="AGENTSCOPE_ADMIN_TOKEN" /></label>{loginError&&<div className="inline-notice warning">{loginError}</div>}<button className="button primary full" disabled={!loginToken.trim()}>解锁管控台</button></form></div>;

  return <div className={`shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
    <aside className="sidebar">
      <div className="sidebar-header"><div className="brand"><div className="brand-mark">A</div><div className="brand-copy"><b>AgentScope</b><small>策略管控台</small></div></div><button className="sidebar-toggle" aria-label={sidebarCollapsed?'展开侧栏':'收起侧栏'} title={sidebarCollapsed?'展开侧栏':'收起侧栏'} aria-expanded={!sidebarCollapsed} aria-controls="workspace-navigation" onClick={()=>setSidebarCollapsed(value=>!value)}><span aria-hidden="true">{sidebarCollapsed?'›':'‹'}</span></button></div>
      <div className="side-label">工作区</div>
      <nav id="workspace-navigation" aria-label="工作区导航">
        <NavItem active={page === 'overview'} icon="▦" label="总览" onClick={() => setPage('overview')} />
        <NavItem active={page === 'strategies'} icon="▤" label="历史策略库" count={dash?.stats?.pending_strategies} onClick={() => setPage('strategies')} />
        <NavItem active={page === 'task'} icon="◈" label="任务与启动审核" onClick={() => setPage('task')} />
        <NavItem active={page === 'runtime'} icon="⌁" label="运行时 Scope" onClick={() => setPage('runtime')} />
        <NavItem active={page === 'governance'} icon="⟳" label="持久治理" count={dash?.stats?.pending_governance} onClick={() => setPage('governance')} />
      </nav>
      <div className="side-foot" title={`Linux VM · ${status?.architecture || '连接中'} · ActPlane 执行后端`}><span className={`pulse ${status?.bpf_lsm ? 'ok' : 'bad'}`} /><span className="side-foot-copy">Linux VM · {status?.architecture || '连接中'}<br/><span className="muted">ActPlane 执行后端</span></span></div>
    </aside>
    <main className="main">
      <header className="topbar"><div><span className="crumb">AgentScope</span><span className="slash">/</span><b>{pageTitle(page)}</b></div><div className="top-right"><span className={`status-pill ${status?.broker?.available && status?.bpf_lsm ? 'good' : 'warn'}`}><i />{status?.broker?.available && status?.bpf_lsm ? '执行面已连接' : '执行面待检查'}</span>{developmentMode ? <span className="status-pill good">本地开发 · 免口令</span> : <button className="avatar" title="锁定管控台" onClick={lock}>锁</button>}</div></header>
      {page === 'overview' && <Overview dash={dash} status={status} tasks={tasks} onSelect={selectTask} onNav={setPage} />}
      {page === 'strategies' && <HistoryLibrary moduleIndex={historyModuleIndex} modules={HISTORY_MODULES} onModuleChange={setHistoryModuleIndex} api={api} post={post} tasks={tasks} busy={busy} action={withBusy} notify={notify} selectTask={selectTask} />}
      {page === 'task' && <TaskPage tasks={tasks} selected={selected} selectTask={selectTask} context={context} versions={versions} busy={busy} action={withBusy} notify={notify} refresh={refresh} />}
      {page === 'runtime' && <RuntimePage tasks={tasks} selected={selected} selectTask={selectTask} runtime={runtime} requests={requests} busy={busy} action={withBusy} refresh={refresh} notify={notify} />}
      {page === 'governance' && <Governance rows={governance} busy={busy} action={withBusy} notify={notify} />}
    </main>
    {toast && <div className="toast">{toast}</div>}
  </div>;
}

function pageTitle(page) { return ({ overview: '总览', strategies: '历史策略库', task: '任务与启动审核', runtime: '运行时 Scope', governance: '持久治理' })[page]; }
function NavItem({ active, icon, label, count, onClick }) { return <button className={`nav-item ${active ? 'active' : ''}`} aria-label={label} aria-current={active?'page':undefined} title={label} onClick={onClick}><span className="nav-icon" aria-hidden="true">{icon}</span><span className="nav-label">{label}</span>{count > 0 && <em>{count}</em>}</button>; }
function Header({ eyebrow, title, description, action }) { return <div className="page-head"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>; }
function Metric({ label, value, note, icon }) { return <div className="metric"><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><strong>{value ?? '—'}</strong><small>{note}</small></div>; }
function StatusTag({ children, kind = 'neutral' }) { return <span className={`tag ${kind}`}>{children}</span>; }
function stateTag(value) { const map = { approved: ['已审核', 'good'], pending_review: ['待审核', 'warn'], rejected: ['已拒绝', 'bad'], compiled: ['已编译', 'good'], partial: ['部分支持', 'warn'], loaded: ['已加载', 'good'], running: ['运行中', 'good'], stopped: ['已停止', 'neutral'], completed: ['已完成', 'good'], prepared: ['待生成策略', 'neutral'], policy_review: ['待策略审核', 'warn'], failed: ['失败', 'bad'] }; const [label,kind] = map[value] || [value || '未知','neutral']; return <StatusTag kind={kind}>{label}</StatusTag>; }

function Overview({ dash, status, tasks, onSelect, onNav }) {
  return <div className="content"><Header eyebrow="系统概览" title="策略运行总览" description="从历史策略、任务启动策略到运行时 Scope，集中查看 Agent 的策略版本与执行状态。" action={<button className="button primary" onClick={() => onNav('task')}>＋ 创建任务</button>} />
    <section className="metric-grid"><Metric label="历史策略" value={dash?.stats?.strategies ?? 0} note={`${dash?.stats?.pending_strategies ?? 0} 条待人工审核`} icon="▤"/><Metric label="任务总数" value={dash?.stats?.tasks ?? 0} note={`${dash?.stats?.active_tasks ?? 0} 个正在运行`} icon="◈"/><Metric label="治理候选" value={dash?.stats?.pending_governance ?? 0} note="批准后才进入后续检索" icon="⟳"/><Metric label="内核执行" value={status?.bpf_lsm ? 'BPF-LSM' : '待检查'} note={status?.kernel || 'Linux 内核'} icon="⌁"/></section>
    <div className="grid-two overview-grid">
      <section className="panel"><div className="panel-head"><div><h2>执行环境</h2><p>AgentScope 服务运行于 Lima Linux 虚拟机</p></div><StatusTag kind={status?.broker?.available && status?.bpf_lsm ? 'good' : 'warn'}>{status?.broker?.available && status?.bpf_lsm ? '可用' : '检查中'}</StatusTag></div>
        <div className="env-list"><EnvRow label="Linux 内核" value={`${status?.kernel || '检测中'} · ${status?.architecture || ''}`} ok={!!status?.kernel}/><EnvRow label="BPF-LSM" value={status?.lsm || '检测中'} ok={!!status?.bpf_lsm}/><EnvRow label="ActPlane CLI" value={status?.actplane_cli ? '已安装' : '未安装'} ok={!!status?.actplane_cli}/><EnvRow label="DSH CLI" value={status?.dsh_cli ? '已安装' : '未安装'} ok={!!status?.dsh_cli}/><EnvRow label="特权代理" value={status?.broker?.available ? '已连接' : status?.broker?.error || '未连接'} ok={!!status?.broker?.available}/></div>
        {!status?.bpf_lsm && <div className="inline-notice warning">当前环境未报告 BPF-LSM；此状态下策略不能标记为“内核已执行”。</div>}
      </section>
      <section className="panel"><div className="panel-head"><div><h2>三层策略流</h2><p>历史证据提供候选，审核决定何时生效</p></div></div><div className="layer-flow"><Layer n="01" title="历史语料" text="GitHub 固定 commit · 来源可追溯"/><span className="flow-down">↓</span><Layer n="02" title="任务启动前" text="仓库证据 + Agent 约束 + 历史候选"/><span className="flow-down">↓</span><Layer n="03" title="运行时与持久治理" text="Scope Delta · 审核 · 版本化更新"/></div></section>
    </div>
    <section className="panel table-panel"><div className="panel-head"><div><h2>最近任务</h2><p>任务工作区始终绑定 GitHub 固定 commit</p></div><button className="button ghost" onClick={() => onNav('task')}>查看全部 →</button></div><TaskTable tasks={tasks.slice(0,6)} onSelect={onSelect}/></section>
  </div>;
}
function EnvRow({ label, value, ok }) { return <div className="env-row"><span><i className={ok ? 'dot good' : 'dot warn'} />{label}</span><b>{value}</b></div>; }
function Layer({ n, title, text }) { return <div className="layer-card"><span>{n}</span><div><b>{title}</b><small>{text}</small></div><i>›</i></div>; }

function TaskTable({ tasks, onSelect }) { return <div className="table-scroll"><table><thead><tr><th>任务</th><th>仓库</th><th>Commit</th><th>状态</th><th>更新时间</th><th></th></tr></thead><tbody>{tasks.map(t => <tr key={t.id} onClick={() => onSelect(t.id)} className="click-row"><td><b>{t.name}</b><small>{short(t.id,16)}</small></td><td>{t.repo}</td><td><code>{short(t.commit_sha,12)}</code></td><td>{stateTag(t.status)}</td><td>{when(t.updated_at)}</td><td>→</td></tr>)}{tasks.length === 0 && <EmptyRow cols={6} text="还没有任务，准备一个 GitHub 仓库开始。"/>}</tbody></table></div>; }
function EmptyRow({ cols, text }) { return <tr><td colSpan={cols} className="empty-row">{text}</td></tr>; }

function TaskPage({ tasks, selected, selectTask, context, versions, busy, action, notify, refresh }) {
  const [repoUrl,setRepoUrl] = useState('https://github.com/'); const [ref,setRef] = useState('main'); const [prompt,setPrompt] = useState('');
  const [picked,setPicked] = useState([]); const [settings,setSettings] = useState({read_only:false,deny_network:false,allow_task_output:false}); const [bundle,setBundle] = useState(null);
  const current = tasks.find(t => t.id === selected); const isBootstrap = ['safety-delete-config','safety-impossible-tests','safety-abusive-apology'].includes(current?.name); const recs = context?.history_recommendations || [];
  useEffect(()=>{setSettings({read_only:false,deny_network:false,allow_task_output:false,...(current?.settings||{})});setBundle(null);},[selected]);
  const prepare = () => action(async () => { const data=await post('/api/tasks/prepare',{repo_url:repoUrl,ref,prompt}); selectTask(data.id); notify(`仓库已固定到 ${data.commit_sha.slice(0,12)}，已采集 ${data.evidence_count} 条项目证据`); });
  const generate = () => action(async () => { const b=await post(`/api/tasks/${selected}/policy`,{strategy_ids:picked,settings,artifact_version_ids:(versions[0]?.policy_ir?.selected_dsl_artifacts||[]).map(a=>a.id)}); setBundle(b); notify(`策略 v${b.version} 已生成；编译状态：${b.compile_state}`); });
  const reviewPolicy = decision => action(async () => { const reviewed=bundle || versions[0]; const v=reviewed?.version; if (!v) throw new Error('没有可审核的策略版本'); const binding=reviewed.policy_ir?.bootstrap; await post(`/api/tasks/${selected}/versions/${v}/approve`,{decision,reviewed_by:'研究者',notes:'',expected_context_hash:binding?.context_hash,expected_proposal_hash:binding?.proposal_hash}); notify(decision==='approve'?'启动策略已批准':'策略已拒绝'); });
  const launch = () => action(async () => { const r=await post(`/api/tasks/${selected}/launch`); notify(`ActPlane 已加载，DSH child domain ${r.domain_id} 已启动`); setBundle(null); });
  const stop = () => action(async () => { await post(`/api/tasks/${selected}/stop`); notify('任务已停止'); });
  const topVersion = versions[0]; const shownBundle = bundle || topVersion;
  return <div className="content"><Header eyebrow="第二层 · 任务启动前" title="任务与启动审核" description="从 GitHub 拉取并锁定 commit，读取项目文档与 Agent 指令，再选择相关历史策略生成可审核的策略包。" action={current ? <button className="button ghost" onClick={() => selectTask('')}>＋ 新任务</button> : null} />
    <BootstrapPanel task={current} api={api} post={post} action={action} busy={busy} selectTask={selectTask} refresh={refresh}/>
    {!current ? <div className="grid-two task-start-grid"><section className="panel form-panel"><div className="panel-head"><div><h2>准备 GitHub 任务</h2><p>只接受公开 GitHub 仓库；任务固定到选定分支或 tag 的实际 commit。</p></div><span className="step-num">01</span></div><label>GitHub 仓库地址<input value={repoUrl} onChange={e=>setRepoUrl(e.target.value)} placeholder="https://github.com/owner/repo"/></label><label>分支 / Tag<input value={ref} onChange={e=>setRef(e.target.value)}/></label><label>任务提示词<textarea rows="6" value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="描述 Agent 在该仓库中要完成的工作"/></label><button className="button primary full" disabled={busy || prompt.trim().length<3} onClick={prepare}>拉取仓库并收集证据 →</button></section>
      <section className="panel"><div className="panel-head"><div><h2>已准备任务</h2><p>继续配置策略，或查看已创建任务。</p></div></div>{tasks.length?<TaskTable tasks={tasks} onSelect={selectTask}/>:<div className="empty-box">仓库、Agent 指令和项目文档会在创建后登记到任务证据。</div>}</section></div> : <>
      <div className="task-summary panel"><div><span className="eyebrow">当前任务</span><h2>{current.name}</h2><p>{current.prompt}</p></div><div className="summary-badges">{stateTag(current.status)}<StatusTag>{current.agent.toUpperCase()}</StatusTag></div><div className="commit-line"><span>固定 Commit</span><code>{current.commit_sha}</code><a href={`https://github.com/${current.repo}/tree/${current.commit_sha}`} target="_blank" rel="noreferrer">GitHub ↗</a></div></div>
      {!isBootstrap && <div className="grid-two"><section className="panel"><div className="panel-head"><div><h2>项目上下文证据</h2><p>README、AGENTS.md、CLAUDE.md、SECURITY/CONTRIBUTING 与 GitHub workflow 摘录</p></div><StatusTag>{context?.evidence?.length || 0} 条</StatusTag></div><div className="evidence-list">{context?.evidence?.slice(0,18).map(ev=><article className="evidence" key={ev.id}><div><b>{ev.file_path || ev.title}</b><span>{ev.kind} · L{ev.line_start}</span></div><p>{ev.excerpt}</p></article>)}{!context?.evidence?.length&&<div className="empty-box">正在加载或仓库没有匹配的项目文档。</div>}</div></section>
        <section className="panel"><div className="panel-head"><div><h2>历史策略候选</h2><p>依据任务提示词与项目证据排序；仅勾选且已审核策略会进入生成请求。</p></div><StatusTag>{recs.length} 条匹配</StatusTag></div><div className="recommend-list">{recs.map(r=><label className={`recommend ${r.eligible_for_policy?'':'disabled'}`} key={r.id}><input type="checkbox" disabled={!r.eligible_for_policy} checked={picked.includes(r.id)} onChange={e=>setPicked(e.target.checked?[...picked,r.id]:picked.filter(id=>id!==r.id))}/><div><p>{r.text}</p><small>{r.source_repo || '治理来源'} · {r.category} · {r.context_scope} {r.eligible_for_policy?'':'· 尚未审核，不进入策略'}</small></div><span className="score">{r.relevance}</span></label>)}{!recs.length&&<div className="empty-box">当前任务没有匹配历史策略，可只使用基础策略与目标仓库证据。</div>}</div></section></div>}
      <section className="panel policy-builder"><div className="panel-head"><div><h2>生成与审核启动策略</h2><p>策略版本绑定固定任务、证据与批准内容；Pi 场景通过上方候选入口构建和审核，批准后受管启动。</p></div><span className="step-num">02</span></div>{!isBootstrap && <><div className="settings-row"><Toggle label="仓库只读" desc="禁止任务写入文件" checked={settings.read_only} onChange={v=>setSettings({...settings,read_only:v})}/><Toggle label="禁止网络连接" desc="阻断 Agent 发起的外连" checked={settings.deny_network} onChange={v=>setSettings({...settings,deny_network:v})}/><Toggle label="允许受控输出目录" desc="新增仓库外的专用输出写权限" checked={settings.allow_task_output} onChange={v=>setSettings({...settings,allow_task_output:v})}/></div><div className="button-row"><button className="button primary" disabled={busy} onClick={generate}>生成策略 DSL / PolicyBundle</button>{shownBundle && <><button className="button success" disabled={busy || shownBundle.compile_state !== 'compiled'} onClick={()=>reviewPolicy('approve')}>审核并批准 v{shownBundle.version}</button><button className="button ghost" disabled={busy} onClick={()=>reviewPolicy('reject')}>拒绝</button></>}</div></>}
        {shownBundle&&<div className="bundle-preview"><div className="bundle-head"><div><b>策略版本 v{shownBundle.version}</b><span> · {stateTag(shownBundle.status)} · {stateTag(shownBundle.compile_state)}</span></div>{(current.status==='approved'||(current.status==='failed'&&!current.active_pid))?<button className="button primary" disabled={busy} onClick={launch}>{current.status==='failed'?'重试批准版本的加载':'ActPlane 受管启动 DSH →'}</button>:current.status==='running'?<button className="button danger" disabled={busy} onClick={stop}>停止任务</button>:null}</div><pre>{shownBundle.dsl_text}</pre>{shownBundle.diagnostic&&<div className="inline-notice warning">{shownBundle.diagnostic}</div>}{shownBundle.policy_ir&&!isBootstrap&&<details><summary>PolicyIR：历史策略、任务证据与适用边界</summary><div className="inline-notice">仓库：{shownBundle.policy_ir.task?.repository} · 固定 commit：<code>{shownBundle.policy_ir.task?.fixed_commit}</code><br/>历史策略作为经审核的 DSH 行为参考；内核只执行上方 DSL 中已编译且获批的访问控制规则。冲突需人工结合任务上下文审核。</div><h4>已选历史策略（{shownBundle.policy_ir.selected_history?.length||0}）</h4>{shownBundle.policy_ir.selected_history?.map(s=><article className="evidence" key={s.id}><div><b>{s.category} · {s.context_scope}</b><span>{s.source_repo||'历史语料'} · {s.kernel_enforcement}</span></div><p>{s.text}</p>{s.raw_url&&<a className="source-link" href={s.raw_url} target="_blank" rel="noreferrer">查看固定 commit 来源 ↗</a>}</article>)}{!shownBundle.policy_ir.selected_history?.length&&<p className="field-note">当前版本未选择自然语言提示参考。</p>}<h4>已选历史 DSL（{shownBundle.policy_ir.selected_dsl_artifacts?.length||0}）</h4>{shownBundle.policy_ir.selected_dsl_artifacts?.map(a=><article className="evidence" key={a.id}><div><b>{a.text}</b><span>产物 v{a.version} · {short(a.id,12)}</span></div><p>{a.origin.path} · {short(a.origin.commit,12)} · {a.kernel_enforcement}</p></article>)}<h4>保留的运行时限制（{shownBundle.policy_ir.runtime_restrictions?.length||0}）</h4>{shownBundle.policy_ir.runtime_restrictions?.map(r=><article className="evidence" key={r.request_id}><div><b>{r.path}</b><span>审批人：{r.approved_by} · 已并入新策略版本</span></div><p>{r.justification}</p></article>)}{!shownBundle.policy_ir.runtime_restrictions?.length&&<p className="field-note">这是启动策略版本，或当前没有已批准的运行时限制。</p>}<h4>目标仓库证据（{shownBundle.policy_ir.evidence?.length||0}）</h4><div className="evidence-list">{shownBundle.policy_ir.evidence?.slice(0,24).map(e=><article className="evidence" key={e.id}><div><b>{e.file_path||e.title}</b><span>{e.kind} · L{e.line_start}{e.line_end&&e.line_end!==e.line_start?`–${e.line_end}`:''}</span></div>{e.uri&&<a className="source-link" href={e.uri} target="_blank" rel="noreferrer">查看来源 ↗</a>}</article>)}</div><p className="field-note">自动冲突消解：未启用；请结合来源与适用范围人工复核。</p></details>}<details><summary>PolicyBundle / 编译诊断</summary><pre>{shownBundle.policy_yaml || JSON.stringify(shownBundle.compile_json || {},null,2)}</pre></details></div>}
      </section>
      <section className="panel"><div className="panel-head"><div><h2>策略版本历史</h2><p>每次重新生成或审批后的 Scope 变更都保留版本与审核人。</p></div></div><div className="version-list">{versions.map(v=><div className="version-row" key={v.id}><b>v{v.version}</b><span>{v.layer}</span><span>{v.change_summary}</span><span>{stateTag(v.status)}</span><small>{when(v.created_at)} {v.approved_by?`· ${v.approved_by} 已批准`:''}</small></div>)}</div></section>
    </>}
  </div>;
}
function Toggle({ label, desc, checked, onChange }) { return <label className="toggle-card"><div><b>{label}</b><small>{desc}</small></div><button type="button" role="switch" aria-checked={checked} className={`switch ${checked?'on':''}`} onClick={()=>onChange(!checked)}><i/></button></label>; }

function RuntimePage({ tasks, selected, selectTask, runtime, requests, busy, action, refresh, notify }) {
  const [kind,setKind]=useState('restrict'); const [path,setPath]=useState(''); const [reason,setReason]=useState(''); const task=tasks.find(t=>t.id===selected);
  const submit=()=>action(async()=>{await post(`/api/tasks/${selected}/scope-requests`,{kind,path:path||null,justification:reason,requested_by:'用户'});setReason('');notify('Scope 申请已提交，需审核后执行');});
  const review=(id,decision)=>action(async()=>{const r=await post(`/api/tasks/${selected}/scope-requests/${id}/review`,{decision,reviewed_by:'研究者',notes:''});notify(r.status==='approved'?(r.result?.status==='delta_applied'?'限制 Delta 已在当前任务域中生效':'扩权已审核，旧进程已停止并按新版本重启'):'Scope 申请已拒绝');await refresh();});
  return <div className="content"><Header eyebrow="第三层 · 运行时 Scope" title="运行事件与权限范围" description="只允许当前任务追加收紧 Delta；扩大权限必须单独审批，并由 ActPlane 停止旧进程、绑定新策略版本后重启。" action={<select className="task-select" value={selected} onChange={e=>selectTask(e.target.value)}><option value="">选择一个任务</option>{tasks.map(t=><option value={t.id} key={t.id}>{t.repo} · {t.status}</option>)}</select>} />
    {!task?<div className="panel empty-box">请先选择一项任务查看运行状态与 Scope 变更记录。</div>:<>
      <div className="runtime-banner panel"><div className="runtime-symbol">⌁</div><div><small>ActPlane 运行时状态</small><b>{runtime?.runtime?.agent_status==='exited'?'DSH 会话已结束':runtime?.runtime?.status==='running'?'受管进程域运行中':task.status==='running'?'运行状态待同步':'任务未运行'}</b><span>{task.repo} @ {short(task.commit_sha,12)} · domain {runtime?.runtime?.domain_id || task.active_domain_id || '—'}</span></div><button className="button ghost" onClick={refresh}>刷新事件</button></div>
      <div className="grid-two runtime-grid"><section className="panel"><div className="panel-head"><div><h2>申请更新 Scope</h2><p>所有变更均先进入审批队列，保存理由和操作人。</p></div></div><div className="segmented"><button className={kind==='restrict'?'sel':''} onClick={()=>setKind('restrict')}>追加限制</button><button className={kind==='expand'?'sel':''} onClick={()=>setKind('expand')}>申请扩权</button></div>{kind==='restrict'?<label>限制后允许写入的仓库路径<input value={path} onChange={e=>setPath(e.target.value)} placeholder={`${task.workspace}/src`} /><small>新规则会拒绝该路径之外的写入；路径必须位于当前仓库工作区内。</small></label>:<div className="inline-notice warning">扩权仅提供受控任务输出目录写入能力；批准后旧 DSH 进程将停止，再使用新版本策略在同一仓库工作区启动。</div>}<label>变更理由<textarea rows="3" value={reason} onChange={e=>setReason(e.target.value)} placeholder="说明为何需要这项 Scope 变更"/></label><button className="button primary" disabled={busy||task.status!=='running'||reason.trim().length<4||(kind==='restrict'&&!path.trim())} onClick={submit}>提交审批</button>{task.status!=='running'&&<small className="field-note">只有运行中的任务能提交运行时 Scope 变更。</small>}</section>
        <section className="panel"><div className="panel-head"><div><h2>待审核申请</h2><p>拒绝或批准；批准扩权会记录新版本和新进程域。</p></div><StatusTag kind={requests.some(r=>r.status==='pending_review')?'warn':'neutral'}>{requests.filter(r=>r.status==='pending_review').length} 待处理</StatusTag></div><div className="request-list">{requests.map(r=><article className="request-card" key={r.id}><div className="request-top"><b>{r.kind==='restrict'?'追加限制':'申请扩权'}</b>{stateTag(r.status)}</div><p>{r.requested_change}</p>{r.path&&<code>{r.path}</code>}<blockquote>{r.justification}</blockquote><small>{r.requested_by} · {when(r.created_at)}</small>{r.status==='pending_review'&&<div className="actions"><button className="button tiny primary" disabled={busy} onClick={()=>review(r.id,'approve')}>批准并执行</button><button className="button tiny ghost" disabled={busy} onClick={()=>review(r.id,'reject')}>拒绝</button></div>}{r.result_json&&<details><summary>执行结果</summary><pre>{typeof r.result_json==='string'?r.result_json:JSON.stringify(r.result_json,null,2)}</pre></details>}</article>)}{requests.length===0&&<div className="empty-box">暂无 Scope 申请记录。</div>}</div></section></div>
      <section className="panel"><div className="panel-head"><div><h2>内核事件与命中原因</h2><p>来源为 ActPlane 运行目录的事件日志；显示已观察到的执行结果。</p></div><StatusTag>{runtime?.events?.length||0} 条</StatusTag></div><div className="table-scroll"><table><thead><tr><th>时间</th><th>事件 / 操作</th><th>对象</th><th>判定</th><th>命中原因</th></tr></thead><tbody>{(runtime?.events||[]).map(ev=><tr key={ev.id}><td>{when(ev.occurred_at)}</td><td>{ev.kind}<small>{ev.operation||'—'}</small></td><td className="break-cell">{ev.target||'—'}</td><td>{ev.decision||'—'}</td><td>{ev.reason}</td></tr>)}{!runtime?.events?.length&&<EmptyRow cols={5} text="当前没有已采集的 ActPlane 策略命中事件。"/>}</tbody></table></div></section>
    </>}
  </div>;
}

function Governance({ rows, busy, action, notify }) {
  const [title,setTitle]=useState('');const [kind,setKind]=useState('memory_diff');const [content,setContent]=useState('');const [source,setSource]=useState('');
  const submit=()=>action(async()=>{await post('/api/governance',{kind,title,content,source_url:source||null});setTitle('');setContent('');setSource('');notify('持久治理候选已进入审核队列；审核通过后才会加入历史策略库');});
  const review=(id,decision)=>action(async()=>{await post(`/api/governance/${id}/review`,{decision,reviewed_by:'研究者'});notify(decision==='approve'?'候选已审核并提升为后续策略':'候选已拒绝');});
  return <div className="content"><Header eyebrow="第三层 · 跨任务持久更新" title="持久治理候选" description="memory.md 差异、Agent 规则维护和治理 PR 先进入隔离候选区；只有审核批准的版本会成为后续任务可检索策略。" />
    <div className="grid-two governance-grid"><section className="panel form-panel"><div className="panel-head"><div><h2>登记候选更新</h2><p>支持记忆差异、GitHub 治理 PR 和人工补充策略。</p></div></div><label>候选类型<select value={kind} onChange={e=>setKind(e.target.value)}><option value="memory_diff">memory.md 差异</option><option value="github_pr">Agent 规则治理 PR</option><option value="manual">人工新增策略</option></select></label><label>标题<input value={title} onChange={e=>setTitle(e.target.value)} placeholder="概括这条候选更新" /></label><label>内容<textarea rows="8" value={content} onChange={e=>setContent(e.target.value)} placeholder="填写新增或修改的规则内容；此处只是待审候选"/></label><label>来源链接（可选）<input value={source} onChange={e=>setSource(e.target.value)} placeholder="GitHub PR / commit 链接"/></label><button className="button primary full" disabled={busy||title.trim().length<2||content.trim().length<5} onClick={submit}>加入待审核队列</button></section>
      <section className="panel"><div className="panel-head"><div><h2>候选审核队列</h2><p>审核通过的内容会生成一条带来源元数据的历史策略记录。</p></div><StatusTag kind={rows.some(r=>r.status==='pending_review')?'warn':'neutral'}>{rows.filter(r=>r.status==='pending_review').length} 待审核</StatusTag></div><div className="request-list">{rows.map(r=><article className="request-card" key={r.id}><div className="request-top"><b>{r.title}</b>{stateTag(r.status)}</div><small>{r.kind} · {when(r.created_at)}</small><p className="candidate-content">{r.content}</p>{r.source_url&&<a className="source-link" href={r.source_url} target="_blank" rel="noreferrer">查看来源 ↗</a>}{r.status==='pending_review'&&<div className="actions"><button className="button tiny primary" disabled={busy} onClick={()=>review(r.id,'approve')}>审核通过并发布</button><button className="button tiny ghost" disabled={busy} onClick={()=>review(r.id,'reject')}>拒绝</button></div>}</article>)}{rows.length===0&&<div className="empty-box">暂无候选更新。</div>}</div></section></div>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
