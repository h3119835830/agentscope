import React,{useCallback,useEffect,useRef,useState} from 'react';
import ArtifactPreview from './PolicyArtifactPreview.jsx';
import PolicyInputForm from './PolicyInputForm.jsx';

const pageSize=20;
const levelNames={'semantic':'语义规则','semantic-only':'语义规则','semantic_only':'语义规则',content:'内容规则','per-event':'单事件规则',per_event:'单事件规则','cross-event':'跨事件规则',cross_event:'跨事件规则','not-applicable':'不适用',not_applicable:'不适用'};
const scopeNames={'self-contained':'通用',self_contained:'通用',project:'项目 / 仓库',task:'任务',not_applicable:'不适用','not-applicable':'不适用'};
const contentNames={policy:'规范',mixed:'混合',description:'描述',uncertain:'待确认'};
const emptyDraft={text:'',category:'semantic',context_scope:'self-contained',execution_layer:'repository_instruction',source_url:''};
const short=value=>value?.slice(0,12)||'—';
const when=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—';
const states={pending_review:'待审核',approved:'已通过候选',rejected:'已拒绝',compiled:'已编译',loaded:'已加载',load_failed:'加载失败',requires_context:'待绑定上下文',unsupported:'不支持',partial:'部分支持',not_checked:'未编译',compile_failed:'编译失败',invalid_candidate:'片段格式无效',checking:'编译中'};
function Status({value}){return <span className={'tag '+(['approved','compiled','loaded'].includes(value)?'good':['rejected','load_failed','compile_failed','invalid_candidate'].includes(value)?'bad':'warn')}>{states[value]||value}</span>}

function RecordDetails({detail,onClose,returnFocus}){
 const dialog=useRef(null);
 const close=()=>{
  if(dialog.current.open)dialog.current.close();
  onClose();
  returnFocus();
 };
 useEffect(()=>{
  const element=dialog.current;
  element.showModal();
  return()=>{if(element.open)element.close()};
 },[]);
 return <dialog ref={dialog} className="record-dialog" aria-labelledby="record-detail-title" onCancel={event=>{event.preventDefault();close()}} onClick={event=>{if(event.target===event.currentTarget)close()}}>
 <div className="record-dialog-head"><h2 id="record-detail-title">策略详情与历史</h2><button className="button ghost" autoFocus onClick={close}>关闭</button></div><div className="record-dialog-body">
   <p>{detail.statement_version?.record.statement.text_zh||detail.text}</p>
   <dl className="record-metadata"><dt>来源</dt><dd>{detail.source_repo||'手工'} · {detail.source_path||'未定位'} · {detail.source_commit||'未固定 commit'}</dd><dt>来源核验</dt><dd>{detail.statement_version?.record.statement.evidence_state==='verified'||!detail.statement_version&&detail.source_verified?'固定 commit 原文已核验':'原文未核验'}</dd><dt>指令来源层</dt><dd>{detail.execution_layer}</dd>{detail.statement_version&&<><dt>内容 / 主题</dt><dd>{contentNames[detail.statement_version.record.statement.content_type]} · {detail.statement_version.record.statement.topics.join(', ')||'—'}</dd></>}</dl>
   {detail.raw_url&&<a className="source-link" href={detail.raw_url} target="_blank" rel="noreferrer">查看固定来源 ↗</a>}
   <h3>版本与审核历史</h3><p>当前{detail.statement_version?'语句':'目录'}版本 v{detail.statement_version?.version||detail.revision} · <Status value={detail.status}/></p><p className="field-note">创建：{when(detail.created_at)}{detail.reviewed_at?' · 审核：'+when(detail.reviewed_at):''}</p>{detail.statement_versions.length?detail.statement_versions.map(v=><details key={v.id} className="revision-entry"><summary>语句 v{v.version} · {states[v.review_status]||v.review_status} · {when(v.created_at)}</summary><p>{v.record.statement.text_zh||v.record.statement.text_original}</p><blockquote>{v.record.statement.source_quote}</blockquote></details>):<p className="field-note">本条为原句目录记录，尚无转换语句版本。</p>}
   {detail.revisions.map(v=><details className="revision-entry" key={v.id}><summary>修改前版本 v{v.revision} · {v.actor} · {when(v.created_at)}</summary><p>{v.snapshot.text}</p></details>)}

   {detail.artifacts.length>0&&<><h3>DSL 与加载历史</h3>{detail.artifacts.map(a=><details key={a.id} className="revision-entry"><summary>语句 v{a.statement_version} / DSL v{a.version} · {states[a.review_status]} · {states[a.compile_state]}</summary><ArtifactPreview artifact={a}/></details>)}</>}

 </div>
 </dialog>;
}

