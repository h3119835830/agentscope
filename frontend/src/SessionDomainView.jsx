import React from 'react';

export default function SessionDomainView({data,onPolicies,onConfigure}){
 return <div className="session-domain-view">
  <p className="field-note">{data?.notice||'正在读取约束归属与继承关系。'}</p>
  {data?.coverage_complete===false&&<p role="alert" className="inline-notice warning">约束信息尚不完整，已取得的数量不能作为全部约束数量。</p>}
  <div className="session-domain-chain" aria-label="约束归属与继承关系">{(data?.nodes||[]).map(node=><button key={node.id} className={'session-domain-node scope-'+node.id} onClick={onPolicies}>
   <span>{node.title}</span><b>{node.count_label||'数量未完整取得'}</b><small>{node.status}</small><small>{node.applies_to}</small>
  </button>)}</div>
  <div className="session-config-actions"><button className="button ghost" onClick={()=>onConfigure('system')}>系统策略</button><button className="button ghost" onClick={()=>onConfigure('agent')}>Agent 策略</button></div>
 </div>;
}
