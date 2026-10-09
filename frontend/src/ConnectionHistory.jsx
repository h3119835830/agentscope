import RecordBadge from './RecordBadge.jsx';
import React,{useEffect,useRef,useState} from 'react';
import {timeLabel} from './taskPresentation.mjs';
import {connectionStatus,connectionEvent,mergeConnectionEvents} from './connectionHistory.mjs';

const when = value => value ? timeLabel(value) : '未记录';

function HistoryDrawer({id,api,onClose,onOpenTask}){
 const dialog=useRef(null),origin=useRef(document.activeElement),sequence=useRef(0);
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function load(before){const n=++sequence.current;setBusy(true);setError('');try{const r=await api(`/api/workspace-connection-history/${encodeURIComponent(id)}${before?`?before=${before}`:''}`);if(n===sequence.current)setData(old=>({...r,events:before?mergeConnectionEvents(old?.events||[],r.events):r.events}));}catch(e){if(n===sequence.current)setError(e.message);}finally{if(n===sequence.current)setBusy(false);}}
 useEffect(()=>{dialog.current?.showModal();dialog.current?.querySelector('button')?.focus();load();return()=>{sequence.current++;dialog.current?.close();if(origin.current?.isConnected)origin.current.focus();};},[id]);
 return <dialog ref={dialog} className="record-drawer connection-history-drawer" aria-label="连接历史详情" onCancel={onClose}>
  <div className="record-drawer-head"><div><h2>连接历史</h2><span className="task-path">{id}</span></div><button type="button" className="button ghost tiny" onClick={onClose}>关闭</button></div>
  <div className="record-drawer-body">
   <p className="field-note">历史核验记录仅说明当时的观测结果。查看当前状态，请返回“当前连接”重新检查。</p>
   {error&&<p role="alert" className="inline-notice warning">{error}<button className="button ghost tiny" onClick={()=>load()}>重试</button></p>}
   {!data&&busy&&<p role="status">正在读取连接历史…</p>}
   {data&&<>
    <h3 className="task-subheading">关联任务 <span className="muted">{data.tasks.length}</span></h3>
    <p className="field-note">关联沿用任务保存的实例来源；后来生成的执行进程会保留自己的连接记录。</p>
    {data.tasks.length?<ul className="connection-task-links">{data.tasks.map(task=><li key={task.id}><button className="button ghost tiny" onClick={()=>onOpenTask(task.id)}>{task.name||task.id}</button><small>{task.ended_at?'已结束':'已保存任务'} · {task.association_source==='workspace_source'?'工作区来源':'受管执行实例'}{task.generation?` · 代次 ${task.generation}`:''}</small></li>)}</ul>:<p className="task-empty">还没有关联任务。</p>}
    <h3 className="task-subheading">连接过程 <span className="muted">{data.total} 条</span></h3>
    <ol className="connection-timeline">{data.events.map(event=>{const o=event.observation;return <li key={event.id}>
     <div className="connection-event-title"><b>{connectionEvent(event.event)}</b><time>{when(event.occurred_at)}</time></div>
     <p>{event.previous_status&&event.previous_status!==event.status?`${connectionStatus(event.previous_status)} → `:''}{connectionStatus(event.status)}</p>
     <dl className="task-fields"><dt>当时进程</dt><dd>{o.pid?`PID ${o.pid}`:'未取得进程证据'}</dd><dt>实例代次</dt><dd>{o.generation||'未取得代次'}</dd><dt>核验时间</dt><dd>{when(o.observed_at)}</dd><dt>工作区</dt><dd>{o.workspaces.length?o.workspaces.map(w=>w.name||w.id).join('、'):'未取得工作区证据'}</dd></dl>
     <details className="connection-event-detail"><summary>核验标识</summary><dl className="task-fields"><dt>检查序号</dt><dd>{o.check_sequence??'未记录'}</dd><dt>进程启动标识</dt><dd>{o.start_ticks||'未记录'}</dd><dt>证据失效时间</dt><dd>{when(o.expires_at)}</dd><dt>会话</dt><dd>{[...new Set([o.session_id,...o.workspaces.flatMap(w=>w.session_ids)].filter(Boolean))].join('、')||'未记录'}</dd></dl></details>
    </li>;})}</ol>
    {data.next_before&&<button className="button ghost" disabled={busy} onClick={()=>load(data.next_before)}>{busy?'正在读取…':'更早的记录'}</button>}
   </>}
  </div>
 </dialog>;
}

export default function ConnectionHistory({api,active,revision,selected,onSelect,onOpenTask}){
 const [data,setData]=useState(null),[page,setPage]=useState(0),[error,setError]=useState(''),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0);
 useEffect(()=>{let current=true;if(!active)return;setLoading(true);setError('');api(`/api/workspace-connection-history?page=${page}`).then(r=>{if(current)setData(r);}).catch(e=>{if(current)setError(e.message);}).finally(()=>{if(current)setLoading(false);});return()=>{current=false;};},[api,active,page,revision,retry]);
 return <section className="panel task-section" aria-label="连接历史列表">
  <div className="task-section-heading"><div><h2>连接历史</h2><p className="field-note">按实例归档接入、状态变化和手动核验。历史状态不代表当前在线。</p></div></div>
  {data?.recording_started_at&&<p className="field-note">开始记录于 {when(data.recording_started_at)}；此前的连接过程没有补造。</p>}
  {error&&<p role="alert" className="inline-notice warning">历史读取失败：{error} <button className="button ghost tiny" onClick={()=>setRetry(v=>v+1)}>重试</button></p>}
  {loading&&<p role="status" className="field-note">正在读取连接历史…</p>}
  {!error&&<><div className="table-scroll"><table className="task-record-table connection-history-table"><thead><tr><th>实例</th><th>最近历史状态</th><th>首次 / 最近记录</th><th>关联任务</th><th>操作</th></tr></thead><tbody>{data?.records.map(row=><tr key={row.instance_id}><td><b>{row.name}</b><small>{row.kind==='native'?'原生 DSH':'受管 DSH'}</small><small className="task-path">{row.instance_id}</small></td><td><RecordBadge tone="purple">{connectionStatus(row.status)}</RecordBadge><small>历史记录 · {row.event_count} 次</small></td><td>{when(row.first_recorded_at)}<small>{when(row.occurred_at)}</small></td><td>{row.task_count}</td><td><button type="button" className="button tiny ghost" onClick={()=>onSelect(row.instance_id)}>查看详情</button></td></tr>)}{!loading&&!data?.records.length&&<tr><td colSpan={5} className="task-empty">还没有连接历史。实例下一次独立检查后会开始记录。</td></tr>}</tbody></table></div>
  <div className="task-table-foot"><span>{data?.total??0} 个实例</span><div className="actions"><button className="button tiny ghost" disabled={loading||!page} onClick={()=>setPage(v=>v-1)}>上一页</button><span>{page+1} / {Math.max(1,Math.ceil((data?.total||0)/(data?.limit||12)))}</span><button className="button tiny ghost" disabled={loading||(page+1)*(data?.limit||12)>=(data?.total||0)} onClick={()=>setPage(v=>v+1)}>下一页</button></div></div></>}
  {selected&&active&&<HistoryDrawer key={selected} id={selected} api={api} onClose={()=>onSelect('')} onOpenTask={onOpenTask}/>}
 </section>;
}
