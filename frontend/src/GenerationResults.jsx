import React,{useCallback,useEffect,useRef,useState} from 'react';
import {states,levels,scopes,initialFilters} from './generationPresentation.js';

export function GenerationStatus({value}){
 return <span className={'tag '+(['complete','compiled','approved','completed'].includes(value)?'good':['rejected','failed','compile_failed','invalid_candidate'].includes(value)?'bad':'warn')}>{states[value]||value}</span>;
}

export function GenerationDialog({title,onClose,children}){
 const dialog=useRef(null),focus=useRef(document.activeElement),label=React.useId();
 useEffect(()=>{const node=dialog.current;node.showModal();return()=>{node.close();if(focus.current?.isConnected)focus.current.focus()}},[]);
 return <dialog className="record-dialog" ref={dialog} aria-labelledby={label} onCancel={event=>{event.preventDefault();onClose()}}><div className="panel-head"><h2 id={label}>{title}</h2><button className="button ghost" onClick={onClose}>关闭</button></div><div className="record-dialog-body">{children}</div></dialog>;
}

function ResultDetail({row,onClose,showProcess}){
 const s=row.record.statement,a=row.artifact;
 return <GenerationDialog title={'策略来源与产物 · v'+row.version} onClose={onClose}>
  <p>{s.text_zh||s.text_original}</p><blockquote>{s.source_quote}</blockquote>
  {s.evidence_spans?.map((span,i)=><blockquote key={i}>L{span.line_start}–{span.line_end}：{span.source_quote}</blockquote>)}
  <p>{row.record.origin.repository} · {row.record.origin.path} · L{s.line_start}–{s.line_end}</p>
  {row.record.origin.url&&<a href={row.record.origin.url+'#L'+s.line_start} target="_blank" rel="noreferrer">查看固定来源 ↗</a>}
  <p>二审：{states[s.completeness]||s.completeness} · 人工审核：{states[row.review_status]||row.review_status}</p>
  {s.review_issues?.map((issue,i)=><p key={i}>{issue}</p>)}
  <h3>适配与加载条件</h3><pre>{JSON.stringify(row.adaptation,null,2)}</pre>{row.load_blockers.map((x,i)=><p key={i}>{x}</p>)}
  <details><summary>参数来源与范围适配</summary><pre>{JSON.stringify(row.record.resolved_context,null,2)}</pre></details>
  <details><summary>校验与编译</summary><pre>{JSON.stringify({checks:a?.policy_record?.compile_check,compilation:row.compilation},null,2)}</pre></details>
  {showProcess&&<details><summary>模型调用记录</summary><pre>{JSON.stringify(a?.llm_runs||[],null,2)}</pre></details>}
  <details><summary>PolicyIR</summary><pre>{JSON.stringify(a?.policy_ir||null,null,2)}</pre></details>
  <details><summary>策略伪代码</summary><pre>{a?.pseudo_code||'尚未生成'}</pre></details>
  <details open><summary>ActPlane DSL</summary><pre>{a?.actplane_dsl||'无执行 DSL'}</pre></details>
  <p>源文件 hash：{row.record.origin.content_hash}<br/>语句 hash：{row.statement_hash}<br/>产物 hash：{row.artifact_hash||'—'}</p>
  {(row.review_blockers||[]).map((x,i)=><p key={i} className="error">{x}</p>)}{row.error&&<p className="error">{row.error}</p>}
 </GenerationDialog>;
}

