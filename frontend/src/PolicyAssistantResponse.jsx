import React from 'react';
import GenerationConfigurations from './GenerationConfigurations.jsx';
import {responseSentence} from './policyAssistantResponse.mjs';

function Notes({label,values=[],open=false}){
 const items=[...new Set(values.filter(Boolean))];
 if(!items.length)return null;
 return <details className="assistant-response-notes" open={open}><summary>{label} · {items.length} 项</summary><ul>{items.map(v=><li key={v}>{v}</li>)}</ul></details>;
}
export default function PolicyAssistantResponse({generation:g}){
 return <div className="assistant-response assistant-response-compact"><p>{responseSentence(g)}</p>
  {g.context_usage?.source_scope?.mode==='explicit_files'&&<p className="assistant-snapshot-note">正文范围：{g.context_usage.source_scope.body_paths.join('、')}</p>}
  <GenerationConfigurations generation={g} compact/>
  <Notes label="需要补充" values={g.questions} open={!g.items?.length}/><Notes label="待解决事项" values={g.gaps} open={!g.items?.length}/>
 </div>;
}
