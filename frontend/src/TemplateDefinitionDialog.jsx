import React,{useEffect,useRef,useState} from 'react';
import {effectLabel,operationLabel} from './policyRecordPresentation.mjs';
import TemplateExecutionSupport,{TemplateParameterInput} from './TemplateExecutionSupport.jsx';
import TemplateDslPreview,{FixedTemplateCommand,TemplateDslPreviewResult} from './TemplateDslPreview.jsx';

const typeLabel={path:'路径',lines:'多行文本',program:'程序名或路径',endpoint:'IPv4 地址或前缀',operations:'操作复选',effect:'动作选择',text:'文本',choices:'选项复选',integer:'整数'};
const parameterValues=value=>Array.isArray(value)?value:String(value??'').split(',').map(v=>v.trim()).filter(Boolean);
function defaultText(template,parameter){
 const value=parameter.type==='effect'?template.effect:parameter.default;
 if(value===undefined||value===null||value===''||(Array.isArray(value)&&!value.length))return '未设置，由子配置填写';
 if(parameter.type==='effect')return effectLabel(value);
 if(parameter.type==='operations')return parameterValues(value).map(operationLabel).join('、');
 return Array.isArray(value)?value.join(parameter.type==='lines'?'\n':'、'):parameter.type==='choices'?parameterValues(value).join('、'):String(value);
}
function parameterOptions(template,parameter){
 if(parameter.type==='operations')return (template.allowed_operations||['write','unlink']).map(operationLabel).join('、');
 if(parameter.type==='effect')return (template.allowed_effects||['block','notify','kill']).map(effectLabel).join('、');
 return parameter.options?.join('、');
}
function parameterGuidance(parameter){
 const range=parameter.type==='integer'&&[parameter.minimum,parameter.maximum].some(v=>v!==undefined)?'取值范围：'+(parameter.minimum??'不限')+' ～ '+(parameter.maximum??'不限')+'。':'';
 return [parameter.help||({path:'填写实际文件或目录路径。',lines:'每行填写一项，匹配规则以模板说明为准。',program:'填写程序名或可执行路径。',endpoint:'填写 IPv4 地址或地址前缀。',operations:'在子配置中选择需要匹配的操作。',effect:'在子配置中选择匹配后的动作。',choices:'可从提供的选项中选择一项或多项。',integer:'填写整数。',text:'填写文本。'})[parameter.type],range].filter(Boolean).join(' ');
}

