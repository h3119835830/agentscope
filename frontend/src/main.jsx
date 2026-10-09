import SecurityNotice from './SecurityNotice.jsx';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import HistoryLibrary from './HistoryLibrary.jsx';
import TaskHub from './TaskHub.jsx';
import AgentWorkspaces from './AgentInstances.jsx';
import ManagedWorkbench from './ManagedWorkbench.jsx';
import {uniqueTasks,selectableTasks,isTaskEnded} from './consoleState.mjs';
import TaskArchive from './TaskArchive.jsx';
import {navigationTarget, readNavigation} from './navigation.mjs';
import './prototypeTheme.css';
import './recordVisuals.css';
import SecurityNotice from './SecurityNotice.jsx';

const api = async (url, options = {}) => {
  const response = await fetch(url, {...options, credentials:'omit', headers:{'Content-Type':'application/json', ...options.headers}});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `请求失败 (${response.status})`);
  return data;
};
const post = (url, body = {}) => api(url, { method: 'POST', body: JSON.stringify(body) });
const short = (value, n = 12) => value ? `${value.slice(0, n)}…` : '—';
const HISTORY_MODULES = [
  {page:'generate',title:'策略生成',icon:'⌘'},
  {page:'records',title:'策略记录与加载',icon:'⇥'},
  {page:'audit',title:'生成记录与审计',icon:'▦'},
];
const when = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';

