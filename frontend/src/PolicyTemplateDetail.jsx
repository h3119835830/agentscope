import React,{useEffect,useRef,useState} from 'react';
import {DslCode} from './DslCode.jsx';
import {createHandoff,createSystemHandoff,materializeTemplate,templateDefaults} from './agentPolicyHandoff.mjs';
import {policySources} from './policySources.mjs';
import {agentName,agentProcessLabel,visibleAgentInstances} from './agentInstancePresentation.mjs';
import {tabKeys} from './consoleState.mjs';
import {operationLabel,effectLabel} from './policyRecordPresentation.mjs';
export default function PolicyTemplateDetail({template:t,agents=[],targetId='',onClose,onHandoff,conversation=false,initialCandidate=null}){
 const system=t.scope_type==='system',dialog=useRef(null),origin=useRef(document.activeElement);
 const [tab,setTab]=useState('configuration'),[target,setTarget]=useState(targetId),[fields,setFields]=useState(()=>initialCandidate?{key:t.id+':'+targetId,values:initialCandidate.presentation.values}:null),[goal,setGoal]=useState(initialCandidate?.presentation?.goal||''),[error,setError]=useState('');
 const row=agents.find(a=>a.id===target),key=t.id+':'+target;
 const values=fields?.key===key?fields.values:templateDefaults(t,system?null:row);
 const [name,setName]=useState(initialCandidate?.presentation?.name||t.name),[reason,setReason]=useState(initialCandidate?.presentation?.reason||t.reason);
 const adapted={...t,name,reason};
 let preview='',invalid='',sources=[];
 try{sources=policySources(t,row,agents);preview=materializeTemplate(adapted,values,goal,'preview',sources).original_dsl;}catch(e){invalid=e.message;}
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const tabs=[['configuration','配置策略'],['dsl','DSL 预览']];
 function submit(e){e.preventDefault();try{
  if(!name.trim())throw Error('请填写策略名称。');
  const candidate=system?createSystemHandoff(adapted,values,goal,crypto.randomUUID(),sources):createHandoff(adapted,values,goal,row);
  onHandoff({...candidate,presentation:{name,values,reason,operation:t.operation,effect:t.effect,template:t,goal}});
 }catch(e){setError(e.message);}}
 return <dialog ref={dialog} className="policy-config-dialog customer-policy-dialog" aria-label={'配置详情 · '+t.name} onCancel={e=>{e.preventDefault();onClose();}}><form onSubmit={submit}>
 <header className="customer-config-head"><div className="customer-config-symbol" aria-hidden="true">◇</div><div><div className="customer-config-kicker">{system?'系统策略':'策略模板'}</div><h2>{t.name}</h2></div><button type="button" className="config-close" aria-label="关闭配置详情" onClick={onClose}>×</button></header>
 <div role="tablist" aria-label="配置详情" className="config-tabs">{tabs.map(([id,title])=><button type="button" key={id} role="tab" id={'config-tab-'+id} aria-selected={tab===id} aria-controls={'config-panel-'+id} tabIndex={tab===id?0:-1} onClick={()=>setTab(id)} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,setTab)}>{title}</button>)}</div>
 <div className="policy-config-body customer-config-body" role="tabpanel" id={'config-panel-'+tab} aria-labelledby={'config-tab-'+tab}>
 {tab==='configuration'?<div className="customer-config-layout"><div className="customer-config-form">
 <label className="customer-name-field">策略名称<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)}/></label>
 <section className="customer-config-section"><h3>适用对象</h3>{system?<><div className="customer-scope-line"><span className="customer-scope-icon">◎</span><div><strong>所有受控 Agent</strong><small>统一约束各 Agent 及其会话</small></div><span className="customer-scope-count">{sources.length} 个连接</span></div><div className="customer-agent-chips">{[...new Set(sources.map(s=>s.name))].map(n=><span key={n}>{n}</span>)}</div></>:conversation?<div className="customer-scope-line"><span className="customer-scope-icon">◇</span><div><strong>{row?agentName(row):'请选择 Agent'}</strong><small>此 Agent 的全部会话</small></div></div>:<label className="customer-agent-field">目标 Agent<select required aria-label="模板目标 Agent" value={target} onChange={e=>{setTarget(e.target.value);setError('');}}><option value="">请选择 Agent</option>{visibleAgentInstances(agents).map(a=><option key={a.id} value={a.id}>{agentProcessLabel(a)}{a.mode!=='controlled'?' · 仅观测':''}</option>)}</select></label>}</section>
 <section className="customer-config-section"><h3>触发条件</h3><div className="customer-operation"><span className="customer-event-dot"/><span>当 Agent 尝试</span><strong>{operationLabel(t.operation)}</strong></div>
 <div className="customer-condition-fields">{t.parameters.length?t.parameters.map(parameter=><label key={parameter.key}>{parameter.label}<div className="customer-path-input"><span aria-hidden="true">{parameter.key==='target'?'▱':'⌘'}</span><input required maxLength={1000} aria-label={parameter.label} className="config-path" value={values[parameter.key]||''} onChange={e=>setFields({key,values:{...values,[parameter.key]:e.target.value}})}/></div></label>):<p className="customer-fixed-condition">git reset / clean / stash / --no-verify</p>}</div>
 <small className="customer-field-help">{t.kind==='file'?'请核对具体文件或目录范围。':'请核对本 Agent 使用的命令与参数。'}</small></section>
 <section className="customer-config-section customer-response-section"><div className="customer-section-line"><h3>匹配后</h3><span className={'effect-pill effect-'+t.effect}>{effectLabel(t.effect)}</span></div><label>Agent 收到的反馈<textarea required rows={2} maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label></section>
 <details className="customer-config-more"><summary>补充说明</summary><label>用途说明（可选）<textarea rows={2} maxLength={1000} value={goal} onChange={e=>setGoal(e.target.value)} placeholder="补充这条策略的用途"/></label><p>{t.caveat}</p>{t.runtime_note&&<p>{t.runtime_note}</p>}</details>
 </div><aside className="customer-config-preview" aria-label="策略配置摘要"><div className="customer-preview-label"><span>配置摘要</span><span className="customer-draft-dot">待确认</span></div><div className={'customer-preview-effect effect-'+t.effect}><span aria-hidden="true">{t.effect==='block'?'⊘':t.effect==='notify'?'◉':'◇'}</span><strong>{effectLabel(t.effect)}</strong></div><p>{system?'对所有受控 Agent':row?agentName(row):'选择一个 Agent'}的指定操作设置约束。</p><dl><dt>保护对象</dt><dd className="customer-preview-target">{values.target||t.name}</dd><dt>触发操作</dt><dd>{operationLabel(t.operation)}</dd><dt>适用范围</dt><dd>{system?'全部受控连接及其会话':'所选 Agent 的全部会话'}</dd></dl><div className="customer-source-preview"><span>启动程序匹配</span>{[...new Set(sources.map(s=>s.pattern))].map(s=><code key={s}>{s}</code>)}{!sources.length&&<small>{row?'等待核验运行来源':'等待选择 Agent'}</small>}</div><div className="customer-confirm-note"><span>✓</span><p>生成后可检查配置<br/>由你确认后应用</p></div></aside></div>:<div className="customer-dsl-preview"><div className="customer-dsl-caption"><strong>当前配置</strong><span>候选 · 尚未应用</span></div><DslCode text={preview||invalid}/><div className="customer-dsl-agents"><strong>对应连接</strong>{sources.map(s=><div key={s.id}><span>{s.name}</span><code>{s.pattern}</code>{s.executable&&<small title={s.executable}>{s.executable}</small>}</div>)}</div></div>}
 {(error||invalid)&&<p role="alert" className="inline-notice warning">{error||invalid}</p>}
 </div><footer className="policy-config-footer customer-config-footer"><span>生成候选，应用前由你确认</span><button type="button" className="button ghost" onClick={onClose}>取消</button><button className="button primary" disabled={!!invalid||!name.trim()||(!system&&row?.mode!=='controlled')}>{conversation?'生成候选':system?'生成系统策略候选':'带入 Agent DSL'}<span aria-hidden="true"> →</span></button></footer>
 </form></dialog>;
}
