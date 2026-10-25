import React,{useEffect,useId,useState} from 'react';
import './sessionAudit.css';

export default function LifecycleSettings({instanceId,configuration,api,post,onSaved}){
 const id=useId(),[open,setOpen]=useState(false),[workspaces,setWorkspaces]=useState([]);
 const [enabled,setEnabled]=useState(!!configuration?.enabled),[requirements,setRequirements]=useState(configuration?.requirements||'');
 const [workspace,setWorkspace]=useState(configuration?.workspace_id||''),[paths,setPaths]=useState((configuration?.integrity_paths||[]).join('\n'));
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{
  if(!open)return;let alive=true;
  api('/api/agent-instances/'+encodeURIComponent(instanceId)+'/policy-reference-workspaces').then(value=>{
   if(alive){setWorkspaces(value.workspaces);if(!workspace&&value.workspaces.length===1)setWorkspace(value.workspaces[0].id);}
  }).catch(()=>{if(alive)setError('参考工作区暂不可读取，请检查受控连接后重试。');});
  return()=>{alive=false;};
 },[open,instanceId,api]);
 async function save(e){
  e.preventDefault();setBusy(true);setError('');
  try{await post('/api/policy-lifecycle/'+encodeURIComponent(instanceId)+'/configuration',{enabled,requirements,workspace_id:workspace,integrity_paths:paths.split('\n').map(p=>p.trim()).filter(Boolean)});setOpen(false);onSaved();}
  catch{setError('设置未保存，请核对当前 Agent 的工作区、读取权限和相对文件路径。');}finally{setBusy(false);}
 }
 return <details className="lifecycle-settings" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary>自动评估设置 · {configuration?.enabled?'已启用':'未启用'}</summary>
  <form onSubmit={save}>
   <label className="lifecycle-toggle"><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/> 对此 Agent 的新运行事件自动评估与审计</label>
   <label htmlFor={id+'-requirements'}>场景要求</label>
   <textarea id={id+'-requirements'} required minLength={5} maxLength={8000} value={requirements} onChange={e=>setRequirements(e.target.value)}/>
   <label htmlFor={id+'-workspace'}>参考工作区</label>
   <select id={id+'-workspace'} required value={workspace} onChange={e=>setWorkspace(e.target.value)}><option value="">请选择</option>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select>
   <label htmlFor={id+'-paths'}>完整性核对文件（相对路径，每行一个）</label>
   <textarea id={id+'-paths'} required value={paths} onChange={e=>setPaths(e.target.value)} placeholder="例如 release.json"/>
   <p>启用时读取当前文件作为比较基线；只触发分析，不自动批准或加载策略。关闭后不再触发新分析，已有记录保留。</p>
   {error&&<p role="alert" className="inline-notice warning">{error}</p>}
   <button className="button primary" disabled={busy||!workspace}>{busy?'正在核验并保存…':'核验并保存设置'}</button>
  </form>
 </details>;
}
