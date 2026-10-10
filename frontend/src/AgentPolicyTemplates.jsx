import React,{useEffect,useState} from 'react';
import catalogue from './rq1-agent-templates.json';
import {createHandoff,materializeTemplate,templateDefaults} from './agentPolicyHandoff.mjs';
import {agentName,agentProcessLabel,visibleAgentInstances} from './agentInstancePresentation.mjs';
import {DslCode} from './ActPlanePolicies.jsx';
import {tabKeys} from './consoleState.mjs';
export default function AgentPolicyTemplates({agents=[],targetId='',fixedTarget=false,onHandoff}){
 const [chosen,setChosen]=useState(catalogue.templates[0].id),[valueState,setValueState]=useState({key:'',values:{}}),[target,setTarget]=useState(targetId),[goal,setGoal]=useState(''),[query,setQuery]=useState(''),[category,setCategory]=useState(''),[error,setError]=useState('');
 const template=catalogue.templates.find(t=>t.id===chosen),choices=visibleAgentInstances(agents),row=agents.find(a=>a.id===(fixedTarget?targetId:target));
 const contextKey=chosen+':'+(row?.id||'');
 const values=valueState.key===contextKey?valueState.values:templateDefaults(template,row);
 function setValues(next){setValueState({key:contextKey,values:next});}
 useEffect(()=>{setValues(templateDefaults(template,row));setError('');},[chosen,row?.id]);
 useEffect(()=>{setTarget(targetId);},[targetId]);
 let preview='';try{preview=materializeTemplate(template,values,goal,'preview').original_dsl;}catch{}
 const shown=catalogue.templates.filter(t=>(!category||t.category===category)&&(t.name+' '+t.summary).includes(query));
 useEffect(()=>{if(shown.length&&!shown.some(t=>t.id===chosen))setChosen(shown[0].id);},[query,category,chosen]);
 return <section className="agent-template-library" aria-label="Agent 策略模板"><div className="policy-page-heading"><div><h2>策略与模板</h2><p>精选 6 个 RQ1 候选模板，用于第二层 Agent 策略。</p></div><span className="policy-layer">第二层 · Agent</span></div>
 <div className="template-filters"><label>搜索模板<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索策略名称"/></label><label>分类<select value={category} onChange={e=>setCategory(e.target.value)}><option value="">全部分类</option>{[...new Set(catalogue.templates.map(t=>t.category))].map(c=><option key={c}>{c}</option>)}</select></label></div>
 <div className="template-layout"><div className="template-cards" role="tablist" aria-label="选择策略模板" aria-orientation="vertical">{shown.map(t=><button role="tab" key={t.id} id={'template-'+t.id} aria-controls="template-configuration" aria-selected={chosen===t.id} tabIndex={chosen===t.id||!shown.some(x=>x.id===chosen)&&shown[0]===t?0:-1} className={'template-card '+(chosen===t.id?'selected':'')} onClick={()=>setChosen(t.id)} onKeyDown={e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const next=(shown.indexOf(t)+(e.key==='ArrowDown'?1:-1)+shown.length)%shown.length;setChosen(shown[next].id);e.currentTarget.parentElement.children[next].focus();}else tabKeys(e,shown.map(x=>x.id),chosen,setChosen);}}><span>{t.category} · {t.effect}</span><b>{t.name}</b><small>{t.summary}</small></button>)}{!shown.length&&<p className="task-empty">没有匹配的模板。</p>}</div>
 {shown.length>0&&<form className="template-configuration" id="template-configuration" role="tabpanel" aria-labelledby={'template-'+chosen} onSubmit={e=>{e.preventDefault();try{onHandoff(createHandoff(template,values,goal,row));setError('');}catch(e){setError(e.message);}}}><h3>{template.name}</h3>
 {!fixedTarget&&<label>导入到 Agent<select required aria-label="模板目标 Agent" value={target} onChange={e=>setTarget(e.target.value)}><option value="">请选择 Agent</option>{choices.map(a=><option key={a.id} value={a.id}>{agentProcessLabel(a)}{a.mode!=='controlled'?' · 仅观测':''}</option>)}</select></label>}
 {fixedTarget&&<p className="template-target">导入到 <b>{row?agentName(row):'尚未选择 Agent'}</b></p>}
 {template.parameters.map(p=><label key={p.key}>{p.label}<input required maxLength={1000} value={values[p.key]||''} onChange={e=>setValues({...values,[p.key]:e.target.value})}/></label>)}
 <label>策略说明（可选）<textarea maxLength={1000} rows={2} value={goal} onChange={e=>setGoal(e.target.value)} placeholder="填写当前项目需要的约束"/></label>
 {template.parameters.some(p=>p.key==='target')&&<p className="field-note">请核对文件范围；此模板只匹配填写的路径。</p>}<p className="template-caveat">{template.caveat}</p>{template.runtime_note&&<p className="inline-notice warning">{template.runtime_note}</p>}<details><summary>预览候选 DSL · 尚未校验</summary><DslCode text={preview||'填写参数后显示候选 DSL'}/></details>
 <details><summary>研究样例依据</summary><p>{template.uid} · {template.evidence.source_file} · {template.evidence.source_lines} 行</p><p>{template.evidence.directive}</p><p>原始数据：607 条；样例的历史编译结果不代表此候选已编译或生效。</p></details>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}{row?.mode!=='controlled'&&<p className="field-note">请选择受控连接，才能进入对应 Agent 的 DSL 编辑器。</p>}
 <button className="button primary" disabled={row?.mode!=='controlled'}>带入此 Agent 的 DSL 编辑器</button><p className="field-note">追加候选文档，保留已有策略。保存并校验后，仍需你确认应用。</p></form>}</div></section>;
}
