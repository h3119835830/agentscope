import React,{useCallback,useEffect,useRef,useState} from 'react';
const names={collect:'文档采集',extract:'语句抽取',translate:'策略转 DSL',compile:'编译检查',rq1_import:'RQ1 语料准备',task_bootstrap:'Pi 启动前生成'};
const states={queued:'排队中',running:'处理中',completed:'已完成',failed:'失败',interrupted:'已中断'};
const actions={rq1_corpus_import:'RQ1 语料导入',history_input_registered:'登记转换输入',history_extracted:'语句抽取完成',history_statement_review:'语句版本审核',history_statement_revised:'语句版本修订',history_artifact_review:'DSL 候选审核',history_artifact_duplicate_result:'重复产物复用',strategy_review:'目录策略审核',strategy_created:'创建策略',strategy_updated:'修改目录策略',strategy_archived:'归档策略',strategy_restored:'恢复策略'};
const time=v=>v?new Date(v).toLocaleString('zh-CN',{hour12:false}):'—';
export default function HistoryAudit({api,post,busy,action,notify}){
 const [section,setSection]=useState('jobs'),[kind,setKind]=useState(''),[status,setStatus]=useState(''),[q,setQ]=useState(''),[offset,setOffset]=useState(0);
 const [page,setPage]=useState({items:[],total:0});
 const request=useRef(0);
 const load=useCallback(async()=>{const sequence=++request.current;const result=await api('/api/history/activity?'+new URLSearchParams({section,kind,status,q,offset:String(offset),limit:'20'}));if(sequence===request.current)setPage(result)},[api,section,kind,status,q,offset]);
 useEffect(()=>{load().catch(e=>notify(e.message));const timer=setInterval(()=>load().catch(()=>{}),5000);return()=>{request.current++;clearInterval(timer)}},[load,notify]);
 const filter=(setter,value)=>{setter(value);setOffset(0)};
 const change=mode=>{setSection(mode);setKind('');setStatus('');setOffset(0)};
 return <div className="history-audit"><div className="panel-head"><div><h2>采集与审计</h2><p>集中记录采集、RQ1 导入、抽取、转换、编译、审核与修订；其他模块保留操作入口。</p></div></div>
 <div className="segmented audit-sections" aria-label="审计记录类型"><button className={section==='jobs'?'sel':''} onClick={()=>change('jobs')}>后台作业</button><button className={section==='events'?'sel':''} onClick={()=>change('events')}>操作审计</button></div>
 <div className="toolbar records-toolbar"><label>记录类型<select value={kind} onChange={e=>filter(setKind,e.target.value)}><option value="">全部类型</option>{Object.entries(section==='jobs'?names:actions).map(([value,title])=><option key={value} value={value}>{title}</option>)}</select></label>{section==='jobs'&&<label>作业状态<select value={status} onChange={e=>filter(setStatus,e.target.value)}><option value="">全部状态</option>{Object.entries(states).map(([value,title])=><option key={value} value={value}>{title}</option>)}</select></label>}<label className="audit-search">搜索记录<input aria-label="搜索审计记录" placeholder="作业 ID、仓库、版本或操作人" value={q} onChange={e=>filter(setQ,e.target.value)}/></label></div>
 <div className="records-pagination"><span>{page.total} 条记录</span><div className="button-row"><button className="button tiny ghost" disabled={offset===0||busy} onClick={()=>setOffset(Math.max(0,offset-20))}>上一页</button><button className="button tiny ghost" disabled={offset+page.items.length>=page.total||busy} onClick={()=>setOffset(offset+20)}>下一页</button></div></div>
 {page.items.map(row=><article className="panel audit-record" key={row.id}><div className="panel-head"><div><b>{section==='jobs'?names[row.kind]||row.kind:actions[row.action]||row.action}</b><small>{time(row.created_at)} · {row.id}</small></div>{section==='jobs'?<span className={'tag '+(row.status==='completed'?'good':row.status==='failed'?'bad':'warn')}>{states[row.status]}</span>:<span className="tag">{row.actor}</span>}</div>
 {section==='jobs'?<><dl className="record-metadata"><dt>开始 / 结束</dt><dd>{time(row.started_at)} / {time(row.finished_at)}</dd>{row.retry_of&&<><dt>重试来源</dt><dd>{row.retry_of}</dd></>}</dl>{row.error&&<p className="error">{row.error}</p>}<details><summary>输入</summary><pre>{JSON.stringify(row.input,null,2)}</pre></details><details><summary>结果与产物引用</summary><pre>{JSON.stringify(row.result,null,2)}</pre></details>{['failed','interrupted'].includes(row.status)&&<button className="button tiny ghost" disabled={busy} onClick={()=>action(async()=>{await post('/api/history/jobs/'+row.id+'/retry');await load();notify('重试已排队')})}>重试作业</button>}</>:<details><summary>审计详情与版本引用</summary><pre>{JSON.stringify(row.details,null,2)}</pre></details>}
 </article>)}{!page.items.length&&<div className="panel empty-box">暂无符合条件的记录。</div>}
 </div>;
}
