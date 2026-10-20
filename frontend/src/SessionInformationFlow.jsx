import React,{useEffect,useRef,useState} from 'react';
import {LabelSourceSummary} from './LabelManagement.jsx';
import {flowTime as date} from './informationFlowPresentation.mjs';
import './informationFlow.css';

const operations={source_introduced:'引入来源标签',file_to_process:'文件 → 进程',process_to_file:'进程 → 文件',fork_inherit:'派生进程继承',exec_inherit:'执行时保留标签',rule_match:'策略命中'};
const outcomes={propagated:'引擎观察到标签传播',report:'已报告 · 不代表操作成功',block:'操作已阻止',kill:'命中后终止进程'};
const statuses={empty:'当前范围暂无带标签的策略命中。可切换到 Agent 共享执行域查看未归属单会话的记录。',legacy:'仅有历史命中回执，缺少逐跳传播记录，无法还原完整链。',unsupported:'此运行版本不支持逐跳传播采集。',collection_failed:'传播事件采集失败，请重试；不能据此判断没有传播。'};
const reasonNames={identity_or_predecessor_missing:'对象身份或前驱未完整记录',label_mapping_missing:'缺少执行标签映射',collector_loss:'采集器报告丢事件',missing_origin:'缺少来源事件',missing_predecessor:'前驱回执尚未入库或已丢失',conflicting_duplicate:'重复事件内容不一致',shared_context_not_in_session:'上游事件属于共享域，未可信关联到本会话',unverified_receipt:'回执与运行绑定不一致',predecessor_identity_mismatch:'前驱对象、标签或代次不一致',cycle:'前驱形成循环',chain_limit:'链路超过查询上限'};

function FlowDetail({detail,onClose}){
 const dialog=useRef(null),origin=useRef(document.activeElement);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const edge=detail.evidence;
 return <dialog ref={dialog} className="record-drawer" aria-label="信息流证据详情" onCancel={e=>{e.preventDefault();onClose();}}><header className="record-drawer-head"><h2>{detail.node?.title||operations[edge.operation]}</h2><button className="button ghost" onClick={onClose}>关闭</button></header><div className="record-drawer-body">
 <dl className="security-facts"><dt>观察时间</dt><dd>{date(edge.time)}</dd><dt>操作</dt><dd>{operations[edge.operation]||edge.operation}</dd><dt>标签</dt><dd>{edge.source_mapping.map(s=>s.label).join('、')||'映射缺失'}</dd><dt>实际处置</dt><dd>{outcomes[edge.outcome]||'处置未记录'}</dd><dt>来源配置</dt><dd>{edge.source_mapping.map(s=>s.configuration_name).filter(Boolean).join('、')||'未记录'}</dd></dl>
 <LabelSourceSummary sources={edge.source_mapping.flatMap(s=>s.sources||[])}/>
 <details><summary>技术证据</summary><dl className="security-facts"><dt>实际 Hook</dt><dd><code>{edge.hook||'未记录'}</code></dd><dt>审计回执</dt><dd>{edge.evidence_ref}</dd><dt>运行代次</dt><dd><code>{edge.generation}</code></dd><dt>执行域</dt><dd>{edge.domain_id}</dd><dt>策略哈希</dt><dd><code>{edge.policy_hash}</code></dd>{detail.node?.identity&&Object.entries(detail.node.identity).filter(([,v])=>v!==null&&v!==undefined&&v!==0).map(([k,v])=><React.Fragment key={k}><dt>{k}</dt><dd><code>{String(v)}</code></dd></React.Fragment>)}</dl></details>
 </div></dialog>;
}

export function FlowStatus({integrity}){
 return <>{statuses[integrity.state]&&<p className="task-empty">{statuses[integrity.state]}</p>}
 {integrity.state==='incomplete'&&<div className="inline-notice warning"><strong>链路不完整</strong><p>{integrity.reasons.map(r=>reasonNames[r]||'证据缺失').join('；')}。只展示已核验的边。</p></div>}</>;
}

export function WitnessGraph({data,onDetail}){
 const byId=Object.fromEntries(data.nodes.map(n=>[n.id,n]));
 const edges=data.edges;
 if(!edges.length)return null;
 const nodes=[byId[edges[0].from],...edges.map(e=>byId[e.to])];
 const step=180, nodeWidth=140, width=nodes.length*step;
 return <div className="flow-canvas" role="region" aria-label="真实传播来源链" tabIndex={0}>
 <svg width={width} height="190" role="img" aria-label="按回执先后排列的单条信息流链">
 <defs><marker id="flow-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#64748b"/></marker></defs>
 {edges.map((e,i)=><g key={e.id}><line x1={i*step+20+nodeWidth} x2={(i+1)*step+20} y1="82" y2="82" stroke="#64748b" markerEnd="url(#flow-arrow)"/><foreignObject x={i*step+100} y="124" width="155" height="60"><button className={'flow-edge '+e.outcome} onClick={()=>onDetail({evidence:e})}>{operations[e.operation]||e.operation}<small>{e.outcome==='block'?'已阻止':'查看回执'}</small></button></foreignObject></g>)}
 {nodes.map((node,i)=><foreignObject key={i+':'+node.id} x={i*step+20} y="32" width={nodeWidth} height="100"><button className={'flow-node '+node.kind} onClick={()=>onDetail({node,evidence:edges[Math.max(0,i-1)]})}><small>{{file:'文件',process:'进程',endpoint:'连接目标',operation:'操作'}[node.kind]}</small><strong>{node.title}</strong></button></foreignObject>)}
 </svg></div>;
}

