import React,{useEffect,useRef,useState} from 'react';
import ConnectionHistory from './ConnectionHistory.jsx';
import AgentWorkspaces from './AgentWorkspaces.jsx';
import {tabKeys} from './consoleState.mjs';
import {timeLabel} from './taskPresentation.mjs';
import {agentTypes as types,agentName,processLabel,observedProcesses,canStart,entryLabel,entryAction,connectionStatus as status,groupAgentInstances} from './agentInstancePresentation.mjs';
import './taskConsole.css';
import './connections.css';
import './agentInstances.css';
const endpoint=id=>'/api/agent-instances/'+encodeURIComponent(id);
const ruleSentence=r=>r.action==='behavior'?r.text:({allow:'允许',deny:'禁止',confirm:'须经确认'})[r.effect]+({read:'读取',write:'修改与删除',tool:'使用工具',network:'连接 IPv4'})[r.action]+'「'+r.target+'」'+(r.text?'；'+r.text:'。');
const eventResult=e=>e.kind==='tool_result'?(e.detail.succeeded?'工具已返回':'工具返回失败'):e.kind==='tool_denied'?e.detail.reason:e.kind==='tool_start'?'允许执行':e.kind==='policy_applied'?'已应用并核验':e.kind==='policy_proposed'?(e.detail.classification==='expand'?'等待用户确认':'校验收紧'):e.kind==='verified'?'实际保护已核验':e.kind==='quiesced'||e.kind==='stopped'?'旧执行进程已终止':e.detail.scope||e.detail.message||'已记录';
function PagedRecords(props){
 const [page,setPage]=useState(1);const total=Math.max(1,Math.ceil(props.rows.length/15));const current=Math.min(page,total);
 return <><Records {...props} rows={props.rows.slice((current-1)*15,current*15)}/>{total>1&&<div className="instance-pagination"><span>第 {current} / {total} 页 · {props.rows.length} 条记录</span><button type="button" className="button tiny ghost" disabled={current===1} onClick={()=>setPage(current-1)}>上一页</button><button type="button" className="button tiny ghost" disabled={current===total} onClick={()=>setPage(current+1)}>下一页</button></div>}</>;
}
const kinds={registered:'登记连接',configured:'修改连接',starting:'启动实例',verified:'保护核验通过',verification_failed:'保护核验失败',start_failed:'启动失败',stopped:'停止实例',policy_proposed:'提出策略变更',gate_closed:'暂停全部会话',quiesced:'终止旧执行进程',policy_applied:'应用共享策略',policy_apply_failed:'策略应用失败',tool_start:'工具执行前检查',tool_result:'工具执行结果',tool_denied:'工具被拒绝'};
function Fields({values}){return <dl className="task-fields">{values.map(([k,v])=><React.Fragment key={k}><dt>{k}</dt><dd>{v??'—'}</dd></React.Fragment>)}</dl>}
function Records({labels,rows,empty='暂无记录'}){return <div className="table-scroll" tabIndex={0}><table className="task-record-table instance-record-table"><thead><tr>{labels.map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={i}>{row.map((value,n)=><td key={n}>{value??'—'}</td>)}</tr>)}{!rows.length&&<tr><td colSpan={labels.length} className="task-empty">{empty}</td></tr>}</tbody></table></div>}
function InstancePicker({group,busy,onOpen,onConfigure,onProcesses,onClose,returnFocus}){
 const dialog=useRef(null),origin=useRef(document.activeElement);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();const target=returnFocus?.current||origin.current;if(target?.isConnected)target.focus({preventScroll:true});};},[]);
 return <dialog ref={dialog} className="record-drawer instance-drawer instance-picker" aria-label="Agent 实例与进程" onCancel={e=>{e.preventDefault();onClose();}}>
  <div className="record-drawer-head"><h2>{group.name} · 实例与进程</h2><button type="button" className="button tiny ghost" onClick={onClose}>关闭</button></div>
  <div className="record-drawer-body">
   <p className="field-note">多个网页标签可以共用一个执行进程。各实例的策略分别配置。</p>
   <Records labels={['连接来源','入口方式','进程号（PID）','运行环境','连接情况','安全覆盖','操作']} rows={group.members.map(row=>[
    row.mode==='controlled'?'受控实例':row.status==='installed'?'安装入口':'本机观测',
    entryLabel(row),processLabel(row),row.environment==='wsl'?'WSL / Ubuntu':row.environment,status(row),row.security,
    <div className="actions">
     <button type="button" className="button tiny ghost" disabled={!!busy} onClick={()=>onOpen(row)}>{busy===row.id?(canStart(row)?'正在启动与核验…':'正在打开…'):entryAction(row).label}</button>
     {entryAction(row).action!=='processes'&&row.status!=='installed'&&<button type="button" className="button tiny ghost" onClick={()=>onProcesses(row.id)}>查看进程</button>}
     <button type="button" className="button tiny ghost" onClick={()=>onConfigure(row.id)}>配置</button>
    </div>
   ])}/>
  </div>
 </dialog>;
}
function Editor({policy,onChange}){
 const labels={read:'读取文件',write:'修改与删除文件',tool:'使用工具',network:'连接 IPv4',behavior:'行为约定'};
 const add=()=>onChange({...policy,rules:[...policy.rules,{action:'write',target:'',effect:'deny',text:''}]});
 const change=(i,key,value)=>onChange({...policy,rules:policy.rules.map((r,n)=>n===i?{...r,[key]:value}:r)});
 return <div className="instance-policy-editor"><label>网络连接<select aria-label="网络连接" value={policy.network} onChange={e=>onChange({...policy,network:e.target.value})}><option value="model_only">本机控制端、DNS 与模型地址</option><option value="disabled">仅保留本机控制端</option></select></label>
 {policy.rules.map((r,i)=><fieldset className="instance-rule" key={i}><legend>策略 {i+1}</legend><label>行为<select aria-label="行为" value={r.action} onChange={e=>change(i,'action',e.target.value)}>{Object.entries(labels).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><label>决定<select aria-label="决定" value={r.effect} onChange={e=>change(i,'effect',e.target.value)}><option value="deny">禁止</option><option value="allow">允许</option><option value="confirm">确认后允许工具</option></select></label><label className="instance-rule-target">目标<input aria-label="目标" value={r.target} placeholder={r.action==='tool'?'原生工具名称':'已登记目录内的绝对路径'} onChange={e=>change(i,'target',e.target.value)}/></label><label className="instance-rule-text">补充约束<textarea aria-label="补充约束" value={r.text} onChange={e=>change(i,'text',e.target.value)} rows={2}/></label><button type="button" className="button ghost tiny" onClick={()=>onChange({...policy,rules:policy.rules.filter((_,n)=>n!==i)})}>移除</button></fieldset>)}
 <button type="button" className="button ghost tiny" onClick={add}>添加策略</button></div>
}
function Drawer({id,api,post,onClose,onChanged,initialTab='connection'}){
 const dialog=useRef(null),origin=useRef(document.activeElement),seq=useRef(0),initialized=useRef(false);
 const [revision,setRevision]=useState(0);
 const [tab,setTab]=useState(initialTab),[row,setRow]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(''),[name,setName]=useState(''),[paths,setPaths]=useState(''),[edit,setEdit]=useState(null),[sessions,setSessions]=useState(null),[processes,setProcesses]=useState(null),[events,setEvents]=useState([]),[proposals,setProposals]=useState([]),[resource,setResource]=useState('');
 const tabs=[['connection','连接设置'],['policy','实例策略'],['sessions','会话与进程']];
 async function refresh(){
  const n=++seq.current;
  try{
   const data=await api(endpoint(id));if(n!==seq.current)return;
   setRow(data);setProposals(data.proposals||[]);setError('');
   if(!initialized.current){initialized.current=true;setName(agentName(data));setPaths((data.resources||[]).join('\n'));setResource(data.resources?.[0]||'');}
  }catch(e){if(n===seq.current)setError(e.message);}
 }
 useEffect(()=>{dialog.current?.showModal();refresh();const timer=setInterval(refresh,5000);return()=>{seq.current++;clearInterval(timer);dialog.current?.close();if(origin.current?.isConnected)origin.current.focus({preventScroll:true});};},[id]);
 useEffect(()=>{
  let active=true;setSessions(null);setProcesses(null);
  function load(){
   if(tab==='sessions'&&row){
    if(!row.connected){setSessions({sessions:[],mapping_available:false});setProcesses({processes:observedProcesses(row),mapping_available:false});return;}
    Promise.all([api(endpoint(id)+'/sessions'),api(endpoint(id)+'/processes')]).then(([s,p])=>{if(active){setSessions(s);setProcesses(p);}}).catch(e=>active&&setError(e.message));
   }
   if(tab==='policy')api(endpoint(id)+'/events').then(r=>active&&setEvents(r.events||[])).catch(e=>active&&setError(e.message));
  }
  load();const timer=setInterval(load,5000);
  return()=>{active=false;clearInterval(timer);};
 },[tab,row?.generation,row?.updated_at,row?.connected,row?.pid,row?.status,revision]);
 async function act(label,fn){setBusy(label);setError('');try{await fn();await refresh();setRevision(n=>n+1);onChanged();}catch(e){setError(e.message);}finally{setBusy('');}}
 const controlled=row?.mode==='controlled'; const pending=proposals.filter(p=>p.state==='pending'&&p.classification==='expand'&&p.generation===row?.generation&&p.base_hash===row?.policy_hash);
 return <dialog ref={dialog} className="record-drawer instance-drawer" aria-label="Agent 实例配置" onCancel={e=>{e.preventDefault();onClose();}}>
 <div className="record-drawer-head"><h2>{row?agentName(row):'读取实例…'}</h2><button type="button" className="button tiny ghost" onClick={onClose}>关闭</button></div>
 <div className="record-drawer-tabs" role="tablist" aria-label="实例配置内容">{tabs.map(([key,label])=><button type="button" id={'instance-tab-'+key} key={key} role="tab" aria-controls={'instance-pane-'+key} aria-selected={tab===key} tabIndex={tab===key?0:-1} onClick={()=>setTab(key)} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,setTab)}>{label}</button>)}</div>
 <div className="record-drawer-body" role="tabpanel" id={'instance-pane-'+tab} aria-labelledby={'instance-tab-'+tab}>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}{busy&&<p role="status">{busy}…</p>}
 {row&&tab==='connection'&&<>
  <Fields values={[['Agent 类型',types[row.agent_type]||row.agent_type],['入口方式',entryLabel(row)],['打开方式',row.entry?.instructions||'尚未接入原生入口'],...(row.entry?.command?[['CLI 启动命令',<code>{row.entry.command}</code>]]:[]),['运行环境',row.environment==='wsl'?'WSL / Ubuntu':row.environment],['连接情况',status(row)],['安全覆盖',row.security],['策略归属',controlled?'此实例内全部会话与子进程共享':'尚未接管此实例的执行'],['启动来源',controlled?(row.agent_type==='hermes'?'/home/happy/.local/bin/hermes（WSL 独立安装）':'DeepSeek Harness'):(row.source||row.executable||row.runtime?.open_url||'原生观测')]]}/>
  {controlled?<form className="instance-form" onSubmit={e=>{e.preventDefault();act('保存连接设置',()=>api(endpoint(id),{method:'PUT',body:JSON.stringify({name,resources:paths.split('\n').map(p=>p.trim()).filter(Boolean),expected_policy_hash:row.policy_hash})}));}}>
    <label>资源目录<textarea required rows={4} value={paths} onChange={e=>setPaths(e.target.value)} placeholder="每行一个已有项目目录"/></label>
    <p className="field-note">资源目录用于会话映射和文件权限。连接设置在实例停止后修改。</p><div className="actions"><button className="button primary" disabled={!!busy||!['closed','failed'].includes(row.gate)}>保存连接设置</button><button type="button" className="button ghost" disabled={!!busy||row.gate==='closed'} onClick={()=>act('停止实例',()=>post(endpoint(id)+'/stop'))}>停止实例</button></div>
  </form>:<p className="field-note">这是发现的本机实例。新建受控连接后可配置共享策略，原实例继续保持原有运行方式。</p>}
  <details className="instance-identifiers"><summary>连接身份与核验详情</summary><Fields values={[['实例标识',row.id],['主机标识',row.host_id],['系统启动标识',row.boot_id],['运行代次',row.generation],['主进程',row.pid],['启动时刻标识',row.start_ticks],['策略域',row.domain_id],['执行入口',row.gate],['策略哈希',row.policy_hash],['进程范围',row.process_cgroup]]}/></details>
 </>}
 {row&&tab==='policy'&&<>
  {!controlled?<p className="task-empty">当前仅观测此实例，还没有受控策略。请添加受控连接。</p>:<>
  <div className="instance-policy-toolbar"><p>这些规则适用于此实例内的全部会话。</p><button type="button" className="button tiny ghost" disabled={!!busy} onClick={()=>setEdit(edit?null:structuredClone(row.policy))}>{edit?'取消编辑':'编辑策略'}</button></div>
  <Records labels={['完整策略语句','来源','执行方式','当前结果']} rows={(row.policy_records||[]).map(r=>[r.sentence,r.source,r.method,r.result])}/>
  {edit&&<form onSubmit={e=>{e.preventDefault();act('校验并提交策略',async()=>{await post(endpoint(id)+'/policy/proposals',{policy:edit,generation:row.generation,base_hash:row.policy_hash,request_key:crypto.randomUUID()});setEdit(null);});}}><Editor policy={edit} onChange={setEdit}/><p className="field-note">收紧自动应用；扩权需确认候选。更新时全部会话暂停，进程重建后恢复。</p><button className="button primary" disabled={!!busy}>提交策略变更</button></form>}
  {!!pending.length&&<section className="instance-pending"><h3>等待确认的扩权</h3>{pending.map(p=><div key={p.id}><p>影响范围：此实例全部会话</p><p>确认后以以下完整候选替换当前实例策略。未列入的旧规则将被移除。</p><Records labels={['完整策略语句']} rows={[[p.policy.network==='disabled'?'禁止外部网络，保留实例控制连接。':'允许本机控制、DNS 与启动层解析的模型 IPv4 连接。'],...(p.policy.rules||[]).map(r=>[ruleSentence(r)])]}/><button type="button" className="button primary" disabled={!!busy} onClick={()=>act('确认并核验扩权',()=>post(endpoint(id)+'/policy/proposals/'+p.id+'/confirm',{proposal_hash:p.proposal_hash}))}>确认此候选并应用</button></div>)}</section>}
  <section className="instance-events"><h3>运行时记录</h3><PagedRecords labels={['时间','操作','会话 / 工具','处理结果']} rows={events.map(e=>[timeLabel(e.created_at),kinds[e.kind]||e.kind,[e.session_id,e.tool].filter(Boolean).join(' / ')||'整个实例',eventResult(e)])}/></section>
 </>}</>}
 {row&&tab==='sessions'&&<>
  <p className="field-note">会话归属来自原生注册表或会话接口。受控进程核验 cgroup 和策略域；仅发现的进程显示 OS 观测信息。共享执行器会关联多个会话。</p>
  <h3>资源目录</h3><Records labels={['原始目录','执行目录','策略归属']} rows={(row.resources||[]).map(p=>[p,row.resource_records?.find(r=>r.source===p)?.execution||'—',controlled?'实例共享策略':'仅观测'])}/>
  <div className="instance-session-heading"><h3>会话记录</h3>{controlled&&<div className="actions"><select aria-label="新会话资源目录" value={resource} onChange={e=>setResource(e.target.value)}>{(row.resources||[]).map(p=><option key={p}>{p}</option>)}</select><button type="button" className="button tiny primary" disabled={!!busy||!row.active} onClick={()=>act('建立原生会话',()=>post(endpoint(id)+'/sessions',{resource}))}>新建会话</button></div>}</div>
  <Records labels={['会话标识','资源目录','执行进程','关联依据']} rows={(sessions?.sessions||[]).map(s=>[s.id,s.resource,(s.process_ids||[]).join(', '),({native_registry:'原生注册表',native_gateway:'原生会话接口',native_session_database:'原生会话记录'})[s.mapping]||'未提供'])} empty={sessions?'暂无原生会话':'正在读取会话…'}/>
  <h3>执行进程</h3><Records labels={['进程','父进程','职责','策略域核验']} rows={(processes?.processes||[]).map(p=>[p.pid,p.ppid,({'control relay':'实例控制','shared agent executor':'共享 Agent 执行器',child:'子进程','observed process':'OS 观测进程'})[p.role]||p.role,p.domain_verified?'已核验':'未核验'])} empty={processes?'当前未运行':'正在读取进程…'}/>
 </>}
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
 const {api,post,notify,active,pane,onContext,onOpenTask,historySeed,workspaceSeed}=props;
 const [rows,setRows]=useState([]),[loaded,setLoaded]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(''),[selected,setSelected]=useState(''),[detailTab,setDetailTab]=useState('connection'),[groupKey,setGroupKey]=useState(''),[adding,setAdding]=useState(false),[historyRevision,setHistoryRevision]=useState(0);
 const seq=useRef(0);
 const groupReturn=useRef(null);
 const groups=groupAgentInstances(rows),group=groups.find(g=>g.key===groupKey);
 function configure(id,tab='connection'){setDetailTab(tab);setSelected(id);}
 async function refresh(){const n=++seq.current;try{const r=await api('/api/agent-instances');if(n===seq.current){setRows(r.instances||[]);setLoaded(true);setError('');}}catch(e){if(n===seq.current){setLoaded(true);setError(e.message);setRows(old=>old.map(r=>({...r,connected:false,active:false,status:'unknown',security:'当前未核验',can_open:false})));}}}
 useEffect(()=>{if(!active)return;refresh();const t=setInterval(refresh,5000);return()=>{seq.current++;clearInterval(t);};},[active,api]);
 async function act(id,label,fn){setBusy(id);try{await fn();await refresh();}catch(e){notify(e.message);setError(e.message);}finally{setBusy('');}}
 async function open(row,start){
  const target=window.open('about:blank','_blank');
  if(target)target.opener=null;
  try{
   if(start)await post(endpoint(row.id)+'/start');
   const result=await post(endpoint(row.id)+'/open');
   const url=new URL(result.url);
   if(url.protocol!=='http:'||url.hostname!=='127.0.0.1')throw Error('原生页面地址未通过本机核验');
   if(target)target.location.replace(url.href);else throw Error('浏览器阻止新标签页，请允许弹出窗口后重试');
  }catch(e){target?.close();throw e;}
 }
 const openInstance=row=>{const action=entryAction(row).action;if(action==='instructions'){configure(row.id);return;}if(action==='processes'){configure(row.id,'sessions');return;}return act(row.id,'打开',()=>open(row,action==='start'));};
 // Old workspace deep links retain their existing read-only association view.
 if(workspaceSeed)return <AgentWorkspaces {...props}/>;
 return <div className="content task-console agent-connections agent-instance-console"><h1 className="connection-screen-reader-heading">Agent连接</h1>
 <div className="connection-toolbar"><div className="task-hub-tabs" role="tablist" aria-label="连接视图">{[['current','当前连接'],['history','连接历史']].map(([v,l])=><button key={v} type="button" role="tab" className={pane===v?'active':''} aria-selected={pane===v} onClick={()=>onContext?.({connectionsPane:v})}>{l}</button>)}</div><div className="actions">{pane!=='history'&&<><button type="button" className="button ghost" disabled={!!busy} onClick={()=>act('discover','发现 Agent',async()=>{const r=await post('/api/agent-instances/discover');setRows(r.instances||[]);})}>发现 Agent</button><button type="button" className="button primary" onClick={()=>setAdding(true)}>添加连接</button></>}</div></div>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}
 {pane==='history'?<ConnectionHistory api={api} active={active} revision={historyRevision} selected={historySeed} onSelect={id=>onContext?.({connectionHistory:id})} onOpenTask={onOpenTask}/>:<Records labels={['Agent','入口方式','当前进程（PID）','运行环境','连接情况','安全覆盖','操作']} rows={groups.map(g=>{const row=g.preferred;return [<b>{g.name}</b>,entryLabel(row),processLabel(row),row.environment==='wsl'?'WSL / Ubuntu':row.environment,status(row),row.security,<div className="actions"><button type="button" className="button tiny ghost" disabled={!!busy} onClick={()=>openInstance(row)}>{busy===row.id?(canStart(row)?'正在启动与核验…':'正在打开…'):entryAction(row).label}</button><button type="button" className="button tiny ghost" onClick={()=>configure(row.id)}>配置</button><button type="button" className="button tiny ghost" onClick={e=>{groupReturn.current=e.currentTarget;setGroupKey(g.key);}}>实例与进程</button></div>];})} empty={loaded?(error?"当前观测不可用，请重新检查。":"尚未发现 Agent。点击“发现 Agent”，或添加连接。") :"正在观测本机 Agent…"}/>}
 {adding&&active&&<Add api={api} post={post} onClose={()=>setAdding(false)} onCreated={r=>{setAdding(false);configure(r.id);refresh();}}/>}
 {group&&active&&!selected&&<InstancePicker group={group} busy={busy} returnFocus={groupReturn} onOpen={openInstance} onConfigure={configure} onProcesses={id=>configure(id,'sessions')} onClose={()=>setGroupKey('')}/>}
 {selected&&active&&<Drawer key={selected+detailTab} id={selected} initialTab={detailTab} api={api} post={post} onChanged={refresh} onClose={()=>setSelected('')}/>}
 </div>
}
