import React,{useEffect,useState} from 'react';
import {displayName,timeLabel} from './taskPresentation.mjs';
import './taskConsole.css';

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

export default function AgentWorkspaces({api,post,notify,onCreateTask}) {
  const [agents,setAgents]=useState([]),[workspaces,setWorkspaces]=useState([]),[selected,setSelected]=useState('');
  const [inventory,setInventory]=useState(null),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [adding,setAdding]=useState(false),[name,setName]=useState(''),[path,setPath]=useState(''),[revision,setRevision]=useState(0);
  const dsh=agents.find(a=>a.id==='dsh');
  async function refresh(){const response=await api('/api/workspace-agents');setAgents(response.agents);if(response.agents.some(a=>a.id==='dsh'&&a.connected))setWorkspaces((await api('/api/workspace-agents/dsh/workspaces')).workspaces);else setWorkspaces([]);}
  useEffect(()=>{let active=true;const load=async()=>{try{const response=await api('/api/workspace-agents');if(!active)return;setAgents(response.agents);if(response.agents.some(a=>a.id==='dsh'&&a.connected)){const value=await api('/api/workspace-agents/dsh/workspaces');if(active)setWorkspaces(value.workspaces);}setError('');}catch(e){if(active)setError(e.message);}};load();const timer=setInterval(load,10000);return()=>{active=false;clearInterval(timer);};},[api]);
  useEffect(()=>{let active=true;setInventory(null);if(!selected)return;setLoading(true);api(`/api/agent-workspaces/${selected}/files`).then(value=>{if(active){setInventory(value);setError('');}}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[selected,revision,api]);
  async function run(fn){setBusy(true);try{await fn();await refresh();}catch(e){notify(e.message);}finally{setBusy(false);}}
  return <div className="content task-console">
    <div className="task-console-heading"><div><h1>Agent 与工作区</h1><p>连接 Agent，查看它能读取的工作区，再选择工作区新建任务。</p></div><button className="button ghost" disabled={busy} onClick={()=>run(async()=>{})}>刷新连接</button></div>
    {error&&<div role="alert" className="inline-notice warning">{error}</div>}
    <section className="panel task-section"><div className="task-section-heading"><h2>可连接的 Agent</h2></div>
      <div className="table-scroll"><table className="task-record-table"><thead><tr><th>Agent</th><th>连接状态</th><th>工作区读取</th><th>任务会话</th><th>操作</th></tr></thead><tbody>
        {agents.map(a=><tr key={a.id}><td><b>{a.name}</b><small>{a.adapter}</small></td><td><span className={`tag ${a.connected?'good':a.available?'neutral':'warn'}`}>{a.connected?'已连接':a.available?'可连接':'暂不可连接'}</span></td><td>{a.capabilities.includes('workspace_read')?'支持':'未接入'}</td><td>{a.running_tasks?`${a.running_tasks} 个执行中`:'尚无执行会话'}</td><td><button className="button tiny primary" disabled={busy||!a.available} onClick={()=>run(()=>post(`/api/workspace-agents/${a.id}/connect`))}>{a.connected?'重新检查':'连接 Agent'}</button></td></tr>)}
        {!agents.length&&<tr><td colSpan={5} className="task-empty">正在检查可连接的 Agent…</td></tr>}
      </tbody></table></div>
      {dsh?.error&&<p role="status" className="field-note">{dsh.error}</p>}
      <p className="field-note">连接的是 DSH 执行端。任务启动后，在任务工作台查看实际会话与进程状态。</p>
    </section>
    <section className="panel task-section"><div className="task-section-heading"><h2>DSH 工作区</h2><button className="button ghost tiny" disabled={!dsh?.connected} onClick={()=>setAdding(!adding)}>添加工作区</button></div>
      {adding&&<form className="workspace-register-form" onSubmit={e=>{e.preventDefault();run(async()=>{const value=await post('/api/workspace-agents/dsh/workspaces',{name,path});setSelected(value.id);setAdding(false);setName('');setPath('');notify('工作区已登记，可以放入项目文件');});}}>
        <label>工作区名称<input value={name} maxLength={120} onChange={e=>setName(e.target.value)} required/></label>
        <label>已有 DSH 目录（可选）<input value={path} onChange={e=>setPath(e.target.value)} placeholder="留空则创建独立文件工作区"/></label>
        <button className="button primary" disabled={busy||!name.trim()}>保存工作区</button>
      </form>}
      <div className="table-scroll"><table className="task-record-table"><thead><tr><th>工作区</th><th>目录</th><th>状态</th><th>操作</th></tr></thead><tbody>
        {workspaces.map(w=><tr key={w.id} className={selected===w.id?'task-selected-row':''}><td><b>{displayName(w)}</b><small>{w.origin==='managed_session_workspace'?'Agent 执行工作区':w.origin==='dsh_inbox'?'文件工作区':'已登记 DSH 工作区'}</small></td><td><span className="task-path">{w.path}</span></td><td>{w.readable?'可读取':'目录不可读'}</td><td><div className="actions"><button className="button tiny ghost" disabled={!w.readable} onClick={()=>setSelected(w.id)}>查看文件</button><button className="button tiny primary" disabled={!w.readable} onClick={()=>onCreateTask(w.id)}>新建任务</button></div></td></tr>)}
        {!workspaces.length&&<tr><td colSpan={4} className="task-empty">{dsh?.connected?'尚无工作区。添加一个工作区后放入项目文件。':'先连接上方的 DSH，再读取工作区。'}</td></tr>}
      </tbody></table></div>
    </section>
    {selected&&<section className="panel task-section"><FieldRecords items={[["Agent",'DSH'],["所选工作区",inventory?displayName(inventory.workspace):'读取中'],["文件目录",inventory?.workspace?.path],["读取时间",timeLabel(inventory?.observed_at)]]}/><WorkspaceFiles inventory={inventory} loading={loading} onRefresh={()=>setRevision(v=>v+1)}/></section>}
  </div>;
}