export default function SessionInformationFlow({api,root}){
 const [view,setView]=useState('session'),[label,setLabel]=useState(''),[anchor,setAnchor]=useState(''),[data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[detail,setDetail]=useState(null),[revision,setRevision]=useState(0);
 const sequence=useRef(0);
 useEffect(()=>{let alive=true;const n=++sequence.current;setData(null);setError('');setBusy(true);setDetail(null);
  const params=new URLSearchParams({view,...(label?{label}:{}),...(anchor?{anchor}:{})});
  api(root+'/information-flow?'+params).then(v=>{if(alive&&n===sequence.current)setData(v);}).catch(()=>{if(alive)setError('无法读取传播记录，请检查连接后刷新重试。不能据此判断没有传播。');}).finally(()=>{if(alive)setBusy(false);});
  return()=>{alive=false;sequence.current++;};
 },[api,root,view,label,anchor,revision]);
 async function more(){const n=sequence.current;setBusy(true);try{const params=new URLSearchParams({view,anchor:data.anchor,cursor:data.next_cursor,generation:data.generation,...(label?{label}:{})});const value=await api(root+'/information-flow?'+params);if(n!==sequence.current)return;
  setData(old=>({...value,anchors:old.anchors,nodes:[...new Map([...old.nodes,...value.nodes].map(x=>[x.id,x])).values()],edges:[...value.edges,...old.edges],integrity:{state:old.integrity.state==='incomplete'||value.integrity.state==='incomplete'?'incomplete':value.integrity.state,reasons:[...new Set([...old.integrity.reasons,...value.integrity.reasons])]}}));
 }catch(e){if(n===sequence.current)setError('更早的来源暂时无法读取，请刷新重试。当前仅展示已取得的回执。');}finally{if(n===sequence.current)setBusy(false);}}
 return <section className="information-flow"><div className="flow-toolbar"><label>查看范围<select value={view} onChange={e=>{setView(e.target.value);setAnchor('');}}><option value="session">当前会话</option><option value="shared_domain">Agent 共享执行域</option></select></label><label>标签<select value={label} onChange={e=>{setLabel(e.target.value);setAnchor('');}}><option value="">全部已记录标签</option>{['SECRET','AGENT','SENSITIVE','REMOTE','CODE'].map(l=><option key={l} value={l}>{l}{['SENSITIVE','REMOTE','CODE'].includes(l)?'（历史）':''}</option>)}</select></label><button className="button ghost" disabled={busy} onClick={()=>setRevision(v=>v+1)}>刷新</button></div>
 <p className={view==='shared_domain'?'inline-notice warning':'session-coverage'}>{view==='shared_domain'?'Agent 共享执行域：可能包含其他会话和共享进程的传播，不代表当前会话独有行为。':'当前会话只显示可信关联事件，不按时间或 PID 猜测归属。'}</p>
 {busy&&!data&&<p role="status">正在读取传播回执…</p>}{error&&<p role="alert" className="inline-notice warning">{error}</p>}
 {data&&<>{data.historical&&<p className="session-coverage">历史运行代次 · 不代表当前运行状态</p>}
 {data.anchors.length>0&&<label className="flow-anchor">策略命中<select value={data.anchor||anchor} onChange={e=>setAnchor(e.target.value)}>{data.anchors.map(a=><option key={a.event_id} value={a.event_id}>{date(a.time)} · {a.labels.join('、')||'标签映射缺失'} · {outcomes[a.outcome]} · {a.target}</option>)}</select></label>}
 <FlowStatus integrity={data.integrity}/>
 <WitnessGraph data={data} onDetail={setDetail}/>
 {data.edges.length>0&&<p className="session-coverage">每条边对应一条审计回执；记录的是引擎标签传播，不推断文件正文或未观察的操作成功。</p>}
 {data.next_cursor&&<button className="button ghost" disabled={busy} onClick={more}>展开更早来源</button>}
 </>}
 {detail&&<FlowDetail detail={detail} onClose={()=>setDetail(null)}/>}
 </section>;
}
