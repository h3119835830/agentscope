import React,{useCallback,useEffect,useRef,useState} from 'react';
import ArtifactPreview from './PolicyArtifactPreview.jsx';

const pageSize=20;
const levelNames={'semantic':'语义规则','semantic-only':'语义规则','semantic_only':'语义规则',content:'内容规则','per-event':'单事件规则',per_event:'单事件规则','cross-event':'跨事件规则',cross_event:'跨事件规则','not-applicable':'不适用',not_applicable:'不适用'};
const scopeNames={'self-contained':'通用',self_contained:'通用',project:'项目 / 仓库',task:'任务',not_applicable:'不适用','not-applicable':'不适用'};
const contentNames={policy:'规范',mixed:'混合',description:'描述',uncertain:'待确认'};
const emptyDraft={text:'',category:'semantic',context_scope:'self-contained',execution_layer:'repository_instruction',source_url:''};
const short=value=>value?.slice(0,12)||'—';
const when=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—';
const states={pending_review:'待审核',approved:'已通过候选',rejected:'已拒绝',compiled:'已编译',loaded:'已加载',load_failed:'加载失败',requires_context:'待绑定上下文',unsupported:'不支持',partial:'部分支持',not_checked:'未编译',compile_failed:'编译失败',invalid_candidate:'片段格式无效',checking:'编译中'};
function Status({value}){return <span className={'tag '+(['approved','compiled','loaded'].includes(value)?'good':['rejected','load_failed','compile_failed','invalid_candidate'].includes(value)?'bad':'warn')}>{states[value]||value}</span>}

