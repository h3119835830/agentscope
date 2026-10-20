import React from 'react';

export default function TemplateExecutionSupport({template}){
 const support=template.execution_support,proof=support?.verification;
 if(!support)return null;
 return <section className="tpl-execution-support" aria-label="模板实际执行能力">
  <h3>实际执行能力 <small>{support.event_type}</small></h3>
  <p className="spl-note spl-attention">{support.status==='unsupported'?'ActPlane 暂不支持 · 仅可保存参数草案，不能提交审批或应用':support.status==='legacy'?'历史模板 · 已由专用 Git 模板替代，已有配置保持原版本':'有限支持 · 按下列边界执行，提交时仍需通过实际编译和目标核验'}</p>
  {proof&&<p className="spl-note">{proof.state==='rejected'?'已实测拒绝提交与应用 · 暂不支持运行拦截':proof.state==='verified'?'真实运行验收 · '+proof.cases+' 项通过 · '+proof.effects.join(' / '):'尚无匹配当前模板执行合同的真实运行验收记录'}</p>}
  <details><summary>查看已支持能力与限制</summary><dl>{[['supported','已支持'],['unsupported','暂不支持'],['boundary','执行边界']].map(([key,label])=>support[key]?.length?<div key={key}><dt>{label}</dt><dd><ul>{support[key].map(value=><li key={value}>{value}</li>)}</ul></dd></div>:null)}</dl>{['verified','rejected'].includes(proof?.state)&&<p className="spl-note">{proof.date} · {proof.scope} 实测记录不代表当前 Agent 已加载或生效。</p>}</details>
 </section>;
}

export function TemplateParameterInput({definition:p,value,onChange,label=p.label}){
 if(p.type==='choices'){
  const selected=Array.isArray(value)?value:String(value??'').split(',');
  return <div className="spl-checks" role="group" aria-label={label}>{p.options.map(option=><label key={option}><input type="checkbox" aria-label={label+' '+option} checked={selected.includes(option)} onChange={e=>onChange((e.target.checked?[...selected.filter(Boolean),option]:selected.filter(v=>v!==option)).sort().join(','))}/>{option}</label>)}</div>;
 }
 if(p.type==='lines')return <textarea aria-label={label} required rows={3} maxLength={10000} value={value??''} onChange={e=>onChange(e.target.value)}/>;
 return <input aria-label={label} readOnly={p.readOnly} required type={p.type==='integer'?'number':'text'} min={p.minimum} max={p.maximum} step={p.type==='integer'?1:undefined} maxLength={1000} value={value??''} onChange={e=>onChange(e.target.value)} placeholder={p.type==='path'?'/w/0/实际文件或目录':undefined}/>;
}
