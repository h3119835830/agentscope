import React,{useEffect,useRef,useState} from 'react';
import catalogue from './rq1-agent-templates.json';
import PolicyTemplateDetail from './PolicyTemplateDetail.jsx';
import AgentPolicyScene from './AgentPolicyScene.jsx';
import PolicyCandidateDetail from './PolicyCandidateDetail.jsx';
import {candidateView,generatedScope,approvalLabel} from './policyExperience.mjs';
import {agentName} from './agentInstancePresentation.mjs';
const cache=new Map();
const uid=()=>crypto.randomUUID();
const busyRun=s=>['queued','running'].includes(s);
function Dialog({title,children,onClose,footer}){
 const ref=useRef(null),origin=useRef(document.activeElement);
 useEffect(()=>{ref.current?.showModal();return()=>{ref.current?.close();if(origin.current?.isConnected)origin.current.focus();};},[]);
 return <dialog ref={ref} className="policy-review-dialog flow-dialog" aria-label={title} onCancel={e=>{e.preventDefault();onClose();}}><header className="experience-detail-head"><h2>{title}</h2><button className="experience-close" aria-label="关闭" onClick={onClose}>×</button></header><div className="experience-detail-body">{children}</div>{footer&&<footer className="experience-detail-footer">{footer}</footer>}</dialog>;
}
function Materials({value,onSave,onClose}){
 const [items,setItems]=useState(value),[name,setName]=useState(''),[text,setText]=useState(''),[error,setError]=useState('');
 return <Dialog title="规范材料" onClose={onClose} footer={<><span>材料作为参考，不授予权限。</span><button className="button primary" onClick={()=>onSave(items)}>保存材料</button></>}><p className="experience-note">引用的名称和正文随草案版本保存。更换材料需要重新生成，已提交的审批快照保持不变。</p>{items.map((m,i)=><div className="flow-material-row" key={i}><span>{m.name}</span><button className="assistant-text-button" onClick={()=>setItems(items.filter((_,n)=>i!==n))}>移除</button></div>)}<label>材料名称<input aria-label="材料名称" maxLength={80} value={name} onChange={e=>setName(e.target.value)}/></label><label>规范内容<textarea aria-label="规范内容" maxLength={8000} rows={6} value={text} onChange={e=>setText(e.target.value)}/></label>{error&&<p role="alert">{error}</p>}<button className="button ghost" disabled={items.length>=10} onClick={()=>{if(!name.trim()||!text.trim()){setError('请填写材料名称和内容。');return;}setItems([...items,{name:name.trim(),text:text.trim()}]);setName('');setText('');setError('');}}>添加材料</button></Dialog>;
}
function Templates({onSelect,onClose}){
 const [q,setQ]=useState('');
 const templates=catalogue.templates.filter(t=>(t.name+' '+t.summary).includes(q));
 return <Dialog title="选择模板" onClose={onClose}><input type="search" autoFocus aria-label="搜索策略模板" value={q} onChange={e=>setQ(e.target.value)} placeholder="搜索名称或用途"/><div className="table-scroll"><table aria-label="策略模板"><thead><tr><th>名称</th><th>用途</th><th>操作</th></tr></thead><tbody>{templates.map(t=><tr key={t.id}><td>{t.name}</td><td>{t.summary}</td><td><button className="assistant-text-button" onClick={()=>onSelect(t)}>使用模板</button></td></tr>)}</tbody></table>{!templates.length&&<p className="task-empty">没有匹配的模板。</p>}</div></Dialog>;
}
export default function AgentPolicyDrafts({target,scope,workspaceId,context,contextError,api,post,onApprovals,onRefreshContext}){
 const identity=target.id+':'+scope+':'+(workspaceId||''),initial=cache.get(identity);
 const [text,setText]=useState(initial?.text||''),[materials,setMaterials]=useState(initial?.materials||[]),[editing,setEditing]=useState(initial?.editing||null),[document,setDocument]=useState(initial?.document||null);
 const [records,setRecords]=useState([]),[runs,setRuns]=useState({}),[results,setResults]=useState({}),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loaded,setLoaded]=useState(false);
 const [materialOpen,setMaterialOpen]=useState(false),[templateOpen,setTemplateOpen]=useState(false),[template,setTemplate]=useState(null),[detail,setDetail]=useState(null),[submission,setSubmission]=useState(null),[ack,setAck]=useState(false),[scene,setScene]=useState(null),[sceneId,setSceneId]=useState(initial?.sceneId||null);
 const alive=useRef(true),saveRequest=useRef(null),actionRequest=useRef(null),tail=useRef(null);
 const root='/api/agent-instances/'+encodeURIComponent(target.id)+'/policy-drafts';
 const query=new URLSearchParams({scope,...(workspaceId?{workspace_id:workspaceId}:{})}).toString();
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{cache.set(identity,{text,materials,editing,document,sceneId});},[identity,text,materials,editing,document,sceneId]);
 async function load(){const value=await api(root+'?'+query);if(alive.current){setRecords(value.records||[]);setLoaded(true);}return value.records||[];}
 useEffect(()=>{let current=true;api(root+'?'+query).then(value=>{if(!current)return;const rows=value.records||[];setRecords(rows);setLoaded(true);if(!initial){const draft=rows.find(d=>d.state==='draft');if(draft){setText(draft.text);setMaterials(draft.materials);setDocument(draft.document);setEditing(draft);setSceneId(draft.scene_id||null);}}}).catch(e=>{if(current){setError(e.message);setLoaded(true);}});return()=>{current=false;};},[api,root,query]);
 const runIds=records.map(d=>d.run_id).filter(Boolean).join('|');
 useEffect(()=>{let current=true,inflight=false;async function poll(){if(inflight)return;inflight=true;await Promise.all(runIds.split('|').filter(Boolean).map(async id=>{try{const [run,page]=await Promise.all([api('/api/history/generations/'+id),api('/api/history/generations/'+id+'/results?limit=20')]);if(current){setRuns(old=>({...old,[id]:run}));setResults(old=>({...old,[id]:page.items||[]}));}}catch(e){if(current)setRuns(old=>({...old,[id]:{status:'read_error',message:e.message}}));}}));inflight=false;}poll();const timer=setInterval(poll,4000);return()=>{current=false;clearInterval(timer);};},[api,runIds]);
 async function persist(values={text,materials,document,scene_id:sceneId}){
  const payload={...values,scope,workspace_id:workspaceId,base_revision:editing?.latest_revision||editing?.revision||0};
  const fingerprint=JSON.stringify({id:editing?.id,...payload});
  if(saveRequest.current?.fingerprint!==fingerprint)saveRequest.current={fingerprint,key:uid()};
  const body={...payload,request_key:saveRequest.current.key};
  const saved=editing?await api(root+'/'+editing.id,{method:'PATCH',body:JSON.stringify(body)}):await post(root,body);
  if(alive.current){setEditing(saved);saveRequest.current=null;}
  return saved;
 }
 async function save(){if(busy)return;setBusy(true);setError('');try{await persist();await load();}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
 async function generate(e){e.preventDefault();if(busy||waiting||!context?.ready||target.mode!=='controlled'||text.trim().length<5)return;setBusy(true);setError('');try{
  const saved=await persist({text,materials,document:null,scene_id:sceneId});
  const fingerprint=saved.id+':'+saved.revision;
  if(actionRequest.current?.fingerprint!==fingerprint)actionRequest.current={fingerprint,key:uid()};
  await post(root+'/'+saved.id+'/generate',{revision:saved.revision,request_key:actionRequest.current.key});
  if(alive.current){setText('');setMaterials([]);setSceneId(null);setDocument(null);setEditing(null);actionRequest.current=null;await load();tail.current?.scrollIntoView({block:'nearest'});}
 }catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
 function revise(d){setText(d.text);setMaterials(d.materials||[]);setDocument(d.document);setEditing(d);setSceneId(d.scene_id||null);setDetail(null);}
 function prepareSubmit(d,result=null){setDetail(null);setAck(false);setSubmission({draft:d,result});actionRequest.current={fingerprint:'submit:'+d.id+':'+d.revision,key:uid()};}
 async function submit(){if(!ack||busy||!submission)return;setBusy(true);setError('');try{const d=submission.draft;
  const p=await post(root+'/'+d.id+'/submit',{revision:d.revision,artifact_id:submission.result?.artifact_id||null,request_key:actionRequest.current.key});
  if(alive.current){setSubmission(null);await load();onApprovals(p.id);}
 }catch(e){if(alive.current){setError(e.message);setSubmission(null);}}finally{if(alive.current)setBusy(false);}}
 async function templateDraft(candidate){setTemplate(null);setBusy(true);setError('');try{const values={scope,workspace_id:workspaceId,text:'配置策略：'+candidate.document.name,materials,document:candidate.document,request_key:uid()};await post(root,values);if(alive.current){await load();setText('');setEditing(null);setDocument(null);}}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
 const waiting=records.some(d=>busyRun(runs[d.run_id]?.status));
 const scopeLabel=scope==='agent'?'此实例的全部工作区与会话':'此实例的当前工作区';
 return <>{scope==='workspace'&&<AgentPolicyScene key={identity} target={target} context={context} api={api} post={post} scene={scene} onScene={setScene} onAdopt={policy=>{setText(policy);setDocument(null);setSceneId(scene?.id||null);}} disabled={busy}/>}
 <section className="policy-assistant assistant-v2 flow-assistant" aria-label="策略助手对话">
  <div className="assistant-chat-messages assistant-v2-messages" aria-live="polite">
   {!records.length&&<div className="assistant-v2-welcome"><span>✦</span><h2>{scope==='agent'?'这个 Agent 应长期遵守什么？':'这个项目需要哪些约束？'}</h2><p>描述对象和限制的操作。先生成草案，核对后提交审批。</p><div className="flow-quick-start">{catalogue.templates.slice(0,3).map(t=><button key={t.id} onClick={()=>{if(scope==='agent')setTemplate(t);else setText(t.summary||t.name);}}>{t.name} ↗</button>)}</div></div>}
   {records.slice().reverse().map(d=>{const run=runs[d.run_id],rows=results[d.run_id]||[],status=d.approval?.status||(d.state==='submitted'?'submitted':null);return <div className="assistant-v2-turn" key={d.id}>
    <article className="assistant-v2-user"><p>{d.text||'未填写的草案'}</p><span>你</span></article>
    <article className="assistant-v2-answer"><span className="assistant-v2-message-icon">✦</span><div>
     {status?<article className="assistant-v2-card"><header><strong>{d.document?.name||'策略变更'}</strong><span className="assistant-card-state">{status==='submitted'?'已提交':approvalLabel(status)}</span></header><p className="flow-card-note">审批快照已固定；应用结果以运行回执为准。</p><footer><button className="assistant-text-button" onClick={()=>revise(d)}>起草新版本</button><button className="button tiny primary" onClick={()=>onApprovals(d.approval_id)}>查看审批</button></footer></article>:d.document?<article className="assistant-v2-card"><header><strong>{d.document.name}</strong><span className="assistant-card-state">待核对草案</span></header><dl><dt>影响范围</dt><dd>{scopeLabel}</dd></dl><footer><button className="assistant-text-button" onClick={()=>revise(d)}>继续调整</button><button className="button tiny primary" disabled={busy} onClick={()=>prepareSubmit(d)}>核对并提交</button></footer></article>:d.run_id?<><p className="assistant-answer-caption">{busyRun(run?.status)?'正在起草策略…':run?.status==='read_error'?'记录读取失败，可刷新重试。':run?.status==='failed'?'生成未完成，请补充需求后重新起草。':rows.length?'请核对候选内容与影响范围。':'正在读取生成结果…'}</p>{rows.map(result=>{const v=candidateView(result);return <article className="assistant-v2-card" key={result.statement_version_id}><header><strong>{v.title}</strong><span className="assistant-card-state">{v.ready?'待核对':'待补充'}</span></header>{v.ready?<dl><dt>影响范围</dt><dd>{generatedScope(result)}</dd><dt>约束对象</dt><dd>{v.targets.join('、')}</dd><dt>操作与处置</dt><dd>{v.operations.join('、')} · {v.effects.join('、')}</dd></dl>:<p className="flow-card-note">尚未形成可提交候选，请补充明确的对象和需求。</p>}<footer><button className="assistant-text-button" onClick={()=>setDetail({draft:d,result})}>查看详情</button>{v.ready?<button className="button tiny primary" disabled={busy} onClick={()=>prepareSubmit(d,result)}>核对并提交</button>:<button className="button tiny ghost" onClick={()=>revise(d)}>补充需求</button>}</footer></article>;})}{!busyRun(run?.status)&&<button className="assistant-text-button" onClick={()=>revise(d)}>重新起草</button>}</>:<article className="assistant-v2-card"><header><strong>已保存草案</strong><span className="assistant-card-state">未生成</span></header><p className="flow-card-note">{scopeLabel} · {d.materials?.length||0} 份参考材料</p><footer><button className="assistant-text-button" onClick={()=>revise(d)}>继续起草</button></footer></article>}
    </div></article></div>;})}
   {!loaded&&<p role="status">正在读取已保存草案…</p>}<div ref={tail}/>
  </div>
  <form className="assistant-chat-composer assistant-v2-composer" onSubmit={generate}>
   {(error||contextError)&&<p role="alert" className="inline-notice warning">{error||contextError} <button type="button" className="assistant-text-button" onClick={()=>contextError?onRefreshContext?.():load().catch(e=>setError(e.message))}>{contextError?'重新核验环境':'重新读取草案'}</button></p>}
   {!context?.ready&&<p className="flow-context-note">{context?.message||'正在核验策略环境…'} 可以先保存需求。</p>}
   {scope==='workspace'&&<p className="flow-context-note">{context?.application_capability?.reason||'当前连接不支持工作区独立应用，候选只供审查。'}</p>}
   {materials.length>0&&<div className="flow-material-chips">{materials.map((m,i)=><span key={i}>{m.name}</span>)}</div>}
   <textarea aria-label="策略需求" rows={2} maxLength={2000} onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();if(context?.ready&&!busy&&!waiting)generate(e);}}} value={text} onChange={e=>{setText(e.target.value);setDocument(null);}} placeholder={scope==='agent'?'描述长期要求；多个资源时请明确对象的完整路径…':'描述当前工作区的具体要求…'}/>
   <div><button type="button" className="assistant-library-trigger" onClick={()=>setMaterialOpen(true)}>＋ 规范材料</button><button type="button" className="assistant-library-trigger" onClick={()=>setTemplateOpen(true)}>选择模板</button><button type="button" className="button tiny ghost" disabled={busy||!text.trim()} onClick={save}>保存草案</button><button className="assistant-send" aria-label="生成策略" disabled={busy||waiting||!context?.ready||text.trim().length<5}>{busy||waiting?'处理中…':'生成策略 ↑'}</button></div>
  </form>
 </section><p className="flow-caption">在这里起草 → 到审批决定 → 显式应用 → 到会话查看实际结果</p>
 {materialOpen&&<Materials value={materials} onClose={()=>setMaterialOpen(false)} onSave={items=>{setMaterials(items);setMaterialOpen(false);}}/>}
 {templateOpen&&<Templates onClose={()=>setTemplateOpen(false)} onSelect={t=>{setTemplateOpen(false);if(scope==='agent')setTemplate(t);else setText(t.summary||t.name);}}/>}
 {template&&<PolicyTemplateDetail template={template} agents={[target]} targetId={target.id} conversation onClose={()=>setTemplate(null)} onHandoff={templateDraft}/>}
 {detail&&<PolicyCandidateDetail result={detail.result} agentName={agentName(target)} busy={busy} onClose={()=>setDetail(null)} onRevise={()=>revise(detail.draft)} onSubmit={()=>prepareSubmit(detail.draft,detail.result)}/>}
 {submission&&<Dialog title="核对并提交审批" onClose={()=>!busy&&setSubmission(null)} footer={<><span>提交后仍未批准或应用。</span><button className="button primary" disabled={!ack||busy} onClick={submit}>{busy?'正在提交…':'提交审批'}</button></>}>
  <dl className="flow-submit-details"><dt>目标</dt><dd>{agentName(target)} · {target.id}</dd><dt>影响范围</dt><dd>{scopeLabel}</dd><dt>需求</dt><dd>{submission.draft.text}</dd><dt>参考材料</dt><dd>{submission.draft.materials?.map(m=>m.name).join('、')||'未引用'}</dd></dl>
  {scope==='workspace'&&<p className="experience-callout">当前不支持工作区独立应用，本次仅提交审查，不能批准加载。</p>}
  <label className="flow-ack"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>已核对内容与范围，确认提交此版本。</label>
 </Dialog>}
 </>;
}
