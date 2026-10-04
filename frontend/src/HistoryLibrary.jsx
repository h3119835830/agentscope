import React,{useState} from 'react';
import StrategyRecords from './StrategyRecords.jsx';
import HistoryAudit from './HistoryAudit.jsx';
import PolicyGeneration from './PolicyGeneration.jsx';
const recordStates=[['','全部状态'],['pending_review','待审核'],['approved','已通过候选'],['rejected','已拒绝'],['loaded','已加载']];
export default function HistoryLibrary({api,post,tasks,busy,action,notify,selectTask,moduleIndex,modules,onModuleChange}){
 const [recordStatus,setRecordStatus]=useState(''),[statementId,setStatementId]=useState('');
 const tab=moduleIndex;
 const navigate=(event,index,count,select)=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?count-1:(index+(event.key==='ArrowRight'?1:-1)+count)%count;select(next);event.currentTarget.parentElement.children[next].focus()};
 return <div className="history-module-page"><div className="history-navigation"><nav className="history-subnav" aria-label="历史策略库二级导航"><div role="tablist" aria-label="历史策略库模块">{modules.map((m,i)=><button key={m.page} id={'history-tab-'+i} role="tab" aria-selected={tab===i} aria-controls="history-module-panel" tabIndex={tab===i?0:-1} className={tab===i?'active':''} onClick={()=>onModuleChange(i)} onKeyDown={e=>navigate(e,tab,modules.length,onModuleChange)}>{m.title}</button>)}</div></nav>{tab===1&&<nav className="history-status-subnav"><div role="tablist" aria-label="策略记录状态">{recordStates.map(([value,title])=><button key={value} id={'record-status-'+(value||'all')} role="tab" aria-selected={recordStatus===value} aria-controls="records-status-panel" tabIndex={recordStatus===value?0:-1} className={recordStatus===value?'active':''} onClick={()=>setRecordStatus(value)} onKeyDown={e=>navigate(e,recordStates.findIndex(([v])=>v===recordStatus),recordStates.length,index=>setRecordStatus(recordStates[index][0]))}>{title}</button>)}</div></nav>}</div><div id="history-module-panel" role="tabpanel" aria-labelledby={'history-tab-'+tab} className="content history-library">{tab===0&&<PolicyGeneration api={api} post={post} tasks={tasks} busy={busy} action={action} notify={notify} initialStatementId={statementId} onConsumed={()=>setStatementId('')}/>}
 <StrategyRecords statusFilter={recordStatus} active={tab===1} api={api} post={post} tasks={tasks} busy={busy} action={action} notify={notify} selectTask={selectTask} reloadHistory={async()=>{}} onTranslate={id=>{setStatementId(id);onModuleChange(0)}}/>
 {tab===2&&<HistoryAudit api={api} post={post} busy={busy} action={action} notify={notify}/>}</div></div>
}
