import React,{useEffect,useRef,useState} from 'react';
import DomainGraph from './DomainGraph.jsx';

export function archiveDomainPath(task,version,key) {
 const base=`/api/tasks/${encodeURIComponent(task)}/archive/domains`;
 return key?`${base}/${encodeURIComponent(key)}`:version===null||version===undefined?base:`${base}?version=${encodeURIComponent(version)}`;
}
function Fields({items}) {return <dl className="record-fields">{items.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{typeof value==='boolean'?(value?'是':'否'):value??'未记录'}</dd></React.Fragment>)}</dl>;}
function DomainEvidence({domain}) {
 return <><div className="record-tags">{(domain.labels||[]).map(label=><span className="record-tag" key={label}>{label}</span>)}</div><Fields items={[
 ['域 ID',domain.domain_id],['历史版本',`v${domain.version}`],['域职责',domain.role==='baseline'?'启动底线域':'任务执行域'],
 ['策略源 hash 核验',domain.available],['加载时核验通过',domain.loading_verification_passed],
 ['策略源',domain.source==='confirmed_policy_hash'?'策略包与加载回执 hash 一致':domain.source==='root_owned_watch_artifact'?'root 所有的 watch 策略与控制记录':'材料缺失或未核验'],['策略包 hash',domain.policy_hash]
 ]}/><p className="muted">标签来自已记录 DSL 的 source 声明。历史加载记录不代表当前在线或策略正在生效。</p>
 {domain.available&&typeof domain.dsl==='string'?<details className="record-note"><summary>查看该次加载的 DSL</summary><pre className="record-code">{domain.dsl}</pre></details>:<p className="muted">没有与该次加载证据一致的 DSL。</p>}</>;
}

export default function ArchiveDomains({task,api}) {
 const [open,setOpen]=useState(false),[version,setVersion]=useState(null),[graph,setGraph]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 const [selected,setSelected]=useState(null),[detail,setDetail]=useState(null),[detailError,setDetailError]=useState(''),[detailBusy,setDetailBusy]=useState(false);
 const graphSeq=useRef(0),detailSeq=useRef(0),heading=useRef(null),trigger=useRef(null);
 useEffect(()=>{setVersion(null);setGraph(null);setSelected(null);setDetail(null);setError('');},[task]);
 useEffect(()=>{
  const seq=++graphSeq.current;detailSeq.current++;setSelected(null);setDetail(null);setDetailError('');setDetailBusy(false);
  if(!open)return;
  setBusy(true);setError('');setGraph(null);
  api(archiveDomainPath(task,version)).then(result=>{if(!result||!Array.isArray(result.nodes)||!Array.isArray(result.edges)||!Array.isArray(result.versions))throw new Error('历史域接口尚未就绪或返回内容不完整，请稍后重试。');if(seq===graphSeq.current)setGraph(result);}).catch(e=>{if(seq===graphSeq.current)setError(e.message);}).finally(()=>{if(seq===graphSeq.current)setBusy(false);});
  return()=>{graphSeq.current++;};
 },[task,api,open,version,retry]);
 useEffect(()=>{if(selected)heading.current?.focus();},[selected]);
 async function selectDomain(node) {
  trigger.current=document.activeElement;const seq=++detailSeq.current;setSelected(node);setDetail(null);setDetailError('');setDetailBusy(true);
  try {const result=await api(archiveDomainPath(task,null,node.key));if(seq===detailSeq.current)setDetail(result);}
  catch(e){if(seq===detailSeq.current)setDetailError(e.message);}
  finally{if(seq===detailSeq.current)setDetailBusy(false);}
 }
 function selectProcess(node){trigger.current=document.activeElement;detailSeq.current++;setSelected(node);setDetail(null);setDetailError('');setDetailBusy(false);}
 return <details className="record-note" onToggle={e=>{if(e.target===e.currentTarget)setOpen(e.currentTarget.open);}}>
  <summary>历史域、进程与 DSL</summary>
  {open&&<><p className="muted">仅展示加载收据中的历史绑定与策略源；未记录的进程不补推。</p>
   {busy&&<p role="status">正在读取历史域…</p>}
   {error&&<p role="alert">{error} <button className="button ghost tiny" onClick={()=>setRetry(n=>n+1)}>重试</button></p>}
   {graph&&<>{graph.notice&&<p className="muted">{graph.notice}</p>}{Array.isArray(graph.missing_sources)&&graph.missing_sources.length>0&&<p className="inline-notice warning">{[...new Set(graph.missing_sources.map(item=>item.role==='baseline'?'底线域加载材料未记录':item.role==='task'?'任务域加载材料未记录':'部分历史加载材料未记录'))].join('；')}。图中仅显示有可信证据的历史域。</p>}<DomainGraph graph={graph} files={{records:[]}} historical fresh={false} onVersion={setVersion} onDomain={selectDomain} onProcess={selectProcess}/></>}
   {selected&&<section className="record-note" aria-label="历史节点详情"><div className="graph-toolbar"><h3 ref={heading} tabIndex="-1">{selected.title}</h3><button className="button ghost tiny" onClick={()=>{detailSeq.current++;setSelected(null);setDetail(null);trigger.current?.isConnected&&trigger.current.focus();}}>收起详情</button></div>
    {detailBusy&&<p role="status">正在读取加载证据…</p>}
    {detailError&&<p role="alert">{detailError} <button className="button ghost tiny" onClick={()=>selectDomain(selected)}>重试</button></p>}
    {detail&&<DomainEvidence domain={detail}/>}
    {selected.kind==='process'&&<><Fields items={[['历史 PID',selected.pid],['历史角色',({runner:'任务 runner',watch:'策略 watch',executor:'DSH 执行进程',agent:'DSH 执行进程'})[selected.role]||selected.role],['历史版本',`v${selected.version}`],['记录时间',selected.recorded_at]]}/><p className="muted">PID 来自该次加载收据，不是当前进程采样。</p></>}
   </section>}
  </>}
 </details>;
}
