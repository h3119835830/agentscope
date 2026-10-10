import RecordBadge from './RecordBadge.jsx';
import React,{useEffect,useRef,useState} from 'react';
import AgentWorkspaces from './AgentWorkspaces.jsx';
import SecurityConfiguration from './SecurityConfiguration.jsx';
import {tabKeys} from './consoleState.mjs';
import {timeLabel} from './taskPresentation.mjs';
import {agentTypes as types,agentName,processLabel,visibleAgentInstances,canOpen,canStart,entryLabel,entryAction,connectionStatus as status} from './agentInstancePresentation.mjs';
import {openAgentPage} from './openAgentPage.mjs';
import SessionProcesses from './SessionProcesses.jsx';
import './taskConsole.css';
import './connections.css';
import './agentInstances.css';
const endpoint=id=>'/api/agent-instances/'+encodeURIComponent(id);
const eventResult=e=>e.kind==='tool_result'?(e.detail.succeeded?'工具已返回':'工具返回失败'):e.kind==='tool_denied'?e.detail.reason:e.kind==='tool_start'?'允许执行':e.kind==='policy_applied'?'已应用并核验':e.kind==='policy_proposed'?(e.detail.classification==='expand'?'等待用户确认':'校验收紧'):e.kind==='verified'?'实际保护已核验':e.kind==='quiesced'||e.kind==='stopped'?'旧执行进程已终止':e.detail.scope||e.detail.message||'已记录';
function PagedRecords(props){
 const [page,setPage]=useState(1);const total=Math.max(1,Math.ceil(props.rows.length/15));const current=Math.min(page,total);
 return <><Records {...props} rows={props.rows.slice((current-1)*15,current*15)}/>{total>1&&<div className="instance-pagination"><span>第 {current} / {total} 页 · {props.rows.length} 条记录</span><button type="button" className="button tiny ghost" disabled={current===1} onClick={()=>setPage(current-1)}>上一页</button><button type="button" className="button tiny ghost" disabled={current===total} onClick={()=>setPage(current+1)}>下一页</button></div>}</>;
}
const kinds={registered:'登记连接',configured:'修改连接',starting:'启动实例',verified:'保护核验通过',verification_failed:'保护核验失败',start_failed:'启动失败',stopped:'停止实例',policy_proposed:'提出策略变更',gate_closed:'暂停全部会话',quiesced:'终止旧执行进程',policy_applied:'应用共享策略',policy_apply_failed:'策略应用失败',tool_start:'工具执行前检查',tool_result:'工具执行结果',tool_denied:'工具被拒绝'};
function Fields({values}){return <dl className="task-fields">{values.map(([k,v])=><React.Fragment key={k}><dt>{k}</dt><dd>{v??'—'}</dd></React.Fragment>)}</dl>}
function Records({labels,rows,empty='暂无记录'}){return <div className="table-scroll" tabIndex={0}><table className="task-record-table instance-record-table"><thead><tr>{labels.map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={i}>{row.map((value,n)=><td key={n}>{value??'—'}</td>)}</tr>)}{!rows.length&&<tr><td colSpan={labels.length} className="task-empty">{empty}</td></tr>}</tbody></table></div>}
function Drawer({id,api,post,onClose,onChanged,onOpen,initialTab='connection'}){
 const dialog=useRef(null),origin=useRef(document.activeElement),seq=useRef(0),initialized=useRef(false);
 const [revision,setRevision]=useState(0);
 const [tab,setTab]=useState(initialTab),[row,setRow]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(''),[name,setName]=useState(''),[paths,setPaths]=useState(''),[sessions,setSessions]=useState(null),[sessionsError,setSessionsError]=useState(''),[events,setEvents]=useState(null),[eventsError,setEventsError]=useState(''),[proposals,setProposals]=useState([]);
 const tabs=[['connection','连接设置'],['policy','安全配置'],['sessions','会话与进程'],['events','运行记录']];
 async function refresh(){
  const n=++seq.current;
  try{
   const data=await api(endpoint(id));if(n!==seq.current)return;
   setRow(data);setProposals(data.proposals||[]);setError('');
   if(!initialized.current){initialized.current=true;setName(agentName(data));setPaths((data.resources||[]).join('\n'));}
  }catch(e){if(n===seq.current)setError(e.message);}
 }
 useEffect(()=>{dialog.current?.showModal();refresh();const timer=setInterval(refresh,5000);return()=>{seq.current++;clearInterval(timer);dialog.current?.close();if(origin.current?.isConnected)origin.current.focus({preventScroll:true});};},[id]);
 useEffect(()=>{
  let active=true;setSessions(null);setSessionsError('');if(tab==='events'){setEvents(null);setEventsError('');}
  function load(){
   if(tab==='sessions'&&row){
    if(!row.connected){setSessions({sessions:[],mapping_available:false,disconnected:true});return;}
    api(endpoint(id)+'/sessions').then(s=>{if(active){setSessions(s);setSessionsError('');}}).catch(e=>{if(active){setSessions(null);setSessionsError(e.message);}});
   }
   if(tab==='events')api(endpoint(id)+'/events').then(r=>{if(active){setEvents(r.events||[]);setEventsError('');}}).catch(e=>{if(active)setEventsError(e.message);});
  }
  load();const timer=setInterval(load,5000);
  return()=>{active=false;clearInterval(timer);};
 },[tab,row?.generation,row?.updated_at,row?.connected,row?.pid,row?.status,revision]);
 async function act(label,fn){setBusy(label);setError('');try{const value=await fn();await refresh();setRevision(n=>n+1);onChanged();return {ok:true,value};}catch(e){setError(e.message);return {ok:false};}finally{setBusy('');}}
 const controlled=row?.mode==='controlled'; const pending=proposals.filter(p=>p.state==='pending'&&p.classification==='expand'&&p.generation===row?.generation&&p.base_hash===row?.policy_hash);
 return <dialog ref={dialog} className="record-drawer instance-drawer" aria-label="Agent 实例配置" onCancel={e=>{e.preventDefault();onClose();}}>
 <div className="record-drawer-head"><h2>{row?agentName(row):'读取实例…'}</h2><div className="actions">{row&&(canOpen(row)||canStart(row))&&<button type="button" className="button tiny primary" disabled={!!busy} onClick={()=>act(canStart(row)?'启动并打开 Agent':'打开 Agent',()=>onOpen(row))}>{canStart(row)?'启动并打开 Agent':'打开 Agent'}</button>}<button type="button" className="button tiny ghost" onClick={onClose}>关闭</button></div></div>
 <div className="record-drawer-tabs" role="tablist" aria-label="实例配置内容">{tabs.map(([key,label])=><button type="button" id={'instance-tab-'+key} key={key} role="tab" aria-controls={'instance-pane-'+key} aria-selected={tab===key} tabIndex={tab===key?0:-1} onClick={()=>setTab(key)} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,setTab)}>{label}</button>)}</div>
 <div className="record-drawer-body" role="tabpanel" id={'instance-pane-'+tab} aria-labelledby={'instance-tab-'+tab}>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}{busy&&<p role="status">{busy}…</p>}
 {row&&tab==='connection'&&<>
  <Fields values={[['Agent 类型',types[row.agent_type]||row.agent_type],['入口方式',<RecordBadge tone="purple" dot={false}>{entryLabel(row)}</RecordBadge>],['打开方式',row.entry?.instructions||'尚未接入原生入口'],...(row.entry?.command?[['CLI 启动命令',<code>{row.entry.command}</code>]]:[]),['运行环境',row.environment==='wsl'?'WSL / Ubuntu':row.environment],['连接情况',<RecordBadge>{status(row)}</RecordBadge>],['安全覆盖',<RecordBadge>{row.security}</RecordBadge>],['策略归属',controlled?'当前受控连接的所有工作区、会话与子进程共享':'尚未接管此实例的执行'],['启动来源',controlled?(row.agent_type==='hermes'?'/home/happy/.local/bin/hermes（WSL 独立安装）':'DeepSeek Harness'):(row.source||row.executable||row.runtime?.open_url||'原生观测')]]}/>
  {controlled?<form className="instance-form" onSubmit={e=>{e.preventDefault();act('保存连接设置',()=>api(endpoint(id),{method:'PUT',body:JSON.stringify({name,resources:paths.split('\n').map(p=>p.trim()).filter(Boolean),expected_policy_hash:row.policy_hash})}));}}>
    <label>资源目录<textarea required rows={4} value={paths} onChange={e=>setPaths(e.target.value)} placeholder="每行一个已有项目目录"/></label>
    <p className="field-note">资源目录用于会话映射和文件权限。连接设置在实例停止后修改。</p><div className="actions"><button className="button primary" disabled={!!busy||!['closed','failed'].includes(row.gate)}>保存连接设置</button><button type="button" className="button ghost" disabled={!!busy||row.gate==='closed'} onClick={()=>act('停止实例',()=>post(endpoint(id)+'/stop'))}>停止实例</button></div>
  </form>:<p className="field-note">这是发现的本机实例。新建受控连接后可配置共享策略，原实例继续保持原有运行方式。</p>}
 </>}
 {row&&tab==='policy'&&<>
  <SecurityConfiguration key={id} row={row} pending={pending} busy={!!busy} onPropose={candidate=>act('提交安全配置',()=>post(endpoint(id)+'/policy/proposals',{policy:candidate.policy,generation:candidate.generation,base_hash:candidate.base_hash,request_key:crypto.randomUUID()}))} onConfirm={proposal=>act('确认并应用变更',()=>post(endpoint(id)+'/policy/proposals/'+proposal.id+'/confirm',{proposal_hash:proposal.proposal_hash}))}/></>}
 {row&&tab==='events'&&<div className="security-runtime">{eventsError&&<p role="alert">{eventsError}</p>}<PagedRecords labels={['时间','操作','会话 / 工具','处理结果']} rows={(events||[]).map(e=>[timeLabel(e.created_at),kinds[e.kind]||e.kind,[e.session_id,e.tool].filter(Boolean).join(' / ')||'整个实例',<RecordBadge>{eventResult(e)}</RecordBadge>])} empty={eventsError?'运行记录读取失败':events?'暂无运行记录':'正在读取运行记录…'}/></div>}
 {row&&tab==='sessions'&&<SessionProcesses agentType={row.agent_type} data={sessions} error={sessionsError} onRefresh={()=>setRevision(n=>n+1)}/>}
 </div></dialog>
}
function Add({api,post,onClose,onCreated}){
 const dialog=useRef(null),origin=useRef(document.activeElement);
 const [type,setType]=useState('dsh'),[mode,setMode]=useState('controlled'),[env,setEnv]=useState('wsl'),[url,setUrl]=useState(''),[name,setName]=useState(''),[paths,setPaths]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.focus();};},[]);
 return <dialog ref={dialog} className="record-drawer instance-add" aria-label="添加 Agent 连接" onCancel={e=>{e.preventDefault();onClose();}}><div className="record-drawer-head"><h2>添加连接</h2><button type="button" className="button tiny ghost" onClick={onClose}>关闭</button></div><form className="record-drawer-body instance-form" onSubmit={async e=>{e.preventDefault();setBusy(true);try{const r=await post('/api/agent-instances',{name:type==='other'?name.trim():types[type],agent_type:type,mode,environment:env,open_url:url,resources:paths.split('\n').map(p=>p.trim()).filter(Boolean)});onCreated(r);}catch(e){setError(e.message);}finally{setBusy(false);}}}>
 <label>接入方式<select value={mode} onChange={e=>{setMode(e.target.value);if(e.target.value==='controlled'){setType('dsh');setEnv('wsl');}}}><option value="controlled">受控实例（DeepSeek Harness / WSL Hermes）</option><option value="observed">手动登记其他 Agent 网页入口</option></select></label><label>Agent<select value={type} onChange={e=>setType(e.target.value)}><option value="dsh">DeepSeek Harness</option><option value="hermes">Hermes（WSL 独立安装）</option>{mode==='observed'&&<option value="other">其他 Agent</option>}</select></label>{mode==='observed'&&<><label>运行环境<select value={env} onChange={e=>setEnv(e.target.value)}><option value="wsl">WSL</option><option value="windows">Windows</option></select></label><label>原生网页入口<input required value={url} onChange={e=>setUrl(e.target.value)} placeholder="http://127.0.0.1:端口/"/></label></>}{type==='other'&&<label>Agent 名称<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)}/></label>}<label>资源目录<textarea required={mode==='controlled'} rows={5} value={paths} onChange={e=>setPaths(e.target.value)} placeholder="每行一个已有项目目录，例如 /home/happy/projects/demo"/></label><p className="field-note">{mode==='controlled'?'新实例从只读资源开始。保存后配置权限，再启动；实例全部会话共享策略。':'手动登记仅提供打开入口，不代表已接管执行。受控启动需要对应适配器。'}</p>{error&&<p role="alert" className="inline-notice warning">{error}</p>}<button className="button primary" disabled={busy}>{busy?'正在登记…':'保存连接'}</button></form></dialog>
}
export default function AgentInstances(props){
 const {api,post,notify,active,workspaceSeed}=props;
 const [rows,setRows]=useState([]),[loaded,setLoaded]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(''),[selected,setSelected]=useState(''),[detailTab,setDetailTab]=useState('connection'),[adding,setAdding]=useState(false);
 const seq=useRef(0);
 const visibleRows=visibleAgentInstances(rows);
 function configure(id,tab='connection'){setDetailTab(tab);setSelected(id);}
 async function refresh(){const n=++seq.current;try{const r=await api('/api/agent-instances');if(n===seq.current){setRows(r.instances||[]);setLoaded(true);setError('');}}catch(e){if(n===seq.current){setLoaded(true);setError(e.message);setRows(old=>old.map(r=>({...r,connected:false,active:false,status:'unknown',security:'当前未核验',can_open:false})));}}}
 useEffect(()=>{if(!active)return;refresh();const t=setInterval(refresh,5000);return()=>{seq.current++;clearInterval(t);};},[active,api]);
 async function act(id,label,fn){setBusy(id);try{await fn();await refresh();}catch(e){notify(e.message);setError(e.message);}finally{setBusy('');}}
 const open=(row,start)=>openAgentPage({id:row.id,start,post});
 const openInstance=row=>{const action=entryAction(row).action;if(action==='instructions'){configure(row.id);return;}if(action==='processes'){configure(row.id,'sessions');return;}return act(row.id,'打开',()=>open(row,action==='start'));};
 // Old workspace deep links retain their existing read-only association view.
 if(workspaceSeed)return <AgentWorkspaces {...props}/>;
 return <div className="content task-console agent-connections agent-instance-console"><h1 className="connection-screen-reader-heading">Agent连接</h1>
 <div className="connection-toolbar"><h2 className="connection-current-title">当前连接</h2><div className="actions"><button type="button" className="button ghost" disabled={!!busy} onClick={()=>act('discover','发现 Agent',async()=>{const r=await post('/api/agent-instances/discover');setRows(r.instances||[]);})}>发现 Agent</button><button type="button" className="button primary" onClick={()=>setAdding(true)}>添加连接</button></div></div>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}
 <Records labels={['Agent','入口方式','当前进程（PID）','运行环境','连接情况','安全覆盖','操作']} rows={visibleRows.map(row=>{return [<span className={"record-agent brand-"+row.agent_type}><span className="record-agent-icon" aria-hidden="true">{agentName(row).slice(0,1)}</span><span><b>{agentName(row)}</b>{visibleRows.filter(r=>r.agent_type===row.agent_type).length>1&&<small>{row.name!==agentName(row)?row.name:row.id}</small>}</span></span>,<RecordBadge tone="purple" dot={false}>{entryLabel(row)}</RecordBadge>,<RecordBadge tone={processLabel(row)==='—'?'neutral':'info'} mono dot={false}>{processLabel(row)}</RecordBadge>,row.environment==='wsl'?'WSL / Ubuntu':row.environment,<RecordBadge>{status(row)}</RecordBadge>,<RecordBadge>{row.security}</RecordBadge>,<div className="actions"><button type="button" className="button tiny ghost" disabled={!!busy} onClick={()=>openInstance(row)}>{busy===row.id?(canStart(row)?'正在启动与核验…':'正在打开…'):entryAction(row).label}</button><button type="button" className="button tiny ghost" onClick={()=>configure(row.id)}>配置</button></div>];})} empty={loaded?(error?"当前观测不可用，请重新检查。":"尚未发现 Agent。点击“发现 Agent”，或添加连接。") :"正在观测本机 Agent…"}/>
 {adding&&active&&<Add api={api} post={post} onClose={()=>setAdding(false)} onCreated={r=>{setAdding(false);configure(r.id);refresh();}}/>}
 {selected&&active&&<Drawer key={selected+detailTab} id={selected} initialTab={detailTab} api={api} post={post} onOpen={row=>open(row,canStart(row))} onChanged={refresh} onClose={()=>setSelected('')}/>}
 </div>
}
