import React,{useEffect,useRef} from 'react';
import {layoutGraph} from './graphView.mjs';
import {relativeTarget} from './runtimeView.mjs';

export default function DomainGraph({graph,files={records:[]},workspace,fresh,onVersion,onDomain,onProcess,onAudit,historical=false}) {
  const scroll=useRef(null);
  useEffect(()=>{
    const element=scroll.current;if(!element)return;
    let width=0;
    const center=()=>{if(element.clientWidth!==width){width=element.clientWidth;element.scrollLeft=(element.scrollWidth-width)/2;}};
    center();const observer=new ResizeObserver(center);observer.observe(element);
    return()=>observer.disconnect();
  },[graph?.task_id,graph?.version]);
  if(!graph)return <div className="runtime-empty">正在读取执行域…</div>;
  const nodes=graph.nodes.filter(n=>n.kind!=='process'||(historical?n.pid!=null:fresh&&graph.live)),edges=graph.edges;
  const domain=nodes.find(n=>n.kind==='domain'&&n.role==='task');
  const seen=new Set(),resources=domain?files.records.filter(a=>a.domain_id===domain.domain_id&&a.target&&!seen.has(a.target)&&seen.add(a.target)).slice(0,3):[];
  for(const audit of resources){nodes.push({key:'file:'+audit.id,kind:'file',title:relativeTarget(audit.target,workspace),audit});}
  const layout=layoutGraph(nodes,[...edges,...resources.map(a=>({from:domain.key,to:'file:'+a.id,kind:'access',label:'操作证据'}))]);
  const byKey=new Map(layout.nodes.map(n=>[n.key,n]));
  return <section className="domain-graph" aria-label={historical?"历史域与进程关系图":"域与进程关系图"}>
    <div className="graph-toolbar"><div><strong>{historical?'历史绑定关系':'执行关系'}</strong><span>点击节点查看详情</span></div><select aria-label={historical?"查看历史加载版本":"查看执行域版本"} value={graph.version} onChange={e=>onVersion(Number(e.target.value))}>{graph.versions.length?graph.versions.map(v=><option key={v.version} value={v.version}>v{v.version}{historical?' · 加载记录':v.version===graph.versions[0].version?' · 最近加载':' · 历史域'}</option>):<option value={graph.version}>尚未加载</option>}</select></div>
    {nodes.length?<div ref={scroll} className="graph-scroll" tabIndex="0" aria-label="可滚动关系图"><div className="graph-canvas" style={{width:layout.width,height:layout.height}}>
      <svg className="graph-edges" width={layout.width} height={layout.height} aria-hidden="true"><defs><marker id="domain-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7" fill="#94a3b0"/></marker></defs>{layout.edges.map((e,i)=>{const from=byKey.get(e.from),to=byKey.get(e.to),x=from.x+112,y=from.y+88,tx=to.x+112,ty=to.y,mid=(y+ty)/2;return <g key={i}><path d={`M${x},${y} C${x},${mid} ${tx},${mid} ${tx},${ty-6}`} fill="none" stroke="#94a3b0" strokeWidth="1.3" strokeDasharray={e.kind==='access'?'4 4':undefined} markerEnd="url(#domain-arrow)"/><text x={(x+tx)/2+8} y={mid+3} fill="#657687" fontSize="10"><title>{e.label}</title>{historical?({load_observation:"加载监控",recorded_binding:"历史关联",inherits:"底线继承"}[e.kind]||e.label):e.label}</text></g>;})}</svg>
      {layout.nodes.map(n=><button key={n.key} style={{left:n.x,top:n.y}} className={`graph-node ${n.kind} ${n.role||''}`} aria-label={`查看${n.kind==='domain'?'域':n.kind==='process'?'进程':'文件'} ${n.title}`} onClick={event=>{event.currentTarget.focus();n.kind==='domain'?onDomain(n):n.kind==='process'?onProcess(n):onAudit(n.audit);}}>
        <span className="graph-node-kind">{n.kind==='domain'?(n.role==='baseline'?'启动底线':'任务权限'):n.kind==='process'?(n.role==='agent'?'Agent':'进程'):'文件资源'}<span aria-hidden="true">↗</span></span>
        <strong title={n.title}>{n.title}</strong>
        <span className="graph-node-tags">{n.kind==='domain'?<><span className={!historical&&fresh&&n.live?'live':''}>{!historical&&fresh&&n.live?'绑定已核验':'历史加载'}</span>{(n.labels||[]).map(label=><span key={label}>{label}</span>)}</>:n.kind==='process'?<><span>{historical?'历史 PID':'PID'} {n.pid}</span><span>{historical?'加载收据':n.domain_verified?'域已核验':'任务 cgroup'}</span></>:<span className="file-evidence">{['denied','correct_block'].includes(n.audit.result)?'拦截记录':'核验记录'}</span>}</span>
      </button>)}
    </div></div>:<div className="runtime-empty"><strong>尚无已登记执行域</strong><p>{historical?'没有已记录的历史加载关系。':'策略完成加载与核验后，显示真实域与进程。'}</p></div>}
    <div className="graph-legend"><span>实线：继承 / 进程关联</span><span>虚线：文件操作证据</span>{historical?<span>进程仅为历史 PID 记录，不代表当前在线。</span>:!graph.live&&<span>当前无已核验进程，域与文件为历史证据。</span>}</div>
  </section>;
}