export default function GenerationResults({runId,api,post,busy,action,notify,readOnly=false,onReviewed}){
 const [page,setPage]=useState({items:[],total:0}),[offset,setOffset]=useState(0),[filters,setFilters]=useState(initialFilters),[selected,setSelected]=useState({}),[detail,setDetail]=useState(null);
 const sequence=useRef(0);
 const load=useCallback(async()=>{const n=++sequence.current;const result=await api('/api/history/generations/'+runId+'/results?'+new URLSearchParams({...filters,limit:'20',offset:String(offset)}));if(n===sequence.current)setPage(result)},[api,runId,filters,offset]);
 useEffect(()=>{load().catch(e=>notify(e.message));const timer=setInterval(()=>load().catch(()=>{}),4000);return()=>{sequence.current++;clearInterval(timer)}},[load,notify]);
 const change=(name,value)=>{setFilters({...filters,[name]:value});setOffset(0);setSelected({})};
 const review=(rows,decision)=>{if(readOnly)return;action(async()=>{await post('/api/history/generations/'+runId+'/review',{decision,reviewed_by:'研究者',items:rows.map(r=>({statement_version_id:r.statement_version_id,expected_statement_hash:r.statement_hash,artifact_id:r.artifact_id,expected_artifact_hash:r.artifact_hash}))});setSelected({});await load();await onReviewed?.();notify(decision==='approve'?'语句与产物已共同审核':'已拒绝候选')})};
 const picked=Object.values(selected);
 return <div className={'generation-results'+(readOnly?' history-result-preview':'')}>
  {readOnly&&<p className="field-note">历史结果预览，仅查看保存的版本；审核状态为当前状态。需要处理请点击“继续审核”。</p>}
  <div className="generation-filters"><label>搜索<input placeholder="策略、来源或文件路径" value={filters.q} onChange={e=>change('q',e.target.value)}/></label>{[['execution_level','执行层级',levels],['context_scope','上下文范围',scopes],['completeness','完整性',{complete:'二审完整',needs_clarification:'待澄清',unreviewed:'未二审'}],['adaptation','本机适配',{required:'需本机适配',complete:'已适配',not_required:'无需适配'}],['loadable','加载状态',{yes:'可加载',no:'不可加载'}]].map(([key,title,options])=><label key={key}>{title}<select aria-label={'筛选'+title} value={filters[key]} onChange={e=>change(key,e.target.value)}><option value="">全部</option>{Object.entries(options).map(([value,text])=><option key={value} value={value}>{text}</option>)}</select></label>)}</div>
  <div className="records-pagination"><span>{page.total} 条策略</span><div className="button-row">{!readOnly&&<button className="button tiny primary" disabled={busy||!picked.length} onClick={()=>review(picked,'approve')}>最终审核通过（{picked.length}）</button>}<button className="button tiny ghost" disabled={!offset} onClick={()=>{setOffset(Math.max(0,offset-20));setSelected({})}}>上一页</button><button className="button tiny ghost" disabled={offset+page.items.length>=page.total} onClick={()=>{setOffset(offset+20);setSelected({})}}>下一页</button></div></div>
  <section className="panel table-panel"><div className="table-scroll"><table className="generation-table"><thead><tr>{!readOnly&&<th>选择</th>}<th>完整策略语句</th><th>来源</th><th>层级 / 范围</th><th>审核与加载条件</th></tr></thead><tbody>{page.items.map(row=>{const s=row.record.statement,canApprove=s.completeness==='complete'&&!(row.review_blockers||[]).length&&!!row.artifact&&(!row.artifact.actplane_dsl||row.compile_state==='compiled')&&row.review_status!=='approved';return <tr key={row.statement_version_id}>
   {!readOnly&&<td><input type="checkbox" aria-label={'选择候选 '+row.statement_version_id} disabled={!canApprove} checked={!!selected[row.statement_version_id]} onChange={e=>setSelected(values=>{const next={...values};if(e.target.checked)next[row.statement_version_id]=row;else delete next[row.statement_version_id];return next})}/></td>}
   <td className="strategy-text"><button className="record-open" onClick={()=>setDetail(row)}>来源 / 伪代码 / DSL</button><p>{s.text_zh||s.text_original}</p>{s.text_zh&&<small>{s.text_original}</small>}{!readOnly&&<div className="record-actions"><button className="button tiny primary" disabled={busy||!canApprove} onClick={()=>review([row],'approve')}>最终审核通过</button><button className="button tiny ghost" disabled={busy||row.review_status==='rejected'} onClick={()=>review([row],'reject')}>拒绝</button></div>}</td>
   <td>{row.record.origin.repository}<small>{row.record.origin.path}:L{s.line_start}–{s.line_end}</small><small>{row.record.origin.commit?.slice(0,12)||'—'}</small></td><td>{levels[s.enforcement_level]}<small>{scopes[s.context_requirement]}</small></td>
   <td><GenerationStatus value={s.completeness}/> <GenerationStatus value={row.review_status}/><small>{row.adaptation.state==='required'?<GenerationStatus value="required"/>:row.compile_state?<GenerationStatus value={row.compile_state}/>:'未生成 DSL'}</small>{row.load_blockers.map((x,i)=><small key={i}>{x}</small>)}{row.error&&<small className="error">{row.error}</small>}</td>
  </tr>})}{!page.items.length&&<tr><td colSpan={readOnly?4:5} className="empty-row">暂无符合条件的策略，生成结果会自动出现。</td></tr>}</tbody></table></div></section>
  {detail&&<ResultDetail row={detail} onClose={()=>setDetail(null)} showProcess={readOnly}/>}
 </div>;
}
