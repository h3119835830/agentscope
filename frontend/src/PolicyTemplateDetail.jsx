import React,{useEffect,useRef,useState} from 'react';
import {DslCode} from './DslCode.jsx';
import {createHandoff,createSystemHandoff,materializeTemplate,templateDefaults} from './agentPolicyHandoff.mjs';
import {agentProcessLabel,visibleAgentInstances} from './agentInstancePresentation.mjs';
import {tabKeys} from './consoleState.mjs';
import {operationLabel,effectLabel} from './policyRecordPresentation.mjs';
export default function PolicyTemplateDetail({template:t,agents=[],targetId='',onClose,onHandoff}){
 const system=t.scope_type==='system',dialog=useRef(null),origin=useRef(document.activeElement);
 const [tab,setTab]=useState('configuration'),[target,setTarget]=useState(targetId),[fields,setFields]=useState(null),[goal,setGoal]=useState(''),[error,setError]=useState('');
 const row=agents.find(a=>a.id===target),key=t.id+':'+target;
 const values=fields?.key===key?fields.values:templateDefaults(t,system?null:row);
 const [name,setName]=useState(t.name),[reason,setReason]=useState(t.reason);
 const adapted={...t,name,reason};
 let preview='',invalid='';try{preview=materializeTemplate(adapted,values,goal,'preview').original_dsl;}catch(e){invalid=e.message;}
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const tabs=[['configuration','配置'],['dsl','DSL 预览'],['conditions','适用条件']];
 function submit(e){e.preventDefault();try{if(!name.trim())throw Error('请填写策略名称。');if(!reason.trim()||/["\\\n\r]/.test(reason))throw Error('反馈说明不能包含引号、反斜杠或换行。');const candidate=system?createSystemHandoff(adapted,values,goal):createHandoff(adapted,values,goal,row);onHandoff(candidate);}catch(e){setError(e.message);}}
 return <dialog ref={dialog} className="policy-config-dialog" aria-label={'配置详情 · '+t.name} onCancel={e=>{e.preventDefault();onClose();}}><form onSubmit={submit}>
 <header className="policy-config-head"><div className="config-identity"><span className={'config-icon '+(system?'system':'')}>◇</span><div><span className="config-eyebrow">{system?'系统策略配置':'Agent 策略模板'} / {t.id}</span><h2>{t.name}</h2></div></div><button type="button" className="button ghost" onClick={onClose}>关闭</button></header>
 <div className="config-summary"><p>{t.summary}</p><div><span className="policy-layer">{system?'所有受控 Agent':'第二层 · Agent 专属'}</span><span className={'effect-pill effect-'+t.effect}>{effectLabel(t.effect)}</span><span className="config-state">候选 · 未应用</span></div></div>
 <div role="tablist" aria-label="配置详情" className="config-tabs">{tabs.map(([id,title])=><button type="button" key={id} role="tab" id={'config-tab-'+id} aria-selected={tab===id} aria-controls={'config-panel-'+id} tabIndex={tab===id?0:-1} onClick={()=>setTab(id)} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,setTab)}>{title}</button>)}</div>
 <div className="policy-config-body" role="tabpanel" id={'config-panel-'+tab} aria-labelledby={'config-tab-'+tab}>
 {tab==='configuration'&&<><section className="config-section"><div className="config-section-title"><span>01</span><div><h3>基本信息</h3><p>明确策略名称与适用范围</p></div></div><div className="config-fields"><label>策略名称<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)}/></label>{system?<div className="config-readonly"><span>适用范围</span><strong>所有受控 Agent</strong><small>各 Agent 继承此层约束</small></div>:<label>目标 Agent<select required aria-label="模板目标 Agent" value={target} onChange={e=>{setTarget(e.target.value);setError('');}}><option value="">请选择 Agent</option>{visibleAgentInstances(agents).map(a=><option key={a.id} value={a.id}>{agentProcessLabel(a)}{a.mode!=='controlled'?' · 仅观测':''}</option>)}</select></label>}</div></section>
 <section className="config-section"><div className="config-section-title"><span>02</span><div><h3>匹配条件</h3><p>设置保护对象与触发操作</p></div></div><div className="config-match"><div className="config-match-kind">{t.kind==='file'?'文件访问':t.kind==='workflow'?'执行顺序':'程序参数'}<small>{operationLabel(t.operation)}</small></div><div className="config-match-fields">{t.parameters.length?t.parameters.map(p=><label key={p.key}>{p.label}<input required maxLength={1000} className="config-path" value={values[p.key]||''} onChange={e=>setFields({key,values:{...values,[p.key]:e.target.value}})}/>{p.key==='target'&&<small>按填写的路径匹配；请核对具体文件或通配范围。</small>}</label>):<div className="config-readonly"><span>匹配参数</span><strong>git reset / clean / stash / --no-verify</strong></div>}</div></div></section>
 <section className="config-section"><div className="config-section-title"><span>03</span><div><h3>处置与反馈</h3><p>命中后执行的动作与反馈内容</p></div></div><div className="config-disposition"><span className={'effect-pill effect-'+t.effect}>{effectLabel(t.effect)}</span><span>{t.effect==='block'?'匹配操作将被阻止并返回原因':t.effect==='notify'?'保留事件并提醒 Agent': '匹配事件后终止违规进程'}</span></div><label>反馈说明<textarea required rows={3} maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label><label>补充约束说明（可选）<textarea rows={2} maxLength={1000} value={goal} onChange={e=>setGoal(e.target.value)} placeholder="说明本次配置的用途"/></label></section></>}
 {tab==='dsl'&&<section className="config-section"><div className="config-section-title"><span>DSL</span><div><h3>候选配置预览</h3><p>根据当前参数组装，尚未保存或校验</p></div></div><DslCode text={preview||invalid}/><p className="field-note">进入 DSL 编辑器后保存、校验，再核对受影响连接。</p></section>}
 {tab==='conditions'&&<section className="config-section"><h3>适用边界</h3><p className="config-boundary">{t.caveat}</p>{t.runtime_note&&<p className="inline-notice warning">{t.runtime_note}</p>}<h3>模板依据</h3>{t.evidence?<><p>{t.evidence.source_file} · 第 {t.evidence.source_lines} 行</p><blockquote>{t.evidence.directive}</blockquote><small>RQ1 原始样例的历史编译结果不代表此候选已编译或生效。</small></>:<p>{t.origin}</p>}</section>}
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}
 </div><footer className="policy-config-footer"><span>带入编辑器后仍需保存、校验与确认应用</span><button type="button" className="button ghost" onClick={onClose}>取消</button><button className="button primary" disabled={!!invalid||(!system&&row?.mode!=='controlled')}>{system?'生成系统策略候选':'带入 Agent DSL'}</button></footer>
 </form></dialog>;
}