export default function StrategyRecords({active,statusFilter,api,post,tasks,busy,action,notify,selectTask,reloadHistory,onTranslate}){
 const [page,setPage]=useState({items:[],total:0}),[offset,setOffset]=useState(0);
 const [query,setQuery]=useState(''),[category,setCategory]=useState(''),[scope,setScope]=useState(''),[repository,setRepository]=useState(''),[archived,setArchived]=useState('active'),[sourceKind,setSourceKind]=useState('');
 const [editor,setEditor]=useState(null),[detail,setDetail]=useState(null),[chosen,setChosen]=useState({});
 const [preparing,setPreparing]=useState(null),[instructionLayer,setInstructionLayer]=useState('');
 const [targetTask,setTargetTask]=useState(''),[bundle,setBundle]=useState(null);
 const [completeness,setCompleteness]=useState(''),[adaptation,setAdaptation]=useState(''),[loadable,setLoadable]=useState('');
 const [adapting,setAdapting]=useState(null),[adaptTask,setAdaptTask]=useState(''),[adaptTargets,setAdaptTargets]=useState(''),[adaptAllowed,setAdaptAllowed]=useState(''),[adaptNote,setAdaptNote]=useState('');
 const [loaded,setLoaded]=useState(false);
 const status=statusFilter;
 const filtering=query||sourceKind||category||scope||repository||instructionLayer||completeness||adaptation||loadable||archived!=='active';
 useEffect(()=>setOffset(0),[status]);
 const detailTrigger=useRef(null);
 const request=useRef(0);
 const load=useCallback(async()=>{
  const sequence=++request.current;
  const params=new URLSearchParams({completeness,adaptation,loadable,q:query,source_kind:sourceKind,category,context_scope:scope,execution_layer:instructionLayer,source_repo:repository,status,archived,limit:String(pageSize),offset:String(offset)});
  const data=await api('/api/history/records?'+params);
  if(sequence!==request.current)return;
  setPage(data);setLoaded(true);
  if(offset>0&&offset>=data.total)setOffset(Math.max(0,Math.floor((data.total-1)/pageSize)*pageSize));
 },[api,query,category,scope,instructionLayer,repository,status,archived,offset,sourceKind,completeness,adaptation,loadable]);
 useEffect(()=>{
  if(!active)return;
  load().catch(e=>notify(e.message));
  const timer=setInterval(()=>load().catch(()=>{}),5000);
  return()=>{request.current++;clearInterval(timer)};
 },[active,load,notify]);
 const run=fn=>action(async()=>{await fn();await load();await reloadHistory()});
 const filter=(setter,value)=>{setter(value);setOffset(0)};
 const inspect=(row,trigger)=>{
  detailTrigger.current=trigger;
  return action(async()=>setDetail(await api('/api/history/records/'+row.id)));
 };
 const draft=row=>{
  const v=row.statement_version;
  if(v){
   const s=v.record.statement;
   setEditor({id:row.id,statementId:v.id,version:v.version,text:s.text_original,text_zh:s.text_zh,text_en:s.text_en,content_type:s.content_type,policy_kind:s.policy_kind,topics:s.topics.join(', '),category:s.enforcement_level,context_scope:s.context_requirement});
  }else setEditor({...emptyDraft,...row});
 };
 const save=()=>run(async()=>{
  if(editor.statementId){
   await post('/api/history/statements/'+editor.statementId+'/revisions',{statement:{text_original:editor.text,text_zh:editor.text_zh,text_en:editor.text_en,content_type:editor.content_type,policy_kind:editor.policy_kind,topics:editor.topics.split(/[,，]/).map(x=>x.trim()).filter(Boolean),enforcement_level:editor.category,context_requirement:editor.context_scope}});
  }else{
   const body={text:editor.text,category:editor.category,context_scope:editor.context_scope,execution_layer:editor.execution_layer,};
   if(editor.id)await api('/api/strategies/'+editor.id,{method:'PATCH',body:JSON.stringify(body)});
   else {await post('/api/strategies',{...body,source_url:editor.source_url||null});setSourceKind('manual');setOffset(0)}
  }
  setEditor(null);setDetail(null);notify('已保存新版本，进入待审核');
 });
 const review=(row,decision)=>run(async()=>{
  const v=row.statement_version;
  await post(v?'/api/history/statements/'+v.id+'/review':'/api/strategies/'+row.id+'/review',{decision,});
  notify(decision==='approve'?'语句版本已通过':'语句已拒绝');
 });
 const archive=row=>run(async()=>{
  await api('/api/strategies/'+row.id+'',{method:'DELETE'});
  setChosen(values=>{const next={...values};delete next[row.id];return next});setDetail(null);setBundle(null);notify('已归档，可恢复');
 });
 const restore=row=>run(async()=>{await post('/api/strategies/'+row.id+'/restore');notify('已恢复记录')});
 const choose=(row,id)=>{
  const artifact=row.artifacts.find(a=>a.id===id);
  if(!artifact?.eligible||row.is_archived)return;
  setChosen(values=>({...values,[row.id]:{artifactId:artifact.id,statementVersion:artifact.statement_version,artifactVersion:artifact.version,text:artifact.record.statement.text_zh||artifact.record.statement.text_original,record:artifact.record}}));
  setBundle(null);
 };
 const unchoose=id=>{setChosen(values=>{const next={...values};delete next[id];return next});setBundle(null)};
 const selected=Object.entries(chosen);
 const readyTasks=tasks.filter(t=>['prepared','policy_review','approved'].includes(t.status)&&selected.every(([,a])=>a.record.origin.repository===t.repo&&a.record.origin.commit===t.commit_sha&&(!a.record.resolved_context.task_id||a.record.resolved_context.task_id===t.id)));
 const targetEligible=readyTasks.some(t=>t.id===targetTask);
 const build=()=>run(async()=>{
  const result=await post('/api/tasks/'+targetTask+'/policy',{artifact_version_ids:selected.map(([,x])=>x.artifactId),settings:{}});
  setBundle({...result,task_id:targetTask,status:'pending_review'});notify('任务策略包已生成');
 });
 const approve=()=>run(async()=>{await post('/api/tasks/'+bundle.task_id+'/versions/'+bundle.version+'/approve',{decision:'approve',});setBundle({...bundle,status:'approved'});notify('任务策略包已批准')});
 const launch=()=>run(async()=>{const receipt=await post('/api/tasks/'+bundle.task_id+'/launch');setBundle({...bundle,status:'loaded',receipt});notify('已绑定 Domain '+receipt.domain_id)});
 return <div hidden={!active} id="records-status-panel" role="tabpanel" aria-labelledby={'record-status-'+(status||'all')} className="strategy-records">
  <div className="records-heading"><span className="row-count">{page.total>0?page.total+' 条策略记录':'策略记录'}</span><button className="button primary" disabled={busy} onClick={()=>setEditor({...emptyDraft})}>＋ 新增策略</button></div>
  {editor&&<section className="panel strategy-editor"><div className="panel-head"><h2>{editor.id?'编辑策略':'新增策略'}{editor.statementId?' · 语句 v'+editor.version:''}</h2><button className="button ghost" onClick={()=>setEditor(null)}>取消</button></div>
   <label>策略内容<textarea rows="4" value={editor.text} onChange={e=>setEditor({...editor,text:e.target.value})}/></label>
   {editor.statementId&&<div className="strategy-editor-grid"><label>中文显示<textarea rows="3" value={editor.text_zh} onChange={e=>setEditor({...editor,text_zh:e.target.value})}/></label><label>英文译文<textarea rows="3" value={editor.text_en} onChange={e=>setEditor({...editor,text_en:e.target.value})}/></label><label>内容类型<select value={editor.content_type} onChange={e=>setEditor({...editor,content_type:e.target.value})}>{Object.entries(contentNames).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select></label><label>规则性质<select value={editor.policy_kind} onChange={e=>setEditor({...editor,policy_kind:e.target.value})}><option value="constraint">约束</option><option value="instruction">指令</option><option value="preference">偏好</option><option value="none">无</option></select></label><label>主题<input value={editor.topics} onChange={e=>setEditor({...editor,topics:e.target.value})}/></label></div>}
   <div className="strategy-editor-grid"><label>执行层级<select value={editor.category} onChange={e=>setEditor({...editor,category:e.target.value})}>{(editor.statementId?['semantic_only','content','per_event','cross_event','not_applicable']:['semantic','content','per-event','cross-event','not-applicable']).map(value=><option key={value} value={value}>{levelNames[value]}</option>)}</select></label><label>上下文范围<select value={editor.context_scope} onChange={e=>setEditor({...editor,context_scope:e.target.value})}>{(editor.statementId?['self_contained','project','task','not_applicable']:['self-contained','project','task','not-applicable']).map(value=><option key={value} value={value}>{scopeNames[value]}</option>)}</select></label>{!editor.id&&<label>来源链接（可选）<input value={editor.source_url} onChange={e=>setEditor({...editor,source_url:e.target.value})} placeholder="https://…"/></label>}</div>
   <button className="button primary" disabled={busy||editor.text.trim().length<5} onClick={save}>保存并进入审核</button>
  </section>}
  {adapting&&<section className="panel history-form"><div className="panel-head"><h2>创建适配新版本</h2><button className="button ghost" onClick={()=>setAdapting(null)}>取消</button></div><p>原记录保留。输入当前任务参数，经后端核验后生成新版本，再进行二审、编译和最终审核。</p><label>适配任务<select value={adaptTask} onChange={e=>setAdaptTask(e.target.value)}><option value="">选择同仓库 / commit 的未启动任务</option>{tasks.filter(t=>['prepared','policy_review','approved'].includes(t.status)&&t.repo===adapting.record.origin.repository&&t.commit_sha===adapting.record.origin.commit).map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label><label>策略操作对象（仓库相对路径，每行一个）<textarea rows="2" value={adaptTargets} onChange={e=>setAdaptTargets(e.target.value)}/></label><label>允许修改的子目录（可选）<textarea rows="2" value={adaptAllowed} onChange={e=>setAdaptAllowed(e.target.value)}/></label><label>参数与范围说明<textarea rows="2" value={adaptNote} onChange={e=>setAdaptNote(e.target.value)}/></label><button className="button primary" disabled={busy||!adaptTask} onClick={()=>run(async()=>{const result=await post('/api/history/statements/'+adapting.id+'/revisions',{resolved_context:{task_id:adaptTask,target_paths:adaptTargets.split(/[\n,]/).map(x=>x.trim()).filter(Boolean),allowed_paths:adaptAllowed.split(/[\n,]/).map(x=>x.trim()).filter(Boolean),context_note:adaptNote}});setAdapting(null);onTranslate(result.id);notify('已创建适配新版本，继续二审与候选生成')})}>创建新版本并重新生成</button></section>}
  {preparing&&<PolicyInputForm key={preparing.id} record={preparing} tasks={tasks} post={post} busy={busy} action={action} onCancel={()=>setPreparing(null)} onSaved={async result=>{setPreparing(null);await load();await reloadHistory();onTranslate(result.id);notify('已进入完整性二审与候选生成')}}/>}
  {(page.total>0||filtering)&&<><div className="toolbar records-toolbar">
   <select aria-label="筛选策略来源" value={sourceKind} onChange={e=>filter(setSourceKind,e.target.value)}><option value="rq1_corpus">导入语料</option><option value="history_document">文档抽取</option><option value="manual">手工新增</option><option value="">全部策略</option></select>
   <div className="search"><span>⌕</span><input value={query} onChange={e=>filter(setQuery,e.target.value)} placeholder="搜索策略内容或文件路径" aria-label="搜索策略记录"/></div>
  </div>

     <details className="console-advanced-filters"><summary>高级筛选{filtering?' · 已启用筛选':''}</summary>  <div className="record-primary-filters"><label>执行层级<select aria-label="筛选执行层级" value={category} onChange={e=>filter(setCategory,e.target.value)}><option value="">全部层级</option>{['semantic','content','per-event','cross-event','not-applicable'].map(value=><option value={value} key={value}>{levelNames[value]}</option>)}</select></label><label>上下文范围<select aria-label="筛选上下文范围" value={scope} onChange={e=>filter(setScope,e.target.value)}><option value="">全部范围</option>{['self-contained','project','task','not-applicable'].map(value=><option value={value} key={value}>{scopeNames[value]}</option>)}</select></label></div><div className="generation-filters">{[['完整性',completeness,setCompleteness,{complete:'二审完整',needs_clarification:'待澄清',unreviewed:'未二审'}],['适配状态',adaptation,setAdaptation,{required:'需本机适配',complete:'已适配',not_required:'无需适配'}],['可加载状态',loadable,setLoadable,{yes:'可加载',no:'不可加载'}]].map(([name,value,setter,options])=><label key={name}>{name}<select aria-label={'筛选记录'+name} value={value} onChange={e=>filter(setter,e.target.value)}><option value="">全部</option>{Object.entries(options).map(([key,title])=><option key={key} value={key}>{title}</option>)}</select></label>)}</div></details>
  <details className="records-more-filters"><summary>来源与归档筛选</summary><div className="toolbar records-toolbar">
   <select aria-label="筛选指令来源层" value={instructionLayer} onChange={e=>filter(setInstructionLayer,e.target.value)}><option value="">全部指令来源层</option><option value="repository_instruction">仓库指令</option><option value="manual_instruction">手工指令</option><option value="llm_candidate">文档抽取候选</option></select>
   <input className="repo-filter" aria-label="筛选仓库" value={repository} onChange={e=>filter(setRepository,e.target.value)} placeholder="仓库，如 owner/repo"/>
   <select aria-label="筛选归档状态" value={archived} onChange={e=>filter(setArchived,e.target.value)}><option value="active">有效策略</option><option value="archived">已归档</option><option value="all">全部记录</option></select>
  </div></details>
  </>}
  {page.total>pageSize&&<div className="records-pagination"><span>{page.total?`${offset+1}–${offset+page.items.length} / ${page.total}`:'0 条记录'}</span><div className="button-row"><span className="row-count">每页 20 条</span><button className="button tiny ghost" disabled={busy||offset===0} onClick={()=>setOffset(Math.max(0,offset-pageSize))}>上一页</button><button className="button tiny ghost" disabled={busy||offset+page.items.length>=page.total} onClick={()=>setOffset(offset+pageSize)}>下一页</button></div></div>}
  {page.items.length>0?<section className="panel table-panel"><div className="table-scroll"><table className="record-table"><thead><tr><th>选择</th><th>策略语句</th><th>层级 / 范围</th><th>来源与位置</th><th>状态 / 版本</th><th>加载记录</th></tr></thead><tbody>{page.items.map(row=>{
   const latest=row.statement_version,selected=chosen[row.id];
   const s=selected?.record.statement||latest?.record.statement;
   const eligible=row.artifacts.filter(a=>a.eligible);
   const deployments=row.artifacts.flatMap(a=>a.deployments.map(d=>({...d,artifactVersion:a.version,statementVersion:a.statement_version})));
   return <tr key={row.id}>
    <td><input type="checkbox" aria-label={'选择策略 '+row.id} checked={!!selected} disabled={!!row.is_archived||(!selected&&!eligible.length)} onChange={e=>e.target.checked?choose(row,eligible[0].id):unchoose(row.id)}/></td>
    <td className="record-text"><button className="record-open" disabled={busy} onClick={event=>inspect(row,event.currentTarget)}>详情 / 历史</button><div>{s?.text_zh||s?.text_original||row.text}</div>{row.adaptation==='required'&&<small className="tag warn">需本机适配 · 不能加载</small>}<small>{row.source_kind==='manual'?'手工新增':row.source_kind==='rq1_corpus'?'导入语料':'文档抽取'}{selected?' · 已选语句 v'+selected.statementVersion:''}</small><div className="record-actions">{!row.is_archived&&<>{row.status==='pending_review'&&<><button className="button tiny primary" disabled={busy||(row.review_blockers||[]).length>0||!!latest&&latest.record.statement.evidence_state!=='verified'} onClick={()=>review(row,'approve')}>通过</button><button className="button tiny ghost" disabled={busy} onClick={()=>review(row,'reject')}>拒绝</button></>}<button className="button tiny ghost" disabled={busy} onClick={()=>draft(row)}>编辑</button>{!latest&&['rq1_corpus','manual'].includes(row.source_kind)&&<button className="button tiny ghost" disabled={busy||row.source_kind==='rq1_corpus'&&!row.source_verified} onClick={()=>setPreparing(row)}>准备转换输入</button>}{latest&&<button className="button tiny ghost" disabled={busy} onClick={()=>onTranslate(latest.id)}>二审 / 生成</button>}{latest&&row.adaptation==='required'&&<button className="button tiny ghost" disabled={busy} onClick={()=>{setAdapting(latest);setAdaptTask('');setAdaptTargets('');setAdaptAllowed('');setAdaptNote('')}}>适配新版本</button>}<button className="button tiny ghost" disabled={busy} onClick={()=>archive(row)}>归档</button></>}{!!row.is_archived&&<button className="button tiny primary" disabled={busy} onClick={()=>restore(row)}>恢复</button>}</div></td>
    <td data-label="层级 / 范围">{levelNames[s?.enforcement_level||row.category]||row.category}<small>{scopeNames[s?.context_requirement||row.context_scope]||row.context_scope}</small></td>
    <td data-label="来源与位置">{row.source_repo||'手工来源'}{row.source_path&&<small>{row.source_path+(s?.line_start||row.line_start?':'+(s?.line_start||row.line_start):'')}</small>}</td>
    <td data-label="状态 / 版本">{row.is_archived?<span className="tag">已归档</span>:<Status value={selected?row.artifacts.find(a=>a.id===selected.artifactId)?.statement_review_status:row.status}/>}<small>{latest?'语句':'目录'} v{selected?.statementVersion||latest?.version||row.revision}</small>{eligible.length>0?<select className="artifact-choice" aria-label={'DSL 版本 '+row.id} value={selected?.artifactId||''} disabled={!!row.is_archived||busy} onChange={e=>e.target.value?choose(row,e.target.value):unchoose(row.id)}><option value="">选择 DSL 版本</option>{eligible.map(a=><option key={a.id} value={a.id}>语句 v{a.statement_version} / DSL v{a.version} · {short(a.id)}</option>)}</select>:<small>{row.artifacts.length?<Status value={row.artifacts[0].compile_state}/>:'未生成 DSL'}</small>}</td>
    <td data-label="加载记录">{deployments.length?deployments.slice(0,2).map(d=><div className="record-load" key={d.id+'-'+d.artifactVersion}><Status value={d.status}/><small>{d.task_name}</small><small>Domain {d.domain_id||'—'} · 策略包 v{d.task_policy_version}</small></div>):'未加载'}</td>
   </tr>;
  })}{!page.items.length&&<tr><td colSpan="6" className="empty-row">暂无符合筛选条件的策略记录。</td></tr>}</tbody></table></div></section>:<p className="task-empty" role={loaded?undefined:'status'}>{loaded?'暂无符合筛选条件的策略记录。':'正在读取策略记录…'}</p>}
  {detail&&<RecordDetails detail={detail} onClose={()=>setDetail(null)} returnFocus={()=>{if(detailTrigger.current?.isConnected)detailTrigger.current.focus()}}/>}
  {selected.length>0&&<section className="panel history-form records-loader"><div className="panel-head"><h2>加载选中策略</h2><span>{selected.length} 个 DSL 版本</span></div>
   {selected.length>0&&<div className="selected-records">{selected.map(([id,a])=><div key={id}><span>{a.text}</span><small>语句 v{a.statementVersion} / DSL v{a.artifactVersion} · {short(a.artifactId)}</small><button className="button tiny ghost" aria-label={'移除 '+id} onClick={()=>unchoose(id)}>移除</button></div>)}</div>}
   <label>目标任务<select value={targetTask} onChange={e=>{setTargetTask(e.target.value);setBundle(null)}}><option value="">选择尚未启动的任务</option>{readyTasks.map(t=><option key={t.id} value={t.id}>{t.name} · {short(t.id)}</option>)}</select></label>
   {selected.length>0&&!readyTasks.length&&<p className="field-note">没有适用的未启动任务，需生成适配新版本后重新审核。</p>}
   <div className="button-row"><button className="button primary" disabled={busy||!selected.length||!targetEligible} onClick={build}>生成任务策略包（{selected.length}）</button>{targetTask&&<button className="button ghost" onClick={()=>selectTask(targetTask)}>查看任务</button>}</div>
   {bundle&&<div className="bundle-preview"><b>任务策略包 v{bundle.version}</b> <Status value={bundle.compile_state}/> <Status value={bundle.status}/><pre>{bundle.dsl_text}</pre>{bundle.diagnostic&&<p>{bundle.diagnostic}</p>}<div className="button-row"><button className="button success" disabled={busy||bundle.status!=='pending_review'||bundle.compile_state!=='compiled'} onClick={approve}>批准策略包</button><button className="button primary" disabled={busy||bundle.status!=='approved'} onClick={launch}>加载并启动 DSH</button></div>{bundle.receipt&&<pre>{JSON.stringify(bundle.receipt,null,2)}</pre>}</div>}
  </section>}
 </div>;
}
