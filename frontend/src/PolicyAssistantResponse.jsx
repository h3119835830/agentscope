import React from 'react';
import GenerationConfigurations from './GenerationConfigurations.jsx';
import PolicyContextEvidence from './PolicyContextEvidence.jsx';
import {analysisParts,generationOutcome,referenceFiles} from './policyAssistantResponse.mjs';

function Notes({label,values=[],open=false}){
 const items=[...new Set(values.filter(Boolean))];
 if(!items.length)return null;
 return <details className="assistant-response-notes" open={open}><summary>{label} · {items.length} 项</summary><ul>{items.map(v=><li key={v}>{v}</li>)}</ul></details>;
}
export default function PolicyAssistantResponse({generation:g}){
 const analysis=analysisParts(g.summary),usage=g.context_usage,files=referenceFiles(usage),shown=files.slice(0,3);
 return <div className="assistant-response"><p className="assistant-response-outcome">{generationOutcome(g)}</p>
  <section className="assistant-response-basis" aria-label="生成依据"><strong>生成依据</strong>
   {analysis.lead?<p>{analysis.lead}</p>:<p>{g.generation_state==='failed'?'本轮未完成分析，尚无完整生成依据。':'本轮未记录分析说明；以下仅展示实际资料和配置记录。'}</p>}
   {analysis.rest&&<details className="assistant-analysis-more"><summary>展开完整分析</summary><p>{analysis.rest}</p></details>}
   {shown.length>0&&<div className="assistant-read-files" aria-label="实际参考文件"><span>已读文件</span>{shown.map(f=><code key={JSON.stringify(f)} title={f.workspace||'上传参考'}>{f.path}</code>)}{files.length>shown.length&&<span>另 {files.length-shown.length} 个，见资料记录</span>}</div>}
   {!files.length&&usage&&<p className="assistant-response-reference-note">未读取文件正文；目录浏览、模板填写和匹配验证不计为正文读取。</p>}
  </section>
  <GenerationConfigurations generation={g}/>
  <Notes label="需要补充" values={g.questions} open={!g.items?.length}/><Notes label="待解决事项" values={g.gaps} open={!g.items?.length}/>
  {usage?<PolicyContextEvidence usage={usage}/>:g.reference_read&&<p className="assistant-response-reference-note">参考资料：{g.reference_read.workspace} · {g.reference_read.paths.join('、')}</p>}
 </div>;
}
