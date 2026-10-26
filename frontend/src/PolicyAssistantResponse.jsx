import React from 'react';
import GenerationConfigurations from './GenerationConfigurations.jsx';
import PolicyContextEvidence from './PolicyContextEvidence.jsx';
import {responseSentence} from './policyAssistantResponse.mjs';

function Notes({label,values=[],open=false}){
 const items=[...new Set(values.filter(Boolean))];
 if(!items.length)return null;
 return <details className="assistant-response-notes" open={open}><summary>{label} · {items.length} 项</summary><ul>{items.map(v=><li key={v}>{v}</li>)}</ul></details>;
}
export default function PolicyAssistantResponse({generation:g}){
 const usage=g.context_usage;
 return <div className="assistant-response assistant-response-compact"><p>{responseSentence(g)}</p>
  <GenerationConfigurations generation={g} compact/>
  <Notes label="需要补充" values={g.questions} open={!g.items?.length}/><Notes label="待解决事项" values={g.gaps} open={!g.items?.length}/>
  <details className="assistant-response-details"><summary>查看详情</summary>
   {g.summary&&<p className="assistant-full-analysis">{g.summary}</p>}
   <GenerationConfigurations generation={g}/>
   {usage?<PolicyContextEvidence usage={usage}/>:g.reference_read&&<p className="assistant-response-reference-note">参考资料：{g.reference_read.workspace} · {g.reference_read.paths.join('、')}</p>}
  </details>
 </div>;
}
