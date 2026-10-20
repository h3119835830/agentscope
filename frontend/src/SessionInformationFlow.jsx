import React,{useEffect,useId,useRef,useState} from 'react';
import {LabelSourceSummary} from './LabelManagement.jsx';
import RecordBadge from './RecordBadge.jsx';
import {flowTime as date} from './informationFlowPresentation.mjs';
import './informationFlow.css';

const operations={connect:'连接',open:'打开文件',read:'读取',write:'写入',exec:'执行',sendmsg:'发送数据',file_read:'读取文件',file_write:'写入文件'};
const actions={block:'已阻止',report:'已报告',notify:'已通知',kill:'已终止'};
const actionTones={block:'bad',kill:'bad',report:'info',notify:'warning'};

function operation(value){return operations[value]||value||'操作未记录';}
function sourceLabel(record){return record.provenance_state==='reported_first_origin'&&record.provenance?.origin_target?record.provenance.origin_target:'来源未由 ActPlane 报告';}
function scopeLabel(binding){return binding?.attribution==='trusted_tool_tag'?'当前会话':'Agent 共享执行域';}
function configurationNames(record){return record.source_configuration?.names?.join('、')||'配置名称未记录';}

export function FlowScopeControl({value,onChange}){
 const id=useId();
 return <div className="flow-scope-control"><div className="flow-scope-heading"><label htmlFor={id}>查看范围</label><details key={value} className="flow-scope-help"><summary aria-label="查看范围说明">ⓘ</summary><p>{value==='shared_domain'?'可能包含其他会话和共享进程的命中，不代表当前会话独有行为。':'只显示由唯一可信工具标签关联到当前会话的命中，不按时间、PID 或路径猜测归属。'}</p></details></div><select id={id} value={value} onChange={e=>onChange(e.target.value)}><option value="session">当前会话</option><option value="shared_domain">Agent 共享执行域</option></select></div>;
}

export function NativeEvidenceStatus({state,collection,view}){
 if(state==='collection_failed')return <p role="alert" className="inline-notice warning">ActPlane 事件采集失败，请重试；不能据此判断没有信息流。</p>;
 if(state==='empty')return <p className="task-empty">{view==='shared_domain'?'此 Agent 共享执行域暂无原生策略命中证据。':'当前会话暂无可信归属的原生策略命中。可切换到 Agent 共享执行域查看未归属单会话的记录。'}</p>;
 if(collection?.available===false)return <p role="alert" className="inline-notice warning">最新事件采集失败，以下仅为此前已保存的证据，不能代表当前采集完整。</p>;
 return null;
}

export function EvidenceTable({records,onDetail}){
 if(!records.length)return null;
 return <div className="table-scroll flow-evidence-shell"><table className="task-record-table flow-evidence-table" aria-label="ActPlane 原生命中证据"><thead><tr><th>时间 / 标签</th><th>首个可用来源</th><th>当前命中</th><th>策略 / 处置</th><th>归属范围</th><th>操作</th></tr></thead><tbody>{records.map(record=><tr key={record.id}>
  <td><time>{date(record.time)}</time><small>{record.labels?.join('、')||'标签未映射'}</small></td>
  <td><span className={record.provenance_state==='reported_first_origin'?'flow-origin':'flow-origin flow-origin-missing'}>{sourceLabel(record)}</span>{record.provenance?.origin_op&&<small>{operation(record.provenance.origin_op)}</small>}</td>
  <td><strong>{operation(record.match?.operation)}</strong><code>{record.match?.target||'目标未记录'}</code></td>
  <td><span>{record.match?.policy_name||record.match?.rule_name||'策略名称未记录'}</span><small><RecordBadge tone={actionTones[record.match?.actual_action]}>{actions[record.match?.actual_action]||record.match?.actual_action||'处置未记录'}</RecordBadge></small></td>
  <td><span>{scopeLabel(record.binding)}</span><small>{record.binding?.session_id?'可信工具标签关联':'未归属单会话'}</small></td>
  <td><button className="button tiny ghost" onClick={()=>onDetail(record)}>查看详情</button></td>
 </tr>)}</tbody></table></div>;
}

