import React,{useEffect,useRef,useState} from 'react';
import {DslCode} from './DslCode.jsx';
import {LabelSourceSummary} from './LabelManagement.jsx';

export function FixedTemplateCommand({template}){
 const fixed=template.fixed_fields;
 if(!fixed)return null;
 return <label>固定命令<input aria-label="固定命令" readOnly value={[fixed.program,fixed.command].filter(Boolean).join(' ')}/><small>由模板固定，手工配置和 Agent 均不能修改。</small></label>;
}

export function UnavailableTemplateEffects({template}){
 return Object.entries(template.disabled_effects||{}).map(([effect,reason])=><label key={effect} className="tpl-unavailable-action" title={reason}><input type="radio" disabled aria-label={effect+' 暂不支持'}/><strong>{effect}</strong><span>暂不支持</span></label>);
}

export default function TemplateDslPreview({template,parameters,effect,reason,post,scopeId,labelSourceRefs}){
 const [result,setResult]=useState(null),sequence=useRef(0);
 const input=JSON.stringify({template_version:template.version,parameters,effect,reason,...(labelSourceRefs?{scope_id:scopeId,label_source_refs:labelSourceRefs}:{})});
 useEffect(()=>{
  const n=++sequence.current;setResult(null);
  const timer=setTimeout(()=>post('/api/policy-templates/'+encodeURIComponent(template.id)+'/preview',JSON.parse(input))
   .then(value=>{if(sequence.current===n)setResult(value);})
   .catch(error=>{if(sequence.current===n)setResult({state:'invalid',errors:[error.message]});}),200);
  return()=>{clearTimeout(timer);sequence.current++;};
 },[template.id,input,post]);
 return <TemplateDslPreviewResult result={result}/>;
}

export function TemplateDslPreviewResult({result,readOnly=false}){
 return <section className="tpl-dsl-preview" aria-label={readOnly?'模板默认参数 DSL 预览':'当前参数 DSL 预览'}><h3>DSL 预览</h3>
  {!result?<p role="status" className="spl-note">正在生成预览…</p>:<>
   <p className="spl-note">{result.state==='unavailable'?'服务端尚未提供此模板的默认参数预览。':result.state==='unsupported'?'ActPlane 暂不支持此执行语义，不生成可执行 DSL；仅能保存参数草案。':result.state==='invalid'?(readOnly?'模板默认参数未通过预览校验，请维护模板后重新核对。':'参数未通过校验，请修改后再预览。'):result.state==='incomplete'?'模板规则已固定；待填写：'+(result.missing||[]).join('、')+'。双花括号表示尚未填写的参数。':readOnly?'服务端提供的模板默认参数预览；具体配置需另行保存、编译、审批和应用。':'根据当前动作和参数生成，仅供预览；保存、编译、审批和应用仍分别执行。'}</p>
   {result.errors?.length>0&&<p role="alert" className="spl-error">{result.errors.join('；')}</p>}
   {result.dsl&&<DslCode text={result.dsl}/>}
   <LabelSourceSummary sources={result.label_sources}/>
  </>}
 </section>;
}
