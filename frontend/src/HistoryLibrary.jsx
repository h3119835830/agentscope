import React, {useCallback,useEffect,useState} from 'react';
import StrategyRecords from './StrategyRecords.jsx';
import ArtifactPreview from './PolicyArtifactPreview.jsx';

const labels={queued:'排队中',running:'处理中',completed:'已完成',failed:'失败',interrupted:'已中断',
 pending_review:'待审核',approved:'已通过候选',rejected:'已拒绝',candidate:'DSL 候选',
 requires_context:'待绑定上下文',unsupported:'不支持',compiled:'已编译',compile_failed:'编译失败',
 invalid_candidate:'片段格式无效',partial:'部分支持',loaded:'已加载',load_failed:'加载失败',checking:'编译中',not_checked:'未编译'};
const status=v=><span className={'tag '+(['approved','compiled','loaded','completed'].includes(v)?'good':['failed','rejected','compile_failed','load_failed'].includes(v)?'bad':'warn')}>{labels[v]||v}</span>;
const clip=x=>x?.slice(0,12)||'—';
const recordStates=[['','全部状态'],['pending_review','待审核'],['approved','已通过候选'],['rejected','已拒绝'],['loaded','已加载']];

export default function HistoryLibrary({api,post,tasks,busy,action,notify,selectTask,moduleIndex,modules,onModuleChange}) {
 const tab=moduleIndex;
 const [recordStatus,setRecordStatus]=useState('');
 const [docs,setDocs]=useState([]),[statements,setStatements]=useState([]),
 [artifacts,setArtifacts]=useState([]),[jobs,setJobs]=useState([]);
 const [repo,setRepo]=useState('https://github.com/zeroclaw-labs/zeroclaw'),[ref,setRef]=useState('main'),[extra,setExtra]=useState('');
 const [documentIds,setDocumentIds]=useState([]),[preview,setPreview]=useState(null);
 const [q,setQ]=useState(''),[showAll,setShowAll]=useState(false),[detail,setDetail]=useState(null),[edit,setEdit]=useState('');
 const [statementId,setStatementId]=useState(''),[bindingTask,setBindingTask]=useState(''),[paths,setPaths]=useState(''),[note,setNote]=useState(''),[contextResolved,setContextResolved]=useState(false);
 const load=useCallback(async()=>{
  const [d,s,a,j]=await Promise.all([api('/api/history/documents'),api('/api/history/statements'),
    api('/api/history/artifacts'),api('/api/history/jobs')]);
  setDocs(d);setStatements(s);setArtifacts(a);setJobs(j);
 },[api]);
 useEffect(()=>{load().catch(e=>notify(e.message)); const timer=setInterval(()=>load().catch(()=>{}),5000); return()=>clearInterval(timer);},[load,notify]);
 const run=fn=>action(async()=>{await fn();await load();});
 const choose=(list,set,id,on)=>set(on?[...new Set([...list,id])]:list.filter(x=>x!==id));
 const readyTasks=tasks.filter(t=>['prepared','policy_review','approved'].includes(t.status));
 const search=r=>JSON.stringify(r).toLowerCase().includes(q.toLowerCase());
 const currentStatements=statements.filter(r=>search(r)&&(showAll||r.record.statement.content_type!=='description'));
 const approvedStatements=statements.filter(r=>r.review_status==='approved');
 const collect=()=>run(async()=>{const j=await post('/api/history/sources',{repo_url:repo,ref,additional_paths:extra.split(/[\n,]/).map(x=>x.trim()).filter(Boolean)});notify('采集已排队：'+clip(j.id));});
 const extract=()=>run(async()=>{const j=await post('/api/history/extractions',{document_ids:documentIds});notify('抽取已排队：'+clip(j.id));onModuleChange(1);});
 const reviewStatement=(id,decision)=>run(async()=>{await post('/api/history/statements/'+id+'/review',{decision,reviewed_by:'研究者'});notify(decision==='approve'?'语句版本已通过':'语句已拒绝');});
 const revise=()=>run(async()=>{const result=await post('/api/history/statements/'+detail.id+'/revisions',{statement:JSON.parse(edit)});notify('已保存新版本：'+clip(result.id));setDetail(null);});
 const translate=()=>run(async()=>{
   let id=statementId;
   if(bindingTask){
    const v=await post('/api/history/statements/'+id+'/revisions',{...(contextResolved?{statement:{uncertainties:[]}}:{}),resolved_context:{
      task_id:bindingTask,allowed_paths:paths.split(/[\n,]/).map(x=>x.trim()).filter(Boolean),context_note:note}});
    id=v.id;
    await post('/api/history/statements/'+id+'/review',{decision:'approve',reviewed_by:'研究者'});
   }
   const j=await post('/api/history/statements/'+id+'/artifacts');notify('转换已排队：'+clip(j.id));
 });
 const reviewArtifact=(id,decision)=>run(async()=>{await post('/api/history/artifacts/'+id+'/review',{decision,reviewed_by:'研究者'});notify(decision==='approve'?'DSL 版本已通过':'DSL 版本已拒绝');});
 const openStatement=r=>{setDetail(r);setEdit(JSON.stringify(r.record.statement,null,2));};

 const navigateTab=event=>{
  const keys=['ArrowLeft','ArrowRight','Home','End'];
  if(!keys.includes(event.key))return;
  event.preventDefault();
  const next=event.key==='Home'?0:event.key==='End'?modules.length-1:(tab+(event.key==='ArrowRight'?1:-1)+modules.length)%modules.length;
  onModuleChange(next);
  event.currentTarget.parentElement.children[next].focus();
 };
 const navigateRecordState=event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();
  const index=recordStates.findIndex(([value])=>value===recordStatus);
  const next=event.key==='Home'?0:event.key==='End'?recordStates.length-1:(index+(event.key==='ArrowRight'?1:-1)+recordStates.length)%recordStates.length;
  setRecordStatus(recordStates[next][0]);
  event.currentTarget.parentElement.children[next].focus();
 };
 return <div className="history-module-page">
  <div className="history-navigation">
  <nav className="history-subnav" aria-label="历史策略库二级导航">
   <div role="tablist" aria-label="历史策略库模块">{modules.map((module,index)=><button key={module.page} id={'history-tab-'+index} type="button" role="tab" aria-selected={tab===index} aria-controls="history-module-panel" tabIndex={tab===index?0:-1} className={tab===index?'active':''} onClick={()=>onModuleChange(index)} onKeyDown={navigateTab}>{module.title}</button>)}</div>
  </nav>
  {tab===3&&<nav className="history-status-subnav" aria-label="策略记录三级导航">
   <div role="tablist" aria-label="策略记录状态">{recordStates.map(([value,title])=><button key={value} id={'record-status-'+(value||'all')} type="button" role="tab" aria-selected={recordStatus===value} aria-controls="records-status-panel" tabIndex={recordStatus===value?0:-1} className={recordStatus===value?'active':''} onClick={()=>setRecordStatus(value)} onKeyDown={navigateRecordState}>{title}</button>)}</div>
  </nav>}
  </div>
  <div id="history-module-panel" role="tabpanel" aria-labelledby={'history-tab-'+tab} className="content history-library">
  {tab===0&&<>
   <section className="panel history-form"><div className="history-fields">
    <label>GitHub 仓库<input value={repo} onChange={e=>setRepo(e.target.value)}/></label>
    <label>分支 / 标签 / commit<input value={ref} onChange={e=>setRef(e.target.value)}/></label>
    <label>指定文件（每行一个，可选）<textarea rows="2" placeholder="SECURITY.md" value={extra} onChange={e=>setExtra(e.target.value)}/></label>
   </div><div className="button-row"><button className="button primary" disabled={busy||!repo||!ref} onClick={collect}>采集文档</button><button className="button ghost" disabled={busy||!documentIds.length} onClick={extract}>抽取选中文档（{documentIds.length}）</button></div></section>
   <section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>选择</th><th>文档</th><th>仓库 / commit</th><th>范围</th><th>操作</th></tr></thead><tbody>{docs.map(d=><tr key={d.id}><td><input type="checkbox" aria-label={'选择 '+d.relative_path} checked={documentIds.includes(d.id)} onChange={e=>choose(documentIds,setDocumentIds,d.id,e.target.checked)}/></td><td>{d.relative_path}<small>{d.byte_size} bytes</small></td><td>{d.repository}<small>{clip(d.commit_sha)}</small></td><td>{d.scope_path||'仓库根目录'}</td><td><button className="button tiny ghost" onClick={()=>api('/api/history/documents/'+d.id).then(setPreview).catch(e=>notify(e.message))}>预览原文</button></td></tr>)}</tbody></table>{!docs.length&&<div className="empty-box">添加仓库，采集指令文档。</div>}</div></section>
   {preview&&<section className="panel history-detail"><div className="panel-head"><b>{preview.origin.path}</b><button className="button tiny ghost" onClick={()=>setPreview(null)}>关闭</button></div><a href={preview.origin.url} target="_blank" rel="noreferrer">固定 commit 来源</a><pre>{preview.text}</pre></section>}
  </>}
  {tab===1&&<>
   <div className="toolbar"><div className="search"><input placeholder="搜索语句或来源" value={q} onChange={e=>setQ(e.target.value)}/></div><label><input type="checkbox" checked={showAll} onChange={e=>setShowAll(e.target.checked)}/> 显示描述性语句</label><span>{currentStatements.length} 个版本</span></div>
   <section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>策略语句</th><th>分类</th><th>来源</th><th>状态</th><th>操作</th></tr></thead><tbody>{currentStatements.map(r=>{const s=r.record.statement;return <tr key={r.id}><td className="strategy-text">{s.text_zh||s.text_original}<small>{s.text_original}</small>{s.text_en&&s.text_en!==s.text_original&&<small>英文：{s.text_en}</small>}</td><td>{s.content_type} / {s.policy_kind}<small>{s.enforcement_level} · {s.context_requirement}</small></td><td>{r.record.origin.path}<small>L{s.line_start}–{s.line_end} · v{r.version}</small></td><td>{status(r.review_status)}<small>{s.evidence_state==='verified'?'原文已核验':'证据未定位'}</small></td><td><div className="actions"><button className="button tiny ghost" onClick={()=>openStatement(r)}>详情 / 修订</button>{r.review_status==='pending_review'&&<><button className="button tiny primary" disabled={busy||s.evidence_state!=='verified'} onClick={()=>reviewStatement(r.id,'approve')}>通过</button><button className="button tiny ghost" disabled={busy} onClick={()=>reviewStatement(r.id,'reject')}>拒绝</button></>}</div></td></tr>})}</tbody></table>{!currentStatements.length&&<div className="empty-box">选择文档并启动抽取。</div>}</div></section>
   {detail&&<section className="panel history-detail"><div className="panel-head"><b>语句 v{detail.version}</b><button className="button tiny ghost" onClick={()=>setDetail(null)}>关闭</button></div><a href={detail.record.origin.url+'#L'+detail.record.statement.line_start} target="_blank" rel="noreferrer">查看来源</a><blockquote>{detail.record.statement.source_quote}</blockquote><label>语句、翻译与标签<textarea className="code-editor" rows="14" value={edit} onChange={e=>setEdit(e.target.value)}/></label><button className="button primary" disabled={busy} onClick={revise}>保存为待审核新版本</button></section>}
  </>}
  {tab===2&&<>
   <section className="panel history-form"><div className="history-fields">
    <label>已通过语句<select value={statementId} onChange={e=>setStatementId(e.target.value)}><option value="">选择语句版本</option>{approvedStatements.map(r=><option key={r.id} value={r.id}>{(r.record.statement.text_zh||r.record.statement.text_original).slice(0,90)} · v{r.version}</option>)}</select></label>
    <label>绑定任务（需要上下文时）<select value={bindingTask} onChange={e=>setBindingTask(e.target.value)}><option value="">暂不绑定</option>{readyTasks.map(t=><option key={t.id} value={t.id}>{t.name} · {clip(t.id)}</option>)}</select></label>
    {bindingTask&&<><label>允许修改的仓库目录（其余路径禁止修改）<textarea rows="2" value={paths} onChange={e=>setPaths(e.target.value)} placeholder="crates/zeroclaw-plugins"/></label><label>上下文说明<textarea rows="2" value={note} onChange={e=>setNote(e.target.value)} placeholder="本任务只修改指定模块；其他模块不属于任务范围"/></label></>}
   </div>{bindingTask&&<label className="inline-check"><input type="checkbox" checked={contextResolved} onChange={e=>setContextResolved(e.target.checked)}/>上述上下文已解决这条语句的待绑定参数</label>}<button className="button primary" disabled={busy||!statementId} onClick={translate}>{bindingTask?'批准上下文并生成候选':'生成伪代码 / DSL 候选'}</button></section>
   {artifacts.map(r=><section className="panel history-detail" key={r.id}><div className="panel-head"><b>DSL v{r.version} · {clip(r.id)}</b><div>{status(r.review_status)} {status(r.compile_state)}</div></div><ArtifactPreview artifact={r}/><div className="button-row">{r.review_status==='pending_review'&&<><button className="button success" disabled={busy||(!!r.artifact.actplane_dsl&&r.compile_state!=='compiled')} onClick={()=>reviewArtifact(r.id,'approve')}>通过候选</button><button className="button ghost" disabled={busy} onClick={()=>reviewArtifact(r.id,'reject')}>拒绝</button></>}<button className="button ghost" disabled={busy||!r.artifact.actplane_dsl||r.compile_state==="invalid_candidate"} onClick={()=>run(async()=>{await post('/api/history/artifacts/'+r.id+'/compile');notify('编译检查已排队');})}>重新编译</button></div></section>)}
   {!artifacts.length&&<div className="empty-box">选择已通过语句，生成两个产物。</div>}
  </>}
  <StrategyRecords statusFilter={recordStatus} active={tab===3} api={api} post={post} tasks={tasks} busy={busy} action={action} notify={notify} selectTask={selectTask} reloadHistory={load} onTranslate={ident=>{setStatementId(ident);onModuleChange(2)}}/>
  <details className="panel history-detail"><summary>后台作业（{jobs.length}）</summary>{jobs.slice(0,15).map(j=><article className="history-job" key={j.id}><span>{({collect:'文档采集',extract:'语句抽取',translate:'DSL 转换',compile:'编译检查',rq1_import:'RQ1 语料准备'})[j.kind]}</span> {status(j.status)} <small>{clip(j.id)}</small>{j.error&&<p className="error">{j.error}</p>}{['failed','interrupted'].includes(j.status)&&<button className="button tiny ghost" disabled={busy} onClick={()=>run(async()=>{await post('/api/history/jobs/'+j.id+'/retry');notify('重试已排队');})}>重试</button>}<details><summary>结果</summary><pre>{JSON.stringify(j.result,null,2)}</pre></details></article>)}</details>
 </div></div>;
}
