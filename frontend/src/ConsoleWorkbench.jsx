import React,{useEffect,useState} from 'react';
import {agentName,agentProcessLabel} from './agentInstancePresentation.mjs';
import {openAgentPage} from './openAgentPage.mjs';
import RecordBadge from './RecordBadge.jsx';

export default function ConsoleWorkbench({api,post,notify,onConfigure,onSessions}){
 const [directory,setDirectory]=useState(null),[agent,setAgent]=useState(''),[workspace,setWorkspace]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true;setDirectory(null);api('/api/sessions?'+new URLSearchParams({instance_id:agent})).then(d=>{if(alive){setDirectory(d);setError('');setAgent(old=>d.connections.some(a=>a.id===old)?old:d.connections.find(a=>a.connected)?.id||d.connections[0]?.id||'');}}).catch(e=>alive&&setError(e.message));return()=>{alive=false};},[api,agent,revision]);
 const current=directory?.connections.find(a=>a.id===agent),sessions=(directory?.records||[]).filter(s=>s.instance_id===agent),workspaces=directory?.workspaces||[];
 const shown=sessions.filter(s=>!workspace||s.resource===workspace);
 return <div className="content task-console"><div className="task-console-heading"><div><h1>策略工作台</h1><p>选择 Agent，查看会话并配置策略。</p></div><div className="actions"><button className="button ghost" onClick={()=>setRevision(r=>r+1)}>刷新</button>{agent&&<button className="button ghost" onClick={()=>onConfigure('system',agent)}>系统策略</button>}</div></div>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}
 {!directory&&!error?<p role="status">正在读取 Agent 与工作区…</p>:<>
 <div className="session-filters"><label>Agent<select value={agent} onChange={e=>{setAgent(e.target.value);setWorkspace('');}}>{directory?.connections.map(a=><option key={a.id} value={a.id}>{agentProcessLabel(a)}</option>)}</select></label>{workspaces.length>0&&<label>工作区<select value={workspace} onChange={e=>setWorkspace(e.target.value)}><option value="">全部工作区</option>{(directory?.workspace_records||[]).map(w=><option key={w.path} value={w.path}>{w.name&&w.name+' · '}{w.path}</option>)}</select></label>}</div>
 {current&&<section className="panel task-section"><div className="panel-head"><div><h2>{agentName(current)}</h2>{current.pid&&<p>PID {current.pid}</p>}</div><div className="actions"><button className="button primary" onClick={()=>onConfigure('agent',agent)}>配置 Agent 策略</button>{current.connected&&<button className="button ghost" disabled={busy} onClick={async()=>{setBusy(true);try{await openAgentPage({id:agent,start:false,post});}catch(e){notify(e.message)}finally{setBusy(false)}}}>打开 Agent</button>}</div></div>
 {shown.length>0&&<><div className="table-scroll"><table className="task-record-table"><thead><tr><th>会话</th>{workspaces.length>0&&<th>工作区</th>}<th>活动</th><th/></tr></thead><tbody>{shown.map(s=><tr key={s.id}><td><b>{s.name||'未命名会话'}</b></td>{workspaces.length>0&&<td>{s.resource&&<>{s.workspace_name&&<b>{s.workspace_name}</b>}<code>{s.resource}</code></>}</td>}<td><RecordBadge>{s.running?'运行中':s.status==='idle'?'空闲':'已保存'}</RecordBadge></td><td><button className="button tiny ghost" onClick={()=>onSessions(agent,s.id)}>查看策略</button></td></tr>)}</tbody></table></div>{directory.next_cursor&&<button className="button ghost" onClick={()=>onSessions(agent)}>查看全部会话</button>}</>}
 </section>}
 </>}
 </div>;
}