export default function StrategyRecords({active,api,post,tasks,busy,action,notify,selectTask,reloadHistory,onTranslate}){
 const [page,setPage]=useState({items:[],total:0}),[offset,setOffset]=useState(0);
 const [query,setQuery]=useState(''),[category,setCategory]=useState(''),[scope,setScope]=useState(''),[repository,setRepository]=useState(''),[status,setStatus]=useState(''),[archived,setArchived]=useState('active'),[sourceKind,setSourceKind]=useState('rq1_corpus');
 const [editor,setEditor]=useState(null),[detail,setDetail]=useState(null),[chosen,setChosen]=useState({});
 const [targetTask,setTargetTask]=useState(''),[bundle,setBundle]=useState(null);
 const request=useRef(0);
 const load=useCallback(async()=>{
  const sequence=++request.current;
  const params=new URLSearchParams({q:query,source_kind:sourceKind,category,context_scope:scope,source_repo:repository,status,archived,limit:String(pageSize),offset:String(offset)});
  const data=await api('/api/history/records?'+params);
  if(sequence!==request.current)return;
  setPage(data);
  if(offset>0&&offset>=data.total)setOffset(Math.max(0,Math.floor((data.total-1)/pageSize)*pageSize));
 },[api,query,category,scope,repository,status,archived,offset,sourceKind]);
 useEffect(()=>{
  if(!active)return;
  load().catch(e=>notify(e.message));
  const timer=setInterval(()=>load().catch(()=>{}),5000);
  return()=>{request.current++;clearInterval(timer)};
 },[active,load,notify]);
 const run=fn=>action(async()=>{await fn();await load();await reloadHistory()});
 const filter=(setter,value)=>{setter(value);setOffset(0)};
 const inspect=row=>run(async()=>setDetail(await api('/api/history/records/'+row.id)));
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
   const body={text:editor.text,category:editor.category,context_scope:editor.context_scope,execution_layer:editor.execution_layer,actor:'研究者'};
   if(editor.id)await api('/api/strategies/'+editor.id,{method:'PATCH',body:JSON.stringify(body)});
   else {await post('/api/strategies',{...body,source_url:editor.source_url||null});setSourceKind('manual');setOffset(0)}
  }
  setEditor(null);setDetail(null);notify('已保存新版本，进入待审核');
 });
 const review=(row,decision)=>run(async()=>{
  const v=row.statement_version;
  await post(v?'/api/history/statements/'+v.id+'/review':'/api/strategies/'+row.id+'/review',{decision,reviewed_by:'研究者'});
  notify(decision==='approve'?'语句版本已通过':'语句已拒绝');
 });
 const archive=row=>run(async()=>{
  await api('/api/strategies/'+row.id+'?actor='+encodeURIComponent('研究者'),{method:'DELETE'});
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
 const approve=()=>run(async()=>{await post('/api/tasks/'+bundle.task_id+'/versions/'+bundle.version+'/approve',{decision:'approve',reviewed_by:'研究者'});setBundle({...bundle,status:'approved'});notify('任务策略包已批准')});
 const launch=()=>run(async()=>{const receipt=await post('/api/tasks/'+bundle.task_id+'/launch');setBundle({...bundle,status:'loaded',receipt});notify('已绑定 Domain '+receipt.domain_id)});
 return <div hidden={!active} className="strategy-records">
  <div className="records-heading"><span className="row-count">{page.total} 条策略记录</span><button className="button primary" disabled={busy} onClick={()=>setEditor({...emptyDraft})}>＋ 新增策略</button></div>
  {editor&&<section className="panel strategy-editor"><div className="panel-head"><h2>{editor.id?'编辑策略':'新增策略'}{editor.statementId?' · 语句 v'+editor.version:''}</h2><button className="button ghost" onClick={()=>setEditor(null)}>取消</button></div>
   <label>策略内容<textarea rows="4" value={editor.text} onChange={e=>setEditor({...editor,text:e.target.value})}/></label>
   {editor.statementId&&<div className="strategy-editor-grid"><label>中文显示<textarea rows="3" value={editor.text_zh} onChange={e=>setEditor({...editor,text_zh:e.target.value})}/></label><label>英文译文<textarea rows="3" value={editor.text_en} onChange={e=>setEditor({...editor,text_en:e.target.value})}/></label><label>内容类型<select value={editor.content_type} onChange={e=>setEditor({...editor,content_type:e.target.value})}>{Object.entries(contentNames).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select></label><label>规则性质<select value={editor.policy_kind} onChange={e=>setEditor({...editor,policy_kind:e.target.value})}><option value="constraint">约束</option><option value="instruction">指令</option><option value="preference">偏好</option><option value="none">无</option></select></label><label>主题<input value={editor.topics} onChange={e=>setEditor({...editor,topics:e.target.value})}/></label></div>}
   <div className="strategy-editor-grid"><label>执行层级<select value={editor.category} onChange={e=>setEditor({...editor,category:e.target.value})}>{(editor.statementId?['semantic_only','content','per_event','cross_event','not_applicable']:['semantic','content','per-event','cross-event','not-applicable']).map(value=><option key={value} value={value}>{levelNames[value]}</option>)}</select></label><label>上下文范围<select value={editor.context_scope} onChange={e=>setEditor({...editor,context_scope:e.target.value})}>{(editor.statementId?['self_contained','project','task','not_applicable']:['self-contained','project','task','not-applicable']).map(value=><option key={value} value={value}>{scopeNames[value]}</option>)}</select></label>{!editor.id&&<label>来源链接（可选）<input value={editor.source_url} onChange={e=>setEditor({...editor,source_url:e.target.value})} placeholder="https://…"/></label>}</div>
   <button className="button primary" disabled={busy||editor.text.trim().length<5} onClick={save}>保存并进入审核</button>
  </section>}
  <div className="toolbar records-toolbar">
   <select aria-label="筛选策略来源" value={sourceKind} onChange={e=>filter(setSourceKind,e.target.value)}><option value="rq1_corpus">RQ1 策略</option><option value="history_document">文档抽取</option><option value="manual">手工新增</option><option value="">全部策略</option></select>
   <div className="search"><span>⌕</span><input value={query} onChange={e=>filter(setQuery,e.target.value)} placeholder="搜索策略内容或文件路径" aria-label="搜索策略记录"/></div>
   <select aria-label="筛选执行层级" value={category} onChange={e=>filter(setCategory,e.target.value)}><option value="">全部层级</option>{['semantic','content','per-event','cross-event','not-applicable'].map(value=><option value={value} key={value}>{levelNames[value]}</option>)}</select>
   <select aria-label="筛选上下文范围" value={scope} onChange={e=>filter(setScope,e.target.value)}><option value="">全部范围</option>{['self-contained','project','task','not-applicable'].map(value=><option value={value} key={value}>{scopeNames[value]}</option>)}</select>
   <input className="repo-filter" aria-label="筛选仓库" value={repository} onChange={e=>filter(setRepository,e.target.value)} placeholder="仓库，如 owner/repo"/>
   <select aria-label="筛选记录状态" value={status} onChange={e=>filter(setStatus,e.target.value)}><option value="">全部状态</option><option value="pending_review">待审核</option><option value="approved">已通过候选</option><option value="rejected">已拒绝</option><option value="loaded">已加载</option></select>
   <select aria-label="筛选归档状态" value={archived} onChange={e=>filter(setArchived,e.target.value)}><option value="active">有效策略</option><option value="archived">已归档</option><option value="all">全部记录</option></select>
  </div>
  <div className="records-pagination"><span>{page.total?`${offset+1}–${offset+page.items.length} / ${page.total}`:'0 条记录'}</span><div className="button-row"><span className="row-count">每页 20 条</span><button className="button tiny ghost" disabled={busy||offset===0} onClick={()=>setOffset(Math.max(0,offset-pageSize))}>上一页</button><button className="button tiny ghost" disabled={busy||offset+page.items.length>=page.total} onClick={()=>setOffset(offset+pageSize)}>下一页</button></div></div>
  <section className="panel table-panel"><div className="table-scroll"><table className="record-table"><thead><tr><th>选择</th><th>策略语句</th><th>层级 / 范围</th><th>来源与位置</th><th>状态 / 版本</th><th>加载记录</th><th>操作</th></tr></thead><tbody>{page.items.map(row=>{
   const latest=row.statement_version,selected=chosen[row.id];
   const s=selected?.record.statement||latest?.record.statement;
   const eligible=row.artifacts.filter(a=>a.eligible);
   const deployments=row.artifacts.flatMap(a=>a.deployments.map(d=>({...d,artifactVersion:a.version,statementVersion:a.statement_version})));
   return <tr key={row.id}>
    <td><input type="checkbox" aria-label={'选择策略 '+row.id} checked={!!selected} disabled={!!row.is_archived||(!selected&&!eligible.length)} onChange={e=>e.target.checked?choose(row,eligible[0].id):unchoose(row.id)}/></td>
    <td className="record-text">{s?.text_zh||s?.text_original||row.text}<small>{row.source_kind==='manual'?'手工新增':row.source_kind==='rq1_corpus'?'RQ1 策略':'文档抽取'}{selected?' · 已选语句 v'+selected.statementVersion:''}</small></td>
    <td>{levelNames[s?.enforcement_level||row.category]||row.category}<small>{scopeNames[s?.context_requirement||row.context_scope]||row.context_scope}</small></td>
    <td>{row.source_repo||'手工来源'}<small>{row.source_path?row.source_path+(s?.line_start||row.line_start?':'+(s?.line_start||row.line_start):''):'未定位到原始行'}</small></td>
    <td>{row.is_archived?<span className="tag">已归档</span>:<Status value={selected?row.artifacts.find(a=>a.id===selected.artifactId)?.statement_review_status:row.status}/>}<small>{latest?'语句':'目录'} v{selected?.statementVersion||latest?.version||row.revision}</small>{eligible.length>0?<select className="artifact-choice" aria-label={'DSL 版本 '+row.id} value={selected?.artifactId||''} disabled={!!row.is_archived||busy} onChange={e=>e.target.value?choose(row,e.target.value):unchoose(row.id)}><option value="">选择 DSL 版本</option>{eligible.map(a=><option key={a.id} value={a.id}>语句 v{a.statement_version} / DSL v{a.version} · {short(a.id)}</option>)}</select>:<small>{row.artifacts.length?<Status value={row.artifacts[0].compile_state}/>:'未生成 DSL'}</small>}</td>
    <td>{deployments.length?deployments.slice(0,2).map(d=><div className="record-load" key={d.id+'-'+d.artifactVersion}><Status value={d.status}/><small>{d.task_name}</small><small>Domain {d.domain_id||'—'} · 策略包 v{d.task_policy_version}</small></div>):'未加载'}</td>
    <td><div className="record-actions">{!row.is_archived&&<>{row.status==='pending_review'&&<><button className="button tiny primary" disabled={busy||!!latest&&latest.record.statement.evidence_state!=='verified'} onClick={()=>review(row,'approve')}>通过</button><button className="button tiny ghost" disabled={busy} onClick={()=>review(row,'reject')}>拒绝</button></>}<button className="button tiny ghost" disabled={busy} onClick={()=>draft(row)}>编辑</button>{latest?.review_status==='approved'&&<button className="button tiny ghost" disabled={busy} onClick={()=>onTranslate(latest.id)}>转 DSL</button>}<button className="button tiny ghost" disabled={busy} onClick={()=>archive(row)}>归档</button></>}{!!row.is_archived&&<button className="button tiny primary" disabled={busy} onClick={()=>restore(row)}>恢复</button>}<button className="button tiny ghost" disabled={busy} onClick={()=>inspect(row)}>详情 / 历史</button></div></td>
   </tr>;
  })}{!page.items.length&&<tr><td colSpan="7" className="empty-row">暂无符合筛选条件的策略记录。</td></tr>}</tbody></table></div></section>
  {detail&&<section className="panel history-detail record-detail"><div className="panel-head"><h2>策略详情与历史</h2><button className="button ghost" onClick={()=>setDetail(null)}>关闭</button></div>
   <p>{detail.statement_version?.record.statement.text_zh||detail.text}</p>
   <dl className="record-metadata"><dt>来源</dt><dd>{detail.source_repo||'手工'} · {detail.source_path||'未定位'} · {detail.source_commit||'未固定 commit'}</dd><dt>来源核验</dt><dd>{detail.statement_version?.record.statement.evidence_state==='verified'||!detail.statement_version&&detail.source_verified?'固定 commit 原文已核验':'原文未核验'}</dd><dt>指令来源层</dt><dd>{detail.execution_layer}</dd>{detail.statement_version&&<><dt>内容 / 主题</dt><dd>{contentNames[detail.statement_version.record.statement.content_type]} · {detail.statement_version.record.statement.topics.join(', ')||'—'}</dd></>}</dl>
   {detail.raw_url&&<a className="source-link" href={detail.raw_url} target="_blank" rel="noreferrer">查看固定来源 ↗</a>}
   <h3>语句版本</h3>{detail.statement_versions.length?detail.statement_versions.map(v=><details key={v.id} className="revision-entry"><summary>语句 v{v.version} · {states[v.review_status]||v.review_status} · {when(v.created_at)}</summary><p>{v.record.statement.text_zh||v.record.statement.text_original}</p><blockquote>{v.record.statement.source_quote}</blockquote><small>版本 ID {v.id}<br/>内容 hash {v.content_sha256}</small></details>):<p>目录版本 v{detail.revision}</p>}
   {detail.revisions.map(v=><details className="revision-entry" key={v.id}><summary>修改前版本 v{v.revision} · {v.actor} · {when(v.created_at)}</summary><p>{v.snapshot.text}</p></details>)}
   <h3>DSL 与加载历史</h3>{detail.artifacts.length?detail.artifacts.map(a=><details key={a.id} className="revision-entry"><summary>语句 v{a.statement_version} / DSL v{a.version} · {states[a.review_status]} · {states[a.compile_state]}</summary><ArtifactPreview artifact={a}/></details>):<p>未生成 DSL</p>}
  </section>}
  <section className="panel history-form records-loader"><div className="panel-head"><h2>加载选中策略</h2><span>{selected.length} 个 DSL 版本</span></div>
   {selected.length>0&&<div className="selected-records">{selected.map(([id,a])=><div key={id}><span>{a.text}</span><small>语句 v{a.statementVersion} / DSL v{a.artifactVersion} · {short(a.artifactId)}</small><button className="button tiny ghost" aria-label={'移除 '+id} onClick={()=>unchoose(id)}>移除</button></div>)}</div>}
   <label>目标任务<select value={targetTask} onChange={e=>{setTargetTask(e.target.value);setBundle(null)}}><option value="">选择尚未启动的任务</option>{readyTasks.map(t=><option key={t.id} value={t.id}>{t.name} · {short(t.id)}</option>)}</select></label>
   {selected.length>0&&!readyTasks.length&&<p className="field-note">没有适用的未启动任务，可在“策略转 DSL”重新绑定任务。</p>}
   <div className="button-row"><button className="button primary" disabled={busy||!selected.length||!targetEligible} onClick={build}>生成任务策略包（{selected.length}）</button>{targetTask&&<button className="button ghost" onClick={()=>selectTask(targetTask)}>查看任务</button>}</div>
   {bundle&&<div className="bundle-preview"><b>任务策略包 v{bundle.version}</b> <Status value={bundle.compile_state}/> <Status value={bundle.status}/><pre>{bundle.dsl_text}</pre>{bundle.diagnostic&&<p>{bundle.diagnostic}</p>}<div className="button-row"><button className="button success" disabled={busy||bundle.status!=='pending_review'||bundle.compile_state!=='compiled'} onClick={approve}>批准策略包</button><button className="button primary" disabled={busy||bundle.status!=='approved'} onClick={launch}>加载并启动 DSH</button></div>{bundle.receipt&&<pre>{JSON.stringify(bundle.receipt,null,2)}</pre>}</div>}
  </section>
 </div>;
}