export function FlowDetail({record,onClose}){
 const dialog=useRef(null),origin=useRef(typeof document==='undefined'?null:document.activeElement);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const docs=record.source_configuration?.documents||[],sources=docs.flatMap(item=>item.sources||[]);
 return <dialog ref={dialog} className="record-drawer flow-evidence-drawer" aria-label="信息流命中证据详情" onCancel={event=>{event.preventDefault();onClose();}}><header className="record-drawer-head"><div><small>ActPlane 原生命中证据</small><h2>{operation(record.match?.operation)} · {record.match?.target||'目标未记录'}</h2></div><button className="button ghost" onClick={onClose}>关闭</button></header><div className="record-drawer-body">
  <p className="flow-native-notice">ActPlane 原生证据只报告当前命中和首个可用来源，不代表完整逐跳传播链。</p>
  <h3>首个可用来源</h3>{record.provenance_state==='reported_first_origin'?<dl className="security-facts"><dt>标签</dt><dd>{record.provenance?.label||record.labels?.join('、')||'未记录'}</dd><dt>来源</dt><dd><code>{record.provenance?.origin_target||'目标未记录'}</code></dd><dt>来源操作</dt><dd>{operation(record.provenance?.origin_op)}</dd><dt>来源进程</dt><dd>{record.provenance?.origin_pid??'未记录'}</dd><dt>内核单调时间</dt><dd>{record.provenance?.origin_timestamp_ns?<><code>{record.provenance.origin_timestamp_ns}</code> ns</>:'未记录'}</dd></dl>:<p className="inline-notice">此命中已由内核报告，但来源未由 ActPlane 报告；AgentScope 不根据 PID、时间或路径推断来源。</p>}
  <h3>当前规则命中</h3><dl className="security-facts"><dt>观察时间</dt><dd>{date(record.time)}</dd><dt>标签</dt><dd>{record.labels?.join('、')||'标签未映射'}</dd><dt>操作与目标</dt><dd>{operation(record.match?.operation)} · <code>{record.match?.target||'目标未记录'}</code></dd><dt>策略</dt><dd>{record.match?.policy_name||configurationNames(record)}</dd><dt>规则</dt><dd>{record.match?.rule_name||'规则名称未记录'}</dd><dt>实际处置</dt><dd>{actions[record.match?.actual_action]||record.match?.actual_action||'处置未记录'}</dd><dt>归属范围</dt><dd>{scopeLabel(record.binding)}{record.binding?.session_id?' · '+record.binding.session_id:' · 未归属单会话'}</dd></dl>
  <h3>来源配置引用</h3>{docs.length?<ul className="flow-configuration-list">{docs.map(item=><li key={item.id}><strong>{item.name||'配置名称未记录'}</strong><small>{(item.labels||[item.label]).filter(Boolean).join('、')||'标签未映射'} · 该配置引用 {item.sources?.length||0} 个来源；不表示某一条就是此次精确来源。</small></li>)}</ul>:<p className="task-empty">当前应用快照未提供可展示的来源配置引用。</p>}
  <LabelSourceSummary sources={sources}/>
  <details className="record-note"><summary>技术证据</summary><dl className="security-facts"><dt>证据编号</dt><dd>{record.evidence_ref}</dd><dt>规则编号</dt><dd>{record.match?.rule_id??'未记录'}</dd><dt>进程</dt><dd>{record.match?.pid??'未记录'}</dd><dt>执行域</dt><dd>{record.binding?.domain_id??'未记录'}</dd><dt>策略包摘要</dt><dd><code>{record.binding?.bundle_hash||'未记录'}</code></dd><dt>provenance</dt><dd>{record.provenance_state==='reported_first_origin'?'ActPlane 已报告首个来源':'ActPlane 未报告来源'}</dd></dl></details>
 </div></dialog>;
}

export default function SessionInformationFlow({api,root}){
 const [view,setView]=useState('session'),[label,setLabel]=useState(''),[data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[detail,setDetail]=useState(null),[revision,setRevision]=useState(0);
 const sequence=useRef(0);
 useEffect(()=>{let alive=true;const n=++sequence.current;setData(null);setError('');setBusy(true);setDetail(null);
  const params=new URLSearchParams({view,...(label?{label}:{})});
  api(root+'/information-flow?'+params).then(value=>{if(alive&&n===sequence.current)setData(value);}).catch(()=>{if(alive&&n===sequence.current)setError('无法读取 ActPlane 命中证据，请检查连接后刷新重试。不能据此判断没有信息流。');}).finally(()=>{if(alive&&n===sequence.current)setBusy(false);});
  return()=>{alive=false;sequence.current++;};
 },[api,root,view,label,revision]);
 async function more(){const n=sequence.current;setBusy(true);setError('');try{const params=new URLSearchParams({view,cursor:data.next_cursor,generation:data.generation,...(label?{label}:{})});const value=await api(root+'/information-flow?'+params);if(n!==sequence.current)return;
  setData(old=>({...value,records:[...old.records,...value.records],available_labels:[...new Set([...old.available_labels,...value.available_labels])]}));
 }catch{if(n===sequence.current)setError('更早的命中证据暂时无法读取，请刷新重试。当前仅展示已取得的记录。');}finally{if(n===sequence.current)setBusy(false);}}
 return <section className="information-flow"><div className="flow-toolbar"><FlowScopeControl value={view} onChange={value=>{setView(value);setLabel('');}}/><label>标签<select value={label} onChange={event=>setLabel(event.target.value)}><option value="">全部已记录标签</option>{(data?.available_labels||[label].filter(Boolean)).map(value=><option key={value} value={value}>{value}{['SENSITIVE','REMOTE','CODE'].includes(value)?'（历史）':''}</option>)}</select></label><button className="button ghost" disabled={busy} onClick={()=>setRevision(value=>value+1)}>刷新</button></div>
 <p className="flow-native-notice">ActPlane 原生证据只报告当前命中和首个可用来源，不代表完整逐跳传播链。</p>
 {busy&&!data&&<p role="status">正在读取 ActPlane 命中证据…</p>}{error&&<p role="alert" className="inline-notice warning">{error}</p>}
 {data&&<>{data.historical&&<p className="session-coverage">历史代次 · 不代表当前运行状态</p>}<NativeEvidenceStatus state={data.state} collection={data.collection} view={view}/><EvidenceTable records={data.records||[]} onDetail={setDetail}/>{data.next_cursor&&<button className="button ghost flow-more" disabled={busy} onClick={more}>{busy?'正在读取…':'加载更早记录'}</button>}</>}
 {detail&&<FlowDetail record={detail} onClose={()=>setDetail(null)}/>}</section>;
}
