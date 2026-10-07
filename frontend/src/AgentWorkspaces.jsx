import React,{useEffect,useRef,useState} from 'react';
import {displayName,timeLabel} from './taskPresentation.mjs';
import './taskConsole.css';
import './connections.css';
import {instanceState,visibleInstances,canReadWorkspace,tabKeys} from './consoleState.mjs';
import ConnectionHistory from './ConnectionHistory.jsx';

export function FieldRecords({items}) {
  return <dl className="task-fields">{items.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{value===undefined||value===null||value===''?'—':value}</dd></React.Fragment>)}</dl>;
}

export function WorkspaceFiles({inventory,loading,onRefresh}) {
  const [page,setPage]=useState(0);
  useEffect(()=>setPage(0),[inventory?.workspace?.id,inventory?.manifest_hash]);
  const files=inventory?.files||[],pages=Math.max(1,Math.ceil(files.length/20));
  return <section className="task-file-section" aria-label="工作区文件列表">
    <div className="task-section-heading"><h3>工作区文件</h3><button type="button" className="button tiny ghost" disabled={loading} onClick={onRefresh}>刷新文件</button></div>
    {loading?<p role="status" className="task-empty">正在读取所选工作区…</p>:<>
      <div className="table-scroll"><table className="task-record-table"><thead><tr><th>文件</th><th>类型</th><th>大小</th></tr></thead><tbody>
        {files.slice(page*20,page*20+20).map(f=><tr key={f.relative_path}><td><span className="task-path">{f.relative_path}</span></td><td>{f.kind==='text'?'文本':'二进制文件'}</td><td>{f.size<1024?`${f.size} B`:`${Math.ceil(f.size/1024)} KB`}</td></tr>)}
        {!files.length&&<tr><td colSpan={3} className="task-empty">还没有项目文件。将文件放入此工作区后，点击“刷新文件”。</td></tr>}
      </tbody></table></div>
      <div className="task-table-foot"><span>{files.length} 个文件</span>{pages>1&&<div className="actions"><button type="button" className="button tiny ghost" disabled={!page} onClick={()=>setPage(page-1)}>上一页</button><span>{page+1} / {pages}</span><button type="button" className="button tiny ghost" disabled={page+1>=pages} onClick={()=>setPage(page+1)}>下一页</button></div>}</div>
    </>}
  </section>;
}

function WorkspaceFileDrawer({workspace,inventory,loading,onRefresh,onClose,trigger}){
 const dialog=useRef(null),origin=useRef(trigger||document.activeElement);
 useEffect(()=>{dialog.current?.showModal();dialog.current?.querySelector('button')?.focus();return()=>{dialog.current?.close();const target=origin.current;if(target?.isConnected){target.focus({preventScroll:true});requestAnimationFrame(()=>{if(target.isConnected)target.focus({preventScroll:true});});}};},[]);
 return <dialog ref={dialog} className="record-drawer" aria-label="工作区文件" onCancel={onClose}><div className="record-drawer-head"><h2>{workspace?.name||inventory?.workspace?.name||'工作区'} · 文件</h2><button className="button ghost tiny" onClick={onClose}>关闭</button></div><div className="record-drawer-body"><FieldRecords items={[["目录",workspace?.path||inventory?.workspace?.path||'未记录']]}/>{workspace?.readable?<WorkspaceFiles inventory={inventory} loading={loading} onRefresh={onRefresh}/>:<p role="status" className="field-note">{workspace?'此工作区不可读取。':'正在读取所选工作区信息…'}</p>}</div></dialog>;
}

function ConnectionEvidence({agent,failed,error,now,onClose}){
 const dialog=useRef(null),origin=useRef(document.activeElement),state=instanceState(agent,now,failed);
 useEffect(()=>{dialog.current?.showModal();dialog.current?.querySelector('button')?.focus();return()=>{dialog.current?.close();if(origin.current?.isConnected)origin.current.focus();};},[]);
 const capabilities={workspace_read:'读取工作区',native_execute:'原生执行',managed_execute:'受管执行',task_create:'创建任务',session_read:'读取会话',policy_enforcement:'策略执行',directory_browse:'浏览目录'};
 const values=[['实例名称',agent.name],['实例 ID',agent.instance_id||agent.id],['管理模式',agent.kind==='managed'?'受管任务实例':'原生实例观测接入'],['连接观测',state.label],['策略核验','未在连接页核验；在策略工作台查看'],['工作区数量',agent.workspace_count],['进程 PID',agent.pid],['进程启动标识',agent.start_ticks],['实例代次',agent.generation],['检查序号',agent.check_sequence],['检查时间',agent.observed_at?timeLabel(agent.observed_at):undefined],['证据失效时间',agent.expires_at?timeLabel(agent.expires_at):undefined],['证据年龄',typeof agent.evidence_age_seconds==='number'?`${agent.evidence_age_seconds} 秒`:undefined],['能力',(agent.capabilities||[]).map(c=>capabilities[c]||c).join('、')||'未记录'],['检查错误',error||agent.error||'无已记录错误']];
 return <dialog ref={dialog} className="record-drawer" aria-label="Agent连接证据" onCancel={onClose}><div className="record-drawer-head"><h2>连接证据</h2><button className="button ghost tiny" onClick={onClose}>关闭</button></div><div className="record-drawer-body"><FieldRecords items={values.map(([label,value])=>[label,value===undefined||value===null||value===''?'未记录':value])}/></div></dialog>;
}

