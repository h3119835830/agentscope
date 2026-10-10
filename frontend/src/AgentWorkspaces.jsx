import React,{useEffect,useRef,useState} from 'react';
import {displayName,timeLabel} from './taskPresentation.mjs';
import './taskConsole.css';
import './connections.css';
import {instanceState,visibleInstances,canReadWorkspace} from './consoleState.mjs';
import WorkspaceRecords from './WorkspaceRecords.jsx';
import {workspaceTasks,workspaceSessions} from './workspaceRecords.mjs';

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

function ConnectionEvidence({agent,failed,error,now,onClose}){
 const dialog=useRef(null),origin=useRef(document.activeElement),state=instanceState(agent,now,failed);
 useEffect(()=>{dialog.current?.showModal();dialog.current?.querySelector('button')?.focus();return()=>{dialog.current?.close();if(origin.current?.isConnected)origin.current.focus();};},[]);
 const capabilities={workspace_read:'读取工作区',native_execute:'原生执行',managed_execute:'受管执行',task_create:'创建任务',session_read:'读取会话',policy_enforcement:'策略执行',directory_browse:'浏览目录'};
 const values=[['实例名称',agent.name],['实例 ID',agent.instance_id||agent.id],['管理模式',agent.kind==='managed'?'受管任务实例':'原生实例观测接入'],['连接观测',state.label],['策略核验','未在连接页核验；在策略工作台查看'],['工作区数量',agent.workspace_count],['进程 PID',agent.pid],['进程启动标识',agent.start_ticks],['实例代次',agent.generation],['检查序号',agent.check_sequence],['检查时间',agent.observed_at?timeLabel(agent.observed_at):undefined],['证据失效时间',agent.expires_at?timeLabel(agent.expires_at):undefined],['证据年龄',typeof agent.evidence_age_seconds==='number'?`${agent.evidence_age_seconds} 秒`:undefined],['能力',(agent.capabilities||[]).map(c=>capabilities[c]||c).join('、')||'未记录'],['检查错误',error||agent.error||'无已记录错误']];
 return <dialog ref={dialog} className="record-drawer" aria-label="Agent连接证据" onCancel={onClose}><div className="record-drawer-head"><h2>连接证据</h2><button className="button ghost tiny" onClick={onClose}>关闭</button></div><div className="record-drawer-body"><FieldRecords items={values.map(([label,value])=>[label,value===undefined||value===null||value===''?'未记录':value])}/></div></dialog>;
}