export function TemplateDefinitionContent({template}){
 return <>
  <p className="upl-template-description">{template.description||template.summary}</p>
  <dl className="upl-template-facts"><dt>默认处置</dt><dd>{effectLabel(template.effect)}</dd><dt>适用范围</dt><dd>{template.scopes?.map(s=>({system:'全部受控 Agent',agent:'指定 Agent',workspace:'历史工作区'})[s]||s).join('、')||'未提供'}</dd>{template.fixed_fields&&<><dt>固定命令</dt><dd><code>{[template.fixed_fields.program,template.fixed_fields.command].filter(Boolean).join(' ')}</code><small>由模板固定，子配置不能修改。</small></dd></>}</dl>
  <section className="upl-template-parameters" aria-label="模板配置项与默认值"><h3>配置项与默认值</h3><p className="spl-note">以下为模板默认值；已保存的子配置使用各自绑定的模板版本。</p>
   {template.parameters.length?<dl className="upl-template-parameter-list">{template.parameters.map(parameter=><div key={parameter.key} className="upl-template-parameter"><dt>{parameter.label}<small>{typeLabel[parameter.type]||'文本'}</small></dt><dd><span className="upl-template-default-label">默认值</span><div className="upl-template-default">{defaultText(template,parameter)}</div>{parameterOptions(template,parameter)&&<p className="upl-template-options">可选：{parameterOptions(template,parameter)}</p>}<p className="upl-template-guidance">{parameterGuidance(parameter)}</p></dd></div>)}</dl>:<p>此模板使用固定条件，没有可填写的配置项。</p>}
  </section>
  {template.reason&&<section className="upl-template-reason"><h3>反馈原因</h3><p>{template.reason}</p></section>}
  {template.note&&<p className="spl-note spl-attention">{template.note}</p>}
  {Object.entries(template.disabled_effects||{}).map(([effect,message])=><p className="spl-note spl-attention" key={effect}>{effectLabel(effect)}：{message}</p>)}
  <TemplateExecutionSupport template={template}/>
  <details className="upl-template-dsl"><summary>查看 DSL 预览</summary><TemplateDslPreviewResult result={template.dsl_preview||{state:'unavailable'}} readOnly/></details>
 </>;
}
export default function TemplateDefinitionDialog({template,post,onClose,onSaved}){
 const dialog=useRef(null),origin=useRef(document.activeElement),request=useRef(crypto.randomUUID());
 const [name,setName]=useState(template.name),[description,setDescription]=useState(template.description||template.summary),[effect,setEffect]=useState(template.effect);
 const [parameters,setParameters]=useState(()=>template.parameters.map(p=>({key:p.key,label:p.label,default:String(p.default??'')}))),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [maintaining,setMaintaining]=useState(false);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const readOnly=!!template.retired;
 const changed=()=>{request.current=crypto.randomUUID();};
 function field(key,property,value){setParameters(old=>old.map(p=>p.key===key?{...p,[property]:value}:p));changed();}
 function action(value){setEffect(value);setParameters(old=>old.map(p=>template.parameters.find(def=>def.key===p.key).type==='effect'?{...p,default:value}:p));changed();}
 async function save(e){e.preventDefault();if(busy||readOnly)return;setBusy(true);setError('');try{
  const saved=await post('/api/policy-templates/'+encodeURIComponent(template.id)+'/versions',{name,description,effect,parameters,base_version:template.version,request_key:request.current});await onSaved(saved);
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 if(!maintaining)return <dialog ref={dialog} className="spl-dialog upl-template-editor" aria-label={'模板详情：'+template.name} onCancel={e=>{e.preventDefault();onClose();}}><header className="spl-editor-head"><div><small>模板详情 · v{template.version}</small><h2>{template.name}</h2></div><button type="button" aria-label="关闭模板详情" onClick={onClose}>×</button></header><div className="spl-editor-body upl-template-readonly"><TemplateDefinitionContent template={template}/><details className="upl-template-advanced"><summary>高级操作</summary><p>维护模板会发布新版本，不修改既有配置或运行策略。</p><button className="button ghost" disabled={readOnly} onClick={()=>setMaintaining(true)}>维护模板</button></details></div><footer className="spl-editor-footer"><button className="button ghost" onClick={onClose}>关闭</button></footer></dialog>;
 return <dialog ref={dialog} className="spl-dialog upl-template-editor" aria-label={'模板详情：'+template.name} onCancel={e=>{e.preventDefault();if(!busy)onClose();}}><form onSubmit={save}>
  <header className="spl-editor-head"><span className="spl-symbol">◇</span><div><small>模板详情 · v{template.version}</small><h2>{template.name}</h2></div><button type="button" aria-label="关闭模板详情" disabled={busy} onClick={onClose}>×</button></header>
  <div className="spl-editor-body spl-form">{error&&<p role="alert" className="spl-error">{error}</p>}
   <fieldset className="tpl-readonly-fields" disabled={readOnly}><label>模板名称<input aria-label="模板名称" required maxLength={120} value={name} onChange={e=>{setName(e.target.value);changed();}}/></label>
   <label>说明<textarea aria-label="模板说明" required maxLength={3000} rows={3} value={description} onChange={e=>{setDescription(e.target.value);changed();}}/></label>
   <FixedTemplateCommand template={template}/>
   <label>默认动作<select aria-label="模板默认动作" value={effect} onChange={e=>action(e.target.value)}>{(template.allowed_effects||['block','notify','kill']).map(value=><option value={value} key={value}>{effectLabel(value)}</option>)}{Object.keys(template.disabled_effects||{}).map(value=><option key={value} value={value} disabled>{value}（暂不支持事前阻断）</option>)}</select></label>
   </fieldset><TemplateExecutionSupport template={template}/><fieldset className="tpl-readonly-fields" disabled={readOnly}>
   <h3>配置项定义</h3><div className="upl-template-fields-scroll"><table className="upl-template-fields" aria-label="模板配置项定义"><thead><tr><th>参数键</th><th>配置项名称</th><th>填写方式</th><th>默认值</th></tr></thead><tbody>{template.parameters.map(def=>{const value=parameters.find(p=>p.key===def.key);return <tr key={def.key}>
    <td><code>{def.key}</code></td><td><input aria-label={def.key+' 配置项名称'} required maxLength={120} value={value.label} onChange={e=>field(def.key,'label',e.target.value)}/>{def.help&&<small>{def.help}</small>}</td><td>{typeLabel[def.type]||'文本'}</td>
    <td>{['choices','integer'].includes(def.type)?<TemplateParameterInput definition={def} label={def.key+' 默认值'} value={value.default} onChange={v=>field(def.key,'default',v)}/>:def.type==='effect'?<span>{effectLabel(effect)}（与默认动作一致）</span>:def.type==='operations'?<div className="upl-template-operations">{(template.allowed_operations||['write','unlink']).map(op=><label key={op}><input type="checkbox" aria-label={def.key+' 默认'+operationLabel(op)} checked={value.default.split(',').includes(op)} onChange={e=>field(def.key,'default',(e.target.checked?[...value.default.split(',').filter(Boolean),op]:value.default.split(',').filter(v=>v!==op)).join(','))}/>{operationLabel(op)}</label>)}</div>:def.type==='lines'?<textarea aria-label={def.key+' 默认值'} rows={2} maxLength={10000} value={value.default} placeholder="留空，由子配置填写" onChange={e=>field(def.key,'default',e.target.value)}/>:<input aria-label={def.key+' 默认值'} maxLength={10000} value={value.default} placeholder="留空，由子配置填写" onChange={e=>field(def.key,'default',e.target.value)}/>}</td>
   </tr>;})}{!template.parameters.length&&<tr><td colSpan={4}>此模板使用固定条件，没有配置项。</td></tr>}</tbody></table></div>
   <p className="spl-note">配置项名称和默认值可编辑；参数键和填写方式由执行器限定，暂不支持新增、删除或更换类型。</p>
   </fieldset><TemplateDslPreview template={template} parameters={Object.fromEntries(parameters.map(p=>[p.key,p.default]))} effect={effect} post={post}/>
  </div><footer className="spl-editor-footer"><span>{readOnly?'历史模板只读；请使用新版 Git 模板。已生效策略可审批停用。':'保存为模板新版本；已有子配置和运行策略保持原版本。'}</span><button type="button" className="button ghost" disabled={busy} onClick={onClose}>取消</button>{!readOnly&&<button className="button primary" disabled={busy}>{busy?'正在保存…':'保存模板新版本'}</button>}</footer>
 </form></dialog>;
}
