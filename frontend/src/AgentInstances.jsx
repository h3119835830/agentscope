import AgentLaunchFields,{launchDefaults} from './AgentLaunchFields.jsx';
import NativeAgentWorkspaces from './NativeAgentWorkspaces.jsx';
import RecordBadge from './RecordBadge.jsx';
import PolicyLifecycleDialog from './PolicyLifecycleDialog.jsx';
import React,{useEffect,useRef,useState} from 'react';
import AgentWorkspaces from './AgentWorkspaces.jsx';
import ProductStatus,{useEvidenceClock} from './ProductStatus.jsx';
import {tabKeys} from './consoleState.mjs';
import {timeLabel} from './taskPresentation.mjs';
import {agentTypes as types,agentName,connectionName,connectionPid,processLabel,visibleAgentInstances,canOpen,canStart,canCheckEntry,entryLabel,entryAction,connectionStatus as status} from './agentInstancePresentation.mjs';
import {openConnection,restartConnection} from './connectionOpen.mjs';
import './taskConsole.css';
import './connections.css';
import './agentInstances.css';
const endpoint=id=>'/api/agent-instances/'+encodeURIComponent(id);
const eventResult=e=>e.kind==='tool_result'?(e.detail.succeeded?'工具已返回':'工具返回失败'):e.kind==='tool_denied'?e.detail.reason:e.kind==='tool_start'?'允许执行':e.kind==='policy_applied'?'已应用并核验':e.kind==='policy_proposed'?(e.detail.classification==='expand'?'等待用户确认':'校验收紧'):e.kind==='verified'?'实际保护已核验':e.kind==='quiesced'||e.kind==='stopped'?'旧执行进程已终止':e.detail.scope||e.detail.message||'已记录';
function PagedRecords(props){
 const [page,setPage]=useState(1);const total=Math.max(1,Math.ceil(props.rows.length/15));const current=Math.min(page,total);
 return <><Records {...props} rows={props.rows.slice((current-1)*15,current*15)}/>{total>1&&<div className="instance-pagination"><span>第 {current} / {total} 页 · {props.rows.length} 条记录</span><button type="button" className="button tiny ghost" disabled={current===1} onClick={()=>setPage(current-1)}>上一页</button><button type="button" className="button tiny ghost" disabled={current===total} onClick={()=>setPage(current+1)}>下一页</button></div>}</>;
}
const kinds={registered:'登记连接',configured:'修改连接',starting:'启动 Agent',verified:'保护核验通过',verification_failed:'保护核验失败',start_failed:'启动失败',stopped:'停止 Agent',policy_proposed:'提出策略变更',gate_closed:'暂停全部会话',quiesced:'终止旧执行进程',policy_applied:'应用共享策略',policy_apply_failed:'策略应用失败',tool_start:'工具执行前检查',tool_result:'工具执行结果',tool_denied:'工具被拒绝'};
function Fields({values}){return <dl className="task-fields">{values.map(([k,v])=><React.Fragment key={k}><dt>{k}</dt><dd>{v??'—'}</dd></React.Fragment>)}</dl>}
export function ConnectionPid({row}){
 const now=useEvidenceClock(row.product_status?.runtime?.expires_at);
 return <>{connectionPid(row,Math.max(now,Date.now()))}</>;
}
function Records({labels,rows,empty='暂无记录'}){if(!rows.length)return <p className="task-empty">{empty}</p>;return <div className="table-scroll" tabIndex={0}><table className="task-record-table instance-record-table"><thead><tr>{labels.map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={i}>{row.map((value,n)=><td key={n}>{value}</td>)}</tr>)}{!rows.length&&<tr><td colSpan={labels.length} className="task-empty">{empty}</td></tr>}</tbody></table></div>}
export function Drawer({id,api,post,onClose,onChanged,onOpen,onSessions,onConfiguration,policyScope,initialTab='connection'}){
 const dialog=useRef(null),origin=useRef(document.activeElement),seq=useRef(0),initialized=useRef(false);
 const [revision,setRevision]=useState(0);
 const [tab,setTab]=useState(initialTab),[row,setRow]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(''),[name,setName]=useState(''),[paths,setPaths]=useState(''),[launch,setLaunch]=useState(null),[events,setEvents]=useState(null),[eventsError,setEventsError]=useState(''),[proposals,setProposals]=useState([]);
 const tabs=[['connection','连接设置'],['resources','资源登记'],['workspaces','工作区'],['events','运行记录']];
 async function refresh(){
  const n=++seq.current;
  try{
   const data=await api(endpoint(id));if(n!==seq.current)return;
   setRow(data);setProposals(data.proposals||[]);setError('');
   if(!initialized.current){initialized.current=true;setName(data.name||agentName(data));setPaths((data.resources||[]).join('\n'));setLaunch(data.launch?{...data.launch}:{...launchDefaults(data.agent_type),cwd:data.resources?.[0]||''});}
  }catch(e){if(n===seq.current)setError(e.message);}
 }
 useEffect(()=>{dialog.current?.showModal();refresh();const timer=setInterval(refresh,5000);return()=>{seq.current++;clearInterval(timer);dialog.current?.close();if(origin.current?.isConnected)origin.current.focus({preventScroll:true});};},[id]);
 useEffect(()=>{
  let active=true;if(tab==='events'){setEvents(null);setEventsError('');}
  function load(){
   if(tab==='events')api(endpoint(id)+'/events').then(r=>{if(active){setEvents(r.events||[]);setEventsError('');}}).catch(e=>{if(active)setEventsError(e.message);});
  }
  load();const timer=setInterval(load,5000);
  return()=>{active=false;clearInterval(timer);};
 },[tab,row?.generation,row?.updated_at,row?.connected,row?.pid,row?.status,revision]);
 async function act(label,fn){setBusy(label);setError('');try{const value=await fn();await refresh();setRevision(n=>n+1);onChanged();return {ok:true,value};}catch(e){setError(e.message);return {ok:false};}finally{setBusy('');}}
 const [stopping,setStopping]=useState(null);
 const controlled=row?.mode==='controlled'; const pending=proposals.filter(p=>p.state==='pending'&&p.classification==='expand'&&p.generation===row?.generation&&p.base_hash===row?.policy_hash);
 return <dialog ref={dialog} className="record-drawer instance-drawer" aria-label="Agent 配置" onCancel={e=>{e.preventDefault();onClose();}}>
 <div className="record-drawer-head"><h2>{row?agentName(row):'读取 Agent…'}</h2><div className="actions">{row&&(canOpen(row)||canStart(row)||canCheckEntry(row))&&<button type="button" className="button tiny primary" disabled={!!busy} onClick={()=>act(canStart(row)?'启动并打开 Agent':'打开 Agent',()=>onOpen(row))}>{entryAction(row).label}</button>}<button type="button" className="button tiny ghost" onClick={onClose}>关闭</button></div></div>
 <div className="record-drawer-tabs" role="tablist" aria-label="Agent 配置内容">{tabs.map(([key,label])=><button type="button" id={'instance-tab-'+key} key={key} role="tab" aria-controls={'instance-pane-'+key} aria-selected={tab===key} tabIndex={tab===key?0:-1} onClick={()=>setTab(key)} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,setTab)}>{label}</button>)}<button type="button" onClick={()=>{onClose();onSessions?.(id);}}>查看会话 ↗</button><button type="button" onClick={()=>{onClose();onConfiguration?.(id);}}>到系统查看配置 ↗</button></div>
 <div className="record-drawer-body" role="tabpanel" id={'instance-pane-'+tab} aria-labelledby={'instance-tab-'+tab}>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}{busy&&<p role="status">{busy}…</p>}
 {row&&tab==='connection'&&<>
  <Fields values={[["Agent",agentName(row)],["运行状态",<ProductStatus value={row.product_status?.runtime} dimension="runtime"/>],["加载核验",<ProductStatus value={row.product_status?.loading}/>]]}/>

  {controlled?<form className="instance-form" onSubmit={e=>{e.preventDefault();act('保存启动配置',()=>api(endpoint(id),{method:'PUT',body:JSON.stringify({name,launch:{command:launch.command,cwd:launch.cwd,kind:launch.kind,web_url:launch.web_url},expected_launch_hash:row.launch?.hash||null,expected_policy_hash:row.policy_hash})}));}}>
    {launch&&<AgentLaunchFields type={row.agent_type} value={launch} onChange={setLaunch} disabled={!!busy||!['closed','failed'].includes(row.gate)}/>}
    {!row.launch&&<p className="field-note">此连接沿用已有受控启动配置。保存后使用上面的显式命令。</p>}
    <div className="actions"><button className="button primary" disabled={!!busy||!['closed','failed'].includes(row.gate)}>保存启动配置</button><button type="button" className="button ghost" disabled={!!busy||row.gate==='closed'} onClick={()=>setStopping({generation:row.generation??null,policy_hash:row.policy_hash,pid:row.pid})}>停止 Agent</button></div>
  </form>:<p className="field-note">此连接提供已有入口的打开与观测；尚未接管执行策略。</p>}
 </>}
 {row&&tab==='workspaces'&&<NativeAgentWorkspaces id={id} api={api}/>}
 {row&&tab==='resources'&&<>
   <details className="policy-inheritance"><summary>文件访问范围 · {(row.resources||[]).length} 个目录</summary><form className="instance-form" onSubmit={e=>{e.preventDefault();act('保存文件访问范围',()=>api(endpoint(id),{method:'PUT',body:JSON.stringify({name,resources:paths.split('\n').map(p=>p.trim()).filter(Boolean),expected_policy_hash:row.policy_hash})}));}}><label>允许访问的项目目录<textarea required rows={4} value={paths} onChange={e=>setPaths(e.target.value)}/></label><p className="field-note">默认包含启动目录。这里只登记可访问范围，DSH 工作区仍由原生页面管理；目录默认只读。停止 Agent 后可追加目录；已有映射顺序保持稳定，替换或移除目录请新建连接。</p><button className="button tiny primary" disabled={!!busy||!['closed','failed'].includes(row.gate)}>保存文件访问范围</button></form></details>
  </>}
 {row&&tab==='events'&&<div className="security-runtime">{eventsError&&<p role="alert">{eventsError}</p>}<PagedRecords labels={['时间','操作','会话 / 工具','处理结果']} rows={(events||[]).map(e=>[timeLabel(e.created_at),kinds[e.kind]||e.kind,[e.session_id,e.tool].filter(Boolean).join(' / ')||'整个 Agent',<RecordBadge>{eventResult(e)}</RecordBadge>])} empty={eventsError?'运行记录读取失败':events?'暂无运行记录':'正在读取运行记录…'}/></div>}
 </div>{stopping&&<PolicyLifecycleDialog title={'停止 '+agentName(row)} confirmLabel="停止全部会话" busy={!!busy} onClose={()=>setStopping(null)} onConfirm={async()=>{const result=await act('停止 Agent',()=>post(endpoint(id)+'/stop',{generation:stopping.generation,policy_hash:stopping.policy_hash}));if(result.ok)setStopping(null);else throw Error('停止未完成，请刷新检查实际运行状态。');}}><p>确认进程：{stopping.pid?'PID '+stopping.pid:'当前未核验'}。若运行身份或策略发生变化，需要重新确认。</p><p>将停止这个 Agent 的全部会话及受控执行进程。策略配置和历史记录保留，之后需要你手动启动。</p><p>停止 Agent 与停用策略是两个操作。</p></PolicyLifecycleDialog>}</dialog>
}
function Add({api,post,onClose,onCreated}){
 const dialog=useRef(null),origin=useRef(document.activeElement);
 const [type,setType]=useState('dsh'),[mode,setMode]=useState('controlled'),[env,setEnv]=useState('wsl'),[url,setUrl]=useState(''),[name,setName]=useState(''),[launch,setLaunch]=useState(launchDefaults('dsh')),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();if(origin.current?.isConnected)origin.current.focus();}},[]);
 return <dialog ref={dialog} className="record-drawer instance-add" aria-label="添加 Agent 连接" onCancel={e=>{e.preventDefault();onClose();}}><div className="record-drawer-head"><h2>添加连接</h2><button type="button" className="button tiny ghost" onClick={onClose}>关闭</button></div><form className="record-drawer-body instance-form" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const r=await post('/api/agent-instances',{name:name.trim()||types[type],agent_type:type,mode,environment:env,open_url:url,resources:[],launch:mode==='controlled'?launch:null});onCreated(r);}catch(e){setError(e.message);}finally{setBusy(false);}}}>
 <label>接入方式<select value={mode} onChange={e=>{setMode(e.target.value);setEnv('wsl')}}><option value="controlled">启动并接入策略管控</option><option value="observed">打开已有网页（仅登记）</option></select></label><label>Agent<select value={type} onChange={e=>{setType(e.target.value);setLaunch({...launchDefaults(e.target.value),cwd:launch.cwd})}}><option value="dsh">DeepSeek Harness</option><option value="hermes">Hermes</option><option value="other">其他 Node / Python Agent</option></select></label><label>连接名称<input maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder={types[type]}/></label>{mode==='controlled'?<><AgentLaunchFields type={type} value={launch} onChange={setLaunch}/><p className="field-note">系统与 Agent 策略在运行前加载并核验。默认只读启动目录，可在资源登记中追加目录，在系统中管理策略。原生工作区与会话流程保留。</p>{type==='other'&&<p className="field-note">其他命令支持进程与子进程的文件、网络策略，当前模型网络预设为 DeepSeek；原生工具、工作区与会话需对应适配器，当前不支持。</p>}</>:<><label>运行环境<select value={env} onChange={e=>setEnv(e.target.value)}><option value="wsl">WSL</option><option value="windows">Windows</option></select></label><label>原生网页入口<input required value={url} onChange={e=>setUrl(e.target.value)} placeholder="http://127.0.0.1:端口/"/></label><p className="field-note">仅打开已有网页，不代表执行已受 AgentScope 策略管控。</p></>}{error&&<p role="alert" className="inline-notice warning">{error}</p>}<button className="button primary" disabled={busy}>{busy?'正在保存…':'保存连接'}</button></form></dialog>;
}
export default function AgentInstances(props){
 const {api,post,notify,active,workspaceSeed}=props;
 const [rows,setRows]=useState([]),[loaded,setLoaded]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(''),[selected,setSelected]=useState(''),[detailTab,setDetailTab]=useState('connection'),[adding,setAdding]=useState(false);
 const seq=useRef(0),inFlight=useRef(null);
 const visibleRows=visibleAgentInstances(rows);
 useEffect(()=>{if(props.configurationId){setSelected(props.configurationId);setDetailTab(['resources','workspaces','events'].includes(props.configurationTab)?props.configurationTab:'connection');}},[props.configurationId,props.configurationTab,props.policyScope]);
 function configure(id,tab='connection'){setDetailTab(tab);setSelected(id);}
 function refresh(){if(inFlight.current)return inFlight.current;const n=++seq.current;inFlight.current=(async()=>{try{const r=await api('/api/agent-instances');if(n===seq.current){setRows(r.instances||[]);setLoaded(true);setError('');}}catch(e){if(n===seq.current){setLoaded(true);setError(e.message);}}finally{inFlight.current=null;}})();return inFlight.current;}
 useEffect(()=>{if(!active)return;refresh();const t=setInterval(refresh,5000);return()=>{seq.current++;clearInterval(t);};},[active,api]);
 async function act(id,label,fn){setBusy(id);try{await fn();await refresh();}catch(e){notify(e.message);setError(e.message);}finally{setBusy('');}}
 const [recovering,setRecovering]=useState(null);
 const open=row=>openConnection({row,post,onRecovery:setRecovering});
 const openInstance=row=>{const action=entryAction(row).action;if(action==='instructions'){configure(row.id);return;}if(action==='processes'){props.onSessions?.(row.id);return;}return act(row.id,'打开',()=>open(row));};

 return <div className="content task-console agent-connections agent-instance-console">
 <div className="connection-toolbar"><h2 className="connection-current-title">当前连接</h2><div className="actions"><button type="button" className="button ghost" disabled={!!busy} onClick={()=>act('discover','发现 Agent',async()=>{const r=await post('/api/agent-instances/discover');await refresh();})}>发现 Agent</button><button type="button" className="button primary" onClick={()=>setAdding(true)}>添加连接</button></div></div>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}
 <Records labels={['Agent','运行 PID','运行状态','加载核验','操作']} rows={visibleRows.map(row=>[
 <span className={"record-agent brand-"+row.agent_type}><span className="record-agent-icon" aria-hidden="true">{connectionName(row).slice(0,1)}</span><span><b>{connectionName(row)}</b></span></span>,
 <ConnectionPid row={row}/>,
 <ProductStatus value={row.product_status?.runtime} dimension="runtime"/>,<ProductStatus value={row.product_status?.loading}/>,
 <div className="actions"><button type="button" className="button tiny ghost" disabled={!!busy} onClick={()=>openInstance(row)}>{busy===row.id?'正在处理…':entryAction(row).label}</button><button type="button" className="button tiny ghost" onClick={()=>configure(row.id)}>配置</button></div>
 ])} empty={loaded?(error?"当前观测不可用，请重新检查。":"添加 Agent 后可查看连接。") :"正在读取 Agent…"}/>

 {adding&&active&&<Add api={api} post={post} onClose={()=>setAdding(false)} onCreated={r=>{setAdding(false);configure(r.id);refresh();}}/>}
 {selected&&active&&<Drawer key={selected+detailTab+props.policyScope} id={selected} initialTab={detailTab} policyScope={props.policyScope} api={api} post={post} onSessions={props.onSessions} onConfiguration={props.onConfiguration} onOpen={open} onChanged={refresh} onClose={()=>{setSelected('');props.onContext?.({connectionInstance:'',connectionTab:''});}}/>}
 {recovering&&active&&<PolicyLifecycleDialog title="重新启动并打开 Agent？" confirmLabel="确认重新启动并打开" onClose={()=>setRecovering(null)} onConfirm={async()=>{
  await restartConnection({snapshot:recovering.row,post});setRecovering(null);await refresh();
 }}>
  <p>{agentName(recovering.row)}</p><p>暂时无法打开现有入口。重新启动会中断这个 Agent 的共享会话和正在执行的任务，并按现有配置重新加载保护。</p>
  <p>尚未执行重启；取消不会改变 Agent。</p>
 </PolicyLifecycleDialog>}
 </div>
}