export default function AgentWorkspaces({api,post,notify,onCreateTask,tasks=[],active=true,agentSeed='',workspaceSeed='',onContext,onOpenTask}) {
 const [agents,setAgents]=useState([]),[instance,setInstance]=useState(agentSeed),[workspaces,setWorkspaces]=useState([]),[selected,setSelected]=useState(workspaceSeed);
 const [inventory,setInventory]=useState(null),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[failed,setFailed]=useState(false),[now,setNow]=useState(Date.now());
 const [adding,setAdding]=useState(false),[name,setName]=useState(''),[path,setPath]=useState(''),[revision,setRevision]=useState(0),[connectionDetail,setConnectionDetail]=useState(null);
 const [query,setQuery]=useState(''),[filesActive,setFilesActive]=useState(false),[workspacesLoading,setWorkspacesLoading]=useState(false),[workspaceError,setWorkspaceError]=useState('');
 const [inventoryRevision,setInventoryRevision]=useState(0);
 const [inventoryError,setInventoryError]=useState('');
 const recordTrigger=useRef(null);
 const seq=useRef(0),workspaceSeq=useRef(0),current=agents.find(a=>a.id===instance),status=instanceState(current,now,failed);
 async function refresh(check){const n=++seq.current;try{const r=check?await post(`/api/workspace-agents/${encodeURIComponent(check)}/check`):await api('/api/workspace-agents');if(n!==seq.current)return;setAgents(r.agents||[]);setFailed(false);setError('');}catch(e){if(n===seq.current){setFailed(true);setError(e.message);}}}
 useEffect(()=>{refresh();const t=setInterval(()=>refresh(),7000),clock=setInterval(()=>setNow(Date.now()),1000);return()=>{seq.current++;clearInterval(t);clearInterval(clock);};},[api]);
 useEffect(()=>{const n=++workspaceSeq.current;setWorkspaces([]);setWorkspaceError('');setAdding(false);setQuery('');if(!instance){setWorkspacesLoading(false);return;}setWorkspacesLoading(true);api(`/api/workspace-agents/${encodeURIComponent(instance)}/workspaces`).then(r=>{if(n===workspaceSeq.current)setWorkspaces(r.workspaces||[]);}).catch(e=>{if(n===workspaceSeq.current)setWorkspaceError(e.message);}).finally(()=>{if(n===workspaceSeq.current)setWorkspacesLoading(false);});return()=>{workspaceSeq.current++;};},[instance,revision,current?.generation,api]);
 useEffect(()=>{if(!instance){const first=visibleInstances(agents,tasks)[0];if(first)setInstance(first.id);}},[agents,instance,tasks]);
 useEffect(()=>setInstance(agentSeed),[agentSeed]);
 useEffect(()=>setSelected(workspaceSeed),[workspaceSeed]);
 const lastInstance=useRef(instance);
 useEffect(()=>{if(lastInstance.current!==instance){setSelected('');lastInstance.current=instance;}},[instance]);
 useEffect(()=>{onContext?.({connectionAgent:instance,connectionWorkspace:selected});},[instance,selected]);
 useEffect(()=>{let active=true;setInventory(null);setInventoryError('');if(!filesActive||!selected||!canReadWorkspace(workspaces,selected)){setLoading(false);return;}setLoading(true);api(`/api/agent-workspaces/${selected}/files`).then(r=>{if(active)setInventory(r);}).catch(e=>{if(active)setInventoryError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[selected,inventoryRevision,workspaces,filesActive,api]);
 async function run(fn){setBusy(true);try{await fn();}catch(e){notify(e.message);}finally{setBusy(false);}}
 const shownWorkspaces=workspaces.filter(workspace=>[workspace.name,workspace.path].some(value=>String(value||'').toLowerCase().includes(query.trim().toLowerCase())));
 const registered=visibleInstances(agents,tasks);
 const selectedWorkspace=workspaces.find(workspace=>workspace.id===selected);
 return <div className="content task-console agent-connections"><h1 className="connection-screen-reader-heading">Agent连接</h1>
 <div className="connection-toolbar"><h2 className="connection-current-title">当前连接</h2><button className="button ghost" disabled={busy} onClick={()=>run(async()=>{await refresh();setRevision(value=>value+1);})}>刷新记录</button></div>
 <div id="connection-pane-current">
 {error&&<p role="alert" className="inline-notice warning">检查失败：{error}。连接状态未知。</p>}
 <section className="panel task-section connection-record-section" aria-label="实例记录"><div className="task-section-heading"><h2>实例记录</h2></div><div className="table-scroll" tabIndex={0} aria-label="实例记录表格"><table className="task-record-table connection-instances"><thead><tr><th>实例</th><th>接入方式</th><th>连接状态</th><th>工作区</th><th>操作</th></tr></thead><tbody>{registered.map(agent=>{const state=instanceState(agent,now,failed);return <tr key={agent.id} className={agent.id===instance?'task-selected-row':''}><td><b>{agent.name}</b></td><td>{agent.kind==='managed'?'受管执行':'原生观测'}</td><td>{state.label}</td><td>{agent.workspace_count??'未提供'}</td><td><div className="actions"><button type="button" className="button tiny ghost" disabled={busy} onClick={()=>run(()=>refresh(agent.id))}>检查</button><button type="button" className="button tiny ghost" aria-pressed={agent.id===instance} onClick={()=>setInstance(agent.id)}>查看工作区</button><button type="button" className="button tiny ghost" onClick={()=>setConnectionDetail(agent)}>连接记录</button></div></td></tr>})}{!registered.length&&<tr><td colSpan={5} className="task-empty">{failed?'状态未知，请重新检查。':'尚未发现实例。'}</td></tr>}</tbody></table></div></section>
 {instance&&<section className="panel task-section connection-record-section" aria-label="工作区记录"><div className="task-section-heading"><h2>工作区记录</h2><div className="connection-workspace-tools"><input type="search" aria-label="搜索工作区" placeholder="搜索名称或目录" value={query} onChange={event=>setQuery(event.target.value)}/><button className="button tiny ghost" disabled={!status.live} onClick={()=>setAdding(!adding)}>添加工作区</button></div></div><dl className="connection-instance-field"><dt>所属实例</dt><dd>{current?.name||instance}</dd></dl>
 {workspaceError&&<p role="alert" className="inline-notice warning">工作区读取失败：{workspaceError} <button type="button" className="button tiny ghost" onClick={()=>setRevision(value=>value+1)}>重试</button></p>}
 {adding&&<form className="workspace-register-form" onSubmit={e=>{e.preventDefault();run(async()=>{await post(`/api/workspace-agents/${encodeURIComponent(instance)}/workspaces`,{name,path});setAdding(false);setRevision(v=>v+1);});}}><label>名称<input required value={name} onChange={e=>setName(e.target.value)}/></label><label>已有目录<input value={path} onChange={e=>setPath(e.target.value)} required={current?.kind==='native'}/></label><button className="button primary" disabled={busy}>登记工作区</button></form>}
 <div className="table-scroll" tabIndex={0} aria-label="工作区记录表格"><table className="task-record-table connection-workspaces"><thead><tr><th>工作区与目录</th><th>会话</th><th>来源任务</th><th>读取状态</th><th>操作</th></tr></thead><tbody>{shownWorkspaces.map(workspace=><tr key={workspace.id}><td><b title={displayName(workspace)}>{displayName(workspace)}</b><small className="task-path" title={workspace.path}>{workspace.path}</small></td><td>{workspaceSessions(workspace).length}</td><td>{workspaceTasks(workspace,tasks).length}</td><td>{workspace.readable?'可读取':'不可读取'}</td><td><div className="actions"><button type="button" className="button tiny ghost" onClick={event=>{recordTrigger.current=event.currentTarget;setSelected(workspace.id);}}>查看记录</button><button type="button" className="button tiny primary" disabled={!workspace.readable||!status.live} onClick={()=>onCreateTask(workspace.id)}>新建任务</button></div></td></tr>)}{!shownWorkspaces.length&&<tr><td colSpan={5} className="task-empty">{workspacesLoading?'正在读取工作区记录…':workspaceError?'工作区记录尚未取得。':query?'没有匹配的工作区。':'此实例尚无工作区记录。'}</td></tr>}</tbody></table></div><div className="task-table-foot"><span>{shownWorkspaces.length} 个工作区</span></div>
 </section>}
 {selectedWorkspace&&active&&<WorkspaceRecords key={selectedWorkspace.id} trigger={recordTrigger.current} workspace={selectedWorkspace} agent={current} tasks={tasks} api={api} files={inventoryError?<p role="alert" className="inline-notice warning">文件读取失败：{inventoryError} <button type="button" className="button tiny ghost" onClick={()=>setInventoryRevision(value=>value+1)}>重试</button></p>:<WorkspaceFiles inventory={inventory} loading={loading||!inventory} onRefresh={()=>setInventoryRevision(value=>value+1)}/>} onFilesActive={setFilesActive} onOpenTask={onOpenTask} onCreateTask={onCreateTask} canCreate={selectedWorkspace.readable&&status.live} onClose={()=>setSelected('')}/>}
 {connectionDetail&&active&&<ConnectionEvidence agent={agents.find(a=>a.id===connectionDetail.id)||connectionDetail} failed={failed} error={error} now={now} onClose={()=>setConnectionDetail(null)}/>}
 </div>
 </div>;
}
