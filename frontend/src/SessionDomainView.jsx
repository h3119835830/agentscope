import React from 'react';

export default function SessionDomainView({data,onPolicies}){
 return <div className="session-domain-view">
  <p className="field-note">{data?.notice||'正在读取已加载策略的作用范围。'}</p>
  {data?.coverage_complete===false&&<p role="alert" className="inline-notice warning">当前加载证据不完整，不能确认全部策略数量。</p>}
  <div className="session-domain-chain" aria-label="共享执行域的两类策略">{(data?.nodes||[]).filter(n=>['system','agent'].includes(n.id)).map(node=><button key={node.id} className={'session-domain-node scope-'+node.id} onClick={onPolicies}>
   <span>{node.title}</span><b>{node.count_label||'数量未完整取得'}</b><small>{node.status}</small><small>{node.applies_to}</small>
  </button>)}</div>
 </div>;
}
