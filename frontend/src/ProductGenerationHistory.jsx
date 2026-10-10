import React,{useEffect,useState} from 'react';
import {GenerationStatus} from './GenerationResults.jsx';
import {sourceName,time} from './generationPresentation.js';

// Diagnostic jobs, raw receipts and audit JSON remain in HistoryAudit for the
// future operations client. This view reads saved generation business records.
export default function ProductGenerationHistory({api,selectedRunId,onSelectRun,onContinueReview}){
 const [page,setPage]=useState(null),[offset,setOffset]=useState(0),[error,setError]=useState('');
 useEffect(()=>{let alive=true;setPage(null);api('/api/history/generations/page?'+new URLSearchParams({offset:String(offset),limit:'20'})).then(d=>{if(alive){setPage(d);setError('');}}).catch(e=>alive&&setError(e.message));return()=>{alive=false};},[api,offset]);
 return <section className="panel table-panel"><div className="panel-head"><h2>生成记录</h2></div>{error&&<p role="alert" className="error">{error}</p>}{!page&&!error&&<p role="status" className="task-empty">正在读取生成记录…</p>}{page?.items.length>0&&<><div className="table-scroll"><table><thead><tr><th>来源</th><th>生成时间</th><th>状态</th><th>操作</th></tr></thead><tbody>{page.items.map(r=><tr key={r.id}><td>{sourceName(r)}</td><td>{time(r.created_at)}</td><td><GenerationStatus value={r.status}/></td><td><button className="button tiny ghost" onClick={()=>{onSelectRun(r.id);onContinueReview(r.id)}}>{r.status==='completed'?'查看结果':'查看并审核'}</button></td></tr>)}</tbody></table></div>{page.total>20&&<div className="records-pagination"><span>{page.total} 条记录</span><div className="actions"><button className="button tiny ghost" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>上一页</button><button className="button tiny ghost" disabled={offset+page.items.length>=page.total} onClick={()=>setOffset(offset+20)}>下一页</button></div></div>}</>}{page&&!page.items.length&&<p className="task-empty">尚无生成记录。</p>}{selectedRunId&&<div className="panel-head"><button className="button ghost" onClick={()=>onContinueReview(selectedRunId)}>查看当前生成结果</button></div>}</section>;
}