function App() {
  const [navigation, setNavigation] = useState(()=>{
    const initial=readNavigation(window.location.href);
    return initial;
  });
  const {page,historyModuleIndex,task:selected}=navigation;
  const navigate=useCallback(patch=>{
    const target=navigationTarget(window.location.href,patch);
    if(target!==window.location.pathname+window.location.search+window.location.hash)
      window.history.pushState(null,'',target);
    setNavigation(readNavigation(window.location.href));
  },[]);
  const setPage=next=>navigate({page:next});
  const setHistoryModuleIndex=index=>navigate({page:'strategies',historyModuleIndex:index});
  useEffect(()=>{
    // Canonicalize the initial selection without creating a second browser-history entry.
    window.history.replaceState(null,'',navigationTarget(window.location.href,navigation));
    const restore=()=>setNavigation(readNavigation(window.location.href));
    window.addEventListener('popstate',restore);
    return()=>window.removeEventListener('popstate',restore);
  },[]);
  const [sidebarCollapsed,setSidebarCollapsed]=useState(()=>{
    try {
      const saved=localStorage.getItem('agentscopeSidebarCollapsed');
      return saved===null ? window.matchMedia('(max-width:650px)').matches : saved==='true';
    } catch { return false; }
  });
  useEffect(()=>{try{localStorage.setItem('agentscopeSidebarCollapsed',String(sidebarCollapsed));}catch{}},[sidebarCollapsed]);
  useEffect(()=>{
    const media=window.matchMedia('(max-width:650px)');
    const compact=()=>{if(media.matches)setSidebarCollapsed(true);};
    compact();media.addEventListener('change',compact);
    return()=>media.removeEventListener('change',compact);
  },[]);
  const [status, setStatus] = useState(null);
  const [dash, setDash] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [strategyQuery, setStrategyQuery] = useState('');
  const [strategyStatus, setStrategyStatus] = useState('');
  const [tasks, setTasks] = useState([]);
  const [workspaceSeed,setWorkspaceSeed]=useState('');
  const [governance, setGovernance] = useState([]);
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState(false);

  const notify = useCallback(message => { setToast(message); setTimeout(() => setToast(''), 4200); }, []);
  const refresh = useCallback(async () => {
    if(page==='history')return;
    try {
      const [s, d, t, g, wt] = await Promise.all([
        api('/api/status'), api('/api/dashboard'), api('/api/tasks'), api('/api/governance'),api('/api/workspace-tasks'),
      ]);
      setStatus(s); setDash(d); setTasks(uniqueTasks([...t,...(wt.records||[])])); setGovernance(g);
    } catch (e) { notify(e.message); }
  }, [selected, page, notify]);
  useEffect(() => { if(page==='history')return; refresh(); const timer = setInterval(refresh, 7000); return () => clearInterval(timer); }, [refresh,page]);
  useEffect(() => {
    if(page==='history')return;
    api(`/api/strategies?q=${encodeURIComponent(strategyQuery)}&limit=200${strategyStatus ? `&status=${strategyStatus}` : ''}`)
      .then(setStrategies).catch(() => {});
  }, [strategyQuery, strategyStatus,page]);

  const withBusy = async fn => {
    setBusy(true);
    try { await fn(); await refresh(); }
    catch (e) { notify(e.message); }
    finally { setBusy(false); }
  };
  const selectTask = id => navigate({task:id,archiveTask:'',workbenchSection:'startup'});
  const openTask = id => navigate({page:'history',archiveTask:id});
  const createTask = (workspace='') => {setWorkspaceSeed(workspace);navigate({page:'workbench',task:'',archiveTask:'',workbenchSection:'startup',workspace});};

  return <div className={`shell prototype-theme ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
    <aside className="sidebar">
      <div className="sidebar-header"><div className="brand"><div className="brand-mark">A</div><div className="brand-copy"><b>AgentScope</b><small>策略管控台</small></div></div><button className="sidebar-toggle" aria-label={sidebarCollapsed?'展开侧栏':'收起侧栏'} title={sidebarCollapsed?'展开侧栏':'收起侧栏'} aria-expanded={!sidebarCollapsed} aria-controls="workspace-navigation" onClick={()=>setSidebarCollapsed(value=>!value)}><span aria-hidden="true">{sidebarCollapsed?'›':'‹'}</span></button></div>
      <div className="side-label">工作区</div>
      <nav id="workspace-navigation" aria-label="工作区导航">
        <NavItem active={page === 'overview'} icon="▦" label="总览" onClick={() => setPage('overview')} />
        <NavItem active={page === 'connections'} icon="⇄" label="Agent连接" onClick={() => setPage('connections')} />
        <NavItem active={page === 'workbench'} icon="◈" label="策略工作台" onClick={() => setPage('workbench')} />
        <NavItem active={page === 'history'} icon="▤" label="任务历史" onClick={() => setPage('history')} />
        <NavItem active={page === 'strategies'} icon="▤" label="历史策略库" count={dash?.stats?.pending_strategies} onClick={() => setPage('strategies')} />
        <NavItem active={page === 'governance'} icon="⟳" label="持久治理" count={dash?.stats?.pending_governance} onClick={() => setPage('governance')} />
      </nav>
      <div className="side-foot" title={`Linux VM · ${status?.architecture || '连接中'} · ActPlane 执行后端`}><span className={`pulse ${status?.bpf_lsm ? 'ok' : 'bad'}`} /><span className="side-foot-copy">Linux VM · {status?.architecture || '连接中'}<br/><span className="muted">ActPlane 执行后端</span></span></div>
    </aside>
    <main className="main" data-page={page}>
      {page!=='connections'&&<header className="topbar"><div><span className="crumb">AgentScope</span><span className="slash">/</span><b>{pageTitle(page)}</b></div><div className="top-right">{page==='history'?<span className="status-pill neutral">历史回放</span>:<span className={`status-pill ${status?.broker?.available && status?.bpf_lsm ? 'good' : 'warn'}`}><i />{status?.broker?.available && status?.bpf_lsm ? '执行后端可用' : '执行后端待检查'}</span>}</div></header>}
      {page === 'overview' && <Overview dash={dash} status={status} tasks={tasks} onSelect={openTask} onCreate={createTask} onNav={setPage} />}
      <div hidden={page!=='workbench'}><div className="content workbench-selector"><label>当前任务<select aria-label="当前工作台任务" value={selected} onChange={e=>selectTask(e.target.value)}><option value="">新建任务</option>{selected&&!selectableTasks(tasks).some(t=>t.id===selected)&&<option value={selected}>{isTaskEnded(tasks.find(t=>t.id===selected))?'历史任务（只读）':'选定任务（查看与恢复）'}</option>}{selectableTasks(tasks).map(t=><option key={t.id} value={t.id}>{t.name||t.id}</option>)}</select></label></div>{page==='workbench'&&(!selected?<TaskHub api={api} post={post} notify={notify} tasks={tasks} task="" onSelectTask={selectTask} onFollowTask={selectTask} onAgents={()=>setPage('connections')} workspaceSeed={navigation.workspace} agentSeed={navigation.agent} onContext={context=>navigate(context)} createOnly/>:<ManagedWorkbench api={api} post={post} notify={notify} task={selected} onSelectTask={selectTask} onCreateTask={createTask} onTaskRecord={()=>navigate({workbenchSection:'startup'})} readOnly={isTaskEnded(tasks.find(t=>t.id===selected))} sourceTask={tasks.find(t=>t.id===selected)} section={navigation.workbenchSection} onSection={workbenchSection=>navigate({workbenchSection})}/>)}</div>
      <div hidden={page!=='history'}><TaskArchive api={api} navigation={navigation} navigate={navigate}/></div>
      {page === 'strategies' && <HistoryLibrary moduleIndex={historyModuleIndex} modules={HISTORY_MODULES} onModuleChange={setHistoryModuleIndex} api={api} post={post} tasks={tasks} busy={busy} action={withBusy} notify={notify} selectTask={openTask} />}
      {page!=='history'&&<div hidden={page!=='connections'}><AgentWorkspaces api={api} post={post} notify={notify} onCreateTask={createTask} onOpenTask={openTask} tasks={tasks} active={page==='connections'} agentSeed={navigation.connectionAgent} workspaceSeed={navigation.connectionWorkspace} pane={navigation.connectionsPane} historySeed={navigation.connectionHistory} onContext={context=>navigate(context)} /></div>}
      {page === 'governance' && <Governance rows={governance} busy={busy} action={withBusy} notify={notify} />}
    </main>
    {toast && <div className="toast">{toast}</div>}
  </div>;
}

function pageTitle(page) { return ({ overview: '总览', workbench:'策略工作台',history:'任务历史',connections:'Agent连接', strategies: '历史策略库', task: '任务与场景策略', 'agent-bridge':'Agent 与工作区', governance: '持久治理' })[page]; }
function NavItem({ active, icon, label, count, onClick }) { return <button className={`nav-item ${active ? 'active' : ''}`} aria-label={label} aria-current={active?'page':undefined} title={label} onClick={onClick}><span className="nav-icon" aria-hidden="true">{icon}</span><span className="nav-label">{label}</span>{count > 0 && <em>{count}</em>}</button>; }
function Header({ eyebrow, title, description, action }) { return <div className="page-head"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>; }
function Metric({ label, value, note, icon }) { return <div className="metric"><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><strong>{value ?? '—'}</strong><small>{note}</small></div>; }
function StatusTag({ children, kind = 'neutral' }) { return <span className={`tag ${kind}`}>{children}</span>; }
function stateTag(value) { const map = { approved: ['已审核', 'good'], pending_review: ['待审核', 'warn'], rejected: ['已拒绝', 'bad'], compiled: ['已编译', 'good'], partial: ['部分支持', 'warn'], loaded: ['已加载', 'good'], running: ['运行中', 'good'], stopped: ['已停止', 'neutral'], completed: ['已完成', 'good'], prepared: ['待生成策略', 'neutral'], policy_review: ['待策略审核', 'warn'], failed: ['失败', 'bad'] }; const [label,kind] = map[value] || [value || '未知','neutral']; return <StatusTag kind={kind}>{label}</StatusTag>; }

function Overview({ dash, status, tasks, onSelect, onCreate, onNav }) {
  return <div className="content"><Header eyebrow="系统概览" title="策略运行总览" description="从历史策略、任务启动策略到运行时 Scope，集中查看 Agent 的策略版本与执行状态。" action={<div className="security-notice-actions"><SecurityNotice /><button className="button primary" onClick={() => onCreate()}>＋ 创建任务</button></div>} />
    <section className="metric-grid"><Metric label="历史策略" value={dash?.stats?.strategies ?? 0} note={`${dash?.stats?.pending_strategies ?? 0} 条待人工审核`} icon="▤"/><Metric label="任务总数" value={dash?.stats?.tasks ?? 0} note={`${dash?.stats?.active_tasks ?? 0} 个正在运行`} icon="◈"/><Metric label="治理候选" value={dash?.stats?.pending_governance ?? 0} note="批准后才进入后续检索" icon="⟳"/><Metric label="内核执行" value={status?.bpf_lsm ? 'BPF-LSM' : '待检查'} note={status?.kernel || 'Linux 内核'} icon="⌁"/></section>
      <section className="panel"><div className="panel-head"><div><h2>执行环境</h2><p>AgentScope 服务运行于 Linux 虚拟机</p></div><StatusTag kind={status?.broker?.available && status?.bpf_lsm ? 'good' : 'warn'}>{status?.broker?.available && status?.bpf_lsm ? '可用' : '检查中'}</StatusTag></div>
        <div className="env-list"><EnvRow label="Linux 内核" value={`${status?.kernel || '检测中'} · ${status?.architecture || ''}`} ok={!!status?.kernel}/><EnvRow label="BPF-LSM" value={status?.lsm || '检测中'} ok={!!status?.bpf_lsm}/><EnvRow label="ActPlane CLI" value={status?.actplane_cli ? '已安装' : '未安装'} ok={!!status?.actplane_cli}/><EnvRow label="DSH CLI" value={status?.dsh_cli ? '已安装' : '未安装'} ok={!!status?.dsh_cli}/><EnvRow label="特权代理" value={status?.broker?.available ? '已连接' : status?.broker?.error || '未连接'} ok={!!status?.broker?.available}/></div>
        {!status?.bpf_lsm && <div className="inline-notice warning">当前环境未报告 BPF-LSM；此状态下策略不能标记为“内核已执行”。</div>}
      </section>
    <section className="panel table-panel"><div className="panel-head"><div><h2>最近任务</h2><p>查看任务的工作区快照、策略与执行记录。</p></div><button className="button ghost" onClick={() => onNav('history')}>查看全部 →</button></div><TaskTable tasks={tasks.slice(0,6)} onSelect={onSelect}/></section>
  </div>;
}
function EnvRow({ label, value, ok }) { return <div className="env-row"><span><i className={ok ? 'dot good' : 'dot warn'} />{label}</span><b>{value}</b></div>; }

function TaskTable({ tasks, onSelect }) { return <div className="table-scroll"><table><thead><tr><th>任务</th><th>仓库</th><th>Commit</th><th>状态</th><th>更新时间</th><th></th></tr></thead><tbody>{tasks.map(t => <tr key={t.id} onClick={() => onSelect(t.id)} className="click-row"><td><b>{t.name}</b><small>{short(t.id,16)}</small></td><td>{t.repo}</td><td><code>{short(t.commit_sha,12)}</code></td><td>{stateTag(t.status)}</td><td>{when(t.updated_at)}</td><td>→</td></tr>)}{tasks.length === 0 && <EmptyRow cols={6} text="还没有任务，准备一个 GitHub 仓库开始。"/>}</tbody></table></div>; }
function EmptyRow({ cols, text }) { return <tr><td colSpan={cols} className="empty-row">{text}</td></tr>; }

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