export default function AgentWorkspaces({api,post,notify,onCreateTask,tasks=[],active=true,agentSeed='',workspaceSeed='',onContext,pane='current',historySeed='',onOpenTask}) {
 const [agents,setAgents]=useState([]),[instance,setInstance]=useState(agentSeed),[workspaces,setWorkspaces]=useState([]),[selected,setSelected]=useState(workspaceSeed);
 const [inventory,setInventory]=useState(null),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[failed,setFailed]=useState(false),[now,setNow]=useState(Date.now());
 const [adding,setAdding]=useState(false),[name,setName]=useState(''),[path,setPath]=useState(''),[revision,setRevision]=useState(0),[connectionDetail,setConnectionDetail]=useState(null);
 const fileTrigger=useRef(null);
 const [historyRevision,setHistoryRevision]=useState(0);
 const seq=useRef(0),workspaceSeq=useRef(0),current=agents.find(a=>a.id===instance),status=instanceState(current,now,failed);
 async function refresh(check){const n=++seq.current;setFailed(true);try{const r=check?await post(`/api/workspace-agents/${encodeURIComponent(check)}/check`):await api('/api/workspace-agents');if(n!==seq.current)return;setAgents(r.agents||[]);setFailed(false);setError('');}catch(e){if(n===seq.current){setFailed(true);setError(e.message);}}finally{if(check)setHistoryRevision(v=>v+1);}}
 useEffect(()=>{refresh();const t=setInterval(()=>refresh(),7000),clock=setInterval(()=>setNow(Date.now()),1000);return()=>{seq.current++;clearInterval(t);clearInterval(clock);};},[api]);
 useEffect(()=>{const n=++workspaceSeq.current;setWorkspaces([]);setAdding(false);if(!instance)return;api(`/api/workspace-agents/${encodeURIComponent(instance)}/workspaces`).then(r=>{if(n===workspaceSeq.current)setWorkspaces(r.workspaces||[]);}).catch(e=>{if(n===workspaceSeq.current)setError(e.message);});return()=>{workspaceSeq.current++;};},[instance,revision]);
 useEffect(()=>setInstance(agentSeed),[agentSeed]);
 useEffect(()=>setSelected(workspaceSeed),[workspaceSeed]);
 const lastInstance=useRef(instance);
 useEffect(()=>{if(lastInstance.current!==instance){setSelected('');lastInstance.current=instance;}},[instance]);
 useEffect(()=>{onContext?.({connectionAgent:instance,connectionWorkspace:selected});},[instance,selected]);
 useEffect(()=>{let active=true;setInventory(null);if(!selected||!canReadWorkspace(workspaces,selected)){setLoading(false);return;}setLoading(true);api(`/api/agent-workspaces/${selected}/files`).then(r=>{if(active)setInventory(r);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[selected,revision,workspaces]);
 async function run(fn){setBusy(true);try{await fn();}catch(e){notify(e.message);}finally{setBusy(false);}}
 return <div className="content task-console agent-connections"><div className="task-console-heading"><div><h1>Agent连接</h1><p>查看当前实例，或回查连接过程与关联任务。</p></div><button className="button ghost" disabled={busy} onClick={()=>pane==='history'?setHistoryRevision(v=>v+1):refresh()}>{pane==='history'?'刷新历史':'刷新状态'}</button></div>
 <div className="task-hub-tabs" role="tablist" aria-label="连接视图">{[['current','当前连接'],['history','连接历史']].map(([key,label])=><button type="button" key={key} id={`connection-tab-${key}`} role="tab" aria-controls={`connection-pane-${key}`} aria-selected={pane===key} tabIndex={pane===key?0:-1} className={pane===key?'active':''} onClick={()=>onContext?.({connectionsPane:key})} onKeyDown={event=>tabKeys(event,['current','history'],pane,key=>onContext?.({connectionsPane:key}))}>{label}</button>)}</div>
 {pane==='history'?<div id="connection-pane-history" role="tabpanel" aria-labelledby="connection-tab-history"><ConnectionHistory api={api} active={active} revision={historyRevision} selected={historySeed} onSelect={id=>onContext?.({connectionHistory:id})} onOpenTask={onOpenTask}/></div>:<div id="connection-pane-current" role="tabpanel" aria-labelledby="connection-tab-current">
 {error&&<p role="alert" className="inline-notice warning">检查失败：{error}。连接状态未知。</p>}
 {['native','managed'].map(kind=><section key={kind} className="panel task-section"><div className="task-section-heading"><div><h2>{kind==='native'?'原生 DSH':'受管 DSH'}</h2><p className="field-note">{kind==='native'?'用户自行打开的 DSH；观测接入不表示策略受管。':'由任务启动的受控进程；策略是否核验在工作台显示。'}</p></div></div><div className="table-scroll"><table className="task-record-table connection-instances"><thead><tr><th>实例</th><th>连接状态</th><th>执行绑定</th><th>工作区</th><th>操作</th></tr></thead><tbody>{visibleInstances(agents,tasks).filter(a=>a.kind===kind).map(a=>{const state=instanceState(a,now,failed);return <tr key={a.id} className={a.id===instance?'task-selected-row':''}><td><b title={a.name}>{a.name}</b></td><td><span className={'tag '+state.tone}>{state.label}</span></td><td>{a.pid?(state.live?`进程 ${a.pid}`:`上次进程 ${a.pid}`):'无进程证据'}<small>{kind==='managed'?'策略加载与生效在工作台单独核验':'原生实例'}</small></td><td>{a.workspace_count??'—'}</td><td><div className="actions"><button className="button tiny ghost" disabled={busy} onClick={()=>refresh(a.id)}>检查</button><button className="button tiny primary" onClick={()=>setInstance(a.id)}>工作区</button><button className="button tiny ghost" onClick={()=>setConnectionDetail(a)}>连接证据</button></div></td></tr>})}{!visibleInstances(agents,tasks).some(a=>a.kind===kind)&&<tr><td colSpan={5} className="task-empty">{failed?'状态未知，请重新检查':'尚未发现实例'}</td></tr>}</tbody></table></div></section>)}
 {instance&&<section className="panel task-section"><div className="task-section-heading"><h2>{current?.name||instance} 的工作区</h2><button className="button tiny ghost" disabled={!status.live} onClick={()=>setAdding(!adding)}>添加工作区</button></div>
 {adding&&<form className="workspace-register-form" onSubmit={e=>{e.preventDefault();run(async()=>{await post(`/api/workspace-agents/${encodeURIComponent(instance)}/workspaces`,{name,path});setAdding(false);setRevision(v=>v+1);});}}><label>名称<input required value={name} onChange={e=>setName(e.target.value)}/></label><label>已有目录<input value={path} onChange={e=>setPath(e.target.value)} required={current?.kind==='native'}/></label><button className="button primary" disabled={busy}>登记工作区</button></form>}
 <div className="table-scroll"><table className="task-record-table connection-workspaces"><thead><tr><th>工作区</th><th>读取状态</th><th>操作</th></tr></thead><tbody>{workspaces.map(w=><tr key={w.id}><td><b title={displayName(w)}>{displayName(w)}</b><small className="task-path" title={w.path}>{w.path}</small></td><td>{w.readable?'可读取':'不可读取'}</td><td><div className="actions"><button className="button tiny ghost" onClick={event=>{event.currentTarget.focus();fileTrigger.current=event.currentTarget;setSelected(w.id);}} disabled={!w.readable}>查看文件</button><button className="button tiny primary" disabled={!w.readable||!status.live} onClick={()=>onCreateTask(w.id)}>新建任务</button></div></td></tr>)}{!workspaces.length&&<tr><td colSpan={3} className="task-empty">暂无可读取工作区。</td></tr>}</tbody></table></div>
 </section>}
 {selected&&active&&<WorkspaceFileDrawer key={selected} trigger={fileTrigger.current} workspace={workspaces.find(w=>w.id===selected)} inventory={inventory} loading={loading} onRefresh={()=>setRevision(v=>v+1)} onClose={()=>setSelected('')}/>}
 {connectionDetail&&active&&<ConnectionEvidence agent={agents.find(a=>a.id===connectionDetail.id)||connectionDetail} failed={failed} error={error} now={now} onClose={()=>setConnectionDetail(null)}/>}
 </div>}
 </div>;
}
