import RecordBadge from './RecordBadge.jsx';
import React,{useState} from 'react';
import {actionLabels,networkSentence,ruleSentence,replaceRule,removeRule,policyChanges,sameBaseline,proposalDraft} from './instanceSecurity.mjs';

function Facts({values}){return <dl className="security-facts">{values.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{value??'—'}</dd></React.Fragment>)}</dl>;}
export function RuleForm({initial,network,title,busy,stale,onSubmit,onCancel}){
 const [rule,setRule]=useState(()=>structuredClone(initial||{})),[mode,setMode]=useState(network);
 const behavior=rule.action==='behavior';
 const changeAction=action=>setRule({...rule,action,target:action===rule.action?rule.target:'',effect:action==='network'||action==='behavior'?'deny':rule.effect==='confirm'&&action!=='tool'?'deny':rule.effect});
 return <form className="security-edit" onSubmit={e=>{e.preventDefault();onSubmit(network!==undefined?mode:rule);}}>
  <div className="security-edit-head"><h3>{title||(network!==undefined?'网络权限':'编辑安全规则')}</h3><button type="button" className="button tiny ghost" disabled={busy} onClick={onCancel}>返回规则列表</button></div>
  {network!==undefined?<label>允许连接的范围<select autoFocus disabled={busy} value={mode} onChange={e=>setMode(e.target.value)}><option value="model_only">本机控制端、DNS 与模型地址</option><option value="disabled">仅保留本机控制端</option></select></label>:<>
   <div className="security-edit-pair"><label>行为<select autoFocus disabled={busy} value={rule.action} onChange={e=>changeAction(e.target.value)}>{Object.entries(actionLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
   {!behavior&&<label>决定<select disabled={busy} value={rule.effect} onChange={e=>setRule({...rule,effect:e.target.value})}>{rule.action!=='network'&&<option value="allow">允许</option>}<option value="deny">禁止</option>{rule.action==='tool'&&<option value="confirm">确认后允许</option>}</select></label>}</div>
   {!behavior&&<label>{rule.action==='network'?'IPv4 地址':rule.action==='tool'?'工具名称':'目标文件或目录'}<input required disabled={busy} value={rule.target} onChange={e=>setRule({...rule,target:e.target.value})} placeholder={rule.action==='network'?'例如 203.0.113.8':rule.action==='tool'?'原生工具名称':'已登记资源内的绝对路径'}/></label>}
   <label>{behavior?'行为约定':'补充说明'}<textarea required={behavior} disabled={busy} maxLength={2000} rows={3} value={rule.text||''} onChange={e=>setRule({...rule,text:e.target.value})}/></label>
  </>}
  <p className="field-note">修改影响此 Agent 实例的全部会话。收紧自动应用，放宽权限需确认；运行中的实例会暂停并重建执行进程。</p>
  {stale&&<p role="alert">配置已有更新，请返回列表后重新编辑。</p>}
  <div className="actions"><button className="button primary" disabled={busy||stale}>提交更改</button><button type="button" className="button ghost" disabled={busy} onClick={onCancel}>取消</button></div>
 </form>;
}
export function PendingChange({proposal,current,busy,onConfirm}){
 return <section className="security-pending" aria-label="待确认的权限变更">
  <div className="security-pending-head"><h3>待确认的权限变更</h3><span>影响全部会话</span></div>
  <p>这项变更会放宽权限，当前规则尚未被替换。</p>
  <dl className="security-change-list">{policyChanges(current,proposal.policy).map((change,i)=><React.Fragment key={i}><dt>{change.operation}</dt><dd>{change.sentence}</dd></React.Fragment>)}</dl>
  <details><summary>查看变更后的完整配置</summary><ul className="security-exact-rules"><li>{networkSentence(proposal.policy.network)}</li>{proposal.policy.rules.map((rule,i)=><li key={i}>{ruleSentence(rule)}</li>)}</ul></details>
  <button type="button" className="button primary" disabled={busy} onClick={()=>onConfirm(proposal)}>确认此变更并应用</button>
 </section>;
}
export default function InstanceSecurity({row,pending=[],busy=false,onPropose,onConfirm}){
 const [draft,setDraft]=useState(null),[detail,setDetail]=useState(null),[message,setMessage]=useState(''),[pendingId,setPendingId]=useState('');
 const policy=row.policy,resources=row.resources||[];
 const recordFor=rule=>(row.policy_records||[]).find(r=>r.action===rule.action&&r.effect===rule.effect&&r.target===rule.target&&r.text===rule.text);
 const resultFor=rule=>rule.action==='behavior'?'行为约定':recordFor(rule)?.result||(row.active?'已核验':'待启动核验');
 const capture=(kind,index=null)=>{setMessage('');setDetail(null);setDraft({...proposalDraft(row,policy),kind,index,initial:index===null?{action:'write',effect:'deny',target:'',text:''}:structuredClone(policy.rules[index])});};
 const showDetail=index=>setDetail({...proposalDraft(row,policy),index,rule:index==='network'?null:structuredClone(policy.rules[index])});
 async function submit(candidate){
  const outcome=await onPropose(candidate);
  if(!outcome?.ok)return;
  setDraft(null);setDetail(null);
  if(outcome.value.state==='pending'){setPendingId(outcome.value.id);setMessage('变更已提交，确认后才会替换当前规则。');}
  else setMessage('安全配置已更新。');
 }
 async function confirm(proposal){const outcome=await onConfirm(proposal);if(outcome?.ok){setPendingId('');setMessage('变更已应用。');}}
 const selected=pending.find(p=>p.id===pendingId)||pending[0];
 if(draft)return <div className="instance-security"><RuleForm key={draft.kind+draft.index} title={draft.kind==='network'?'网络权限':draft.kind==='add'?'添加安全规则':'编辑安全规则'} initial={draft.kind==='network'?undefined:draft.initial} network={draft.kind==='network'?draft.policy.network:undefined} busy={busy} stale={!sameBaseline(row,draft)} onCancel={()=>setDraft(null)} onSubmit={value=>submit({...draft,policy:draft.kind==='network'?{...draft.policy,network:value}:replaceRule(draft.policy,draft.index,value)})}/></div>;
 if(detail!==null){
  const rule=detail.rule,record=rule?recordFor(rule):null,stale=!sameBaseline(row,detail);
  return <div className="instance-security"><div className="security-edit-head"><h3>规则详情</h3><button type="button" className="button tiny ghost" onClick={()=>setDetail(null)}>返回规则列表</button></div>
   <Facts values={rule?[['完整安全规则',ruleSentence(rule)],['目标',rule.target||'整个任务行为'],['来源',record?.source||'安全配置'],['执行方式',record?.method||'尚未提供'],['当前状态',stale?'配置已变化，请返回列表':resultFor(rule)]]:[['完整安全规则',networkSentence(detail.policy.network)],['执行方式','实例 cgroup 网络过滤'],['当前状态',stale?'配置已变化，请返回列表':row.active?'已核验':'待启动核验']]}/>
   <div className="actions"><button type="button" className="button primary" disabled={busy||stale} onClick={()=>capture(rule?'edit':'network',rule?detail.index:null)}>编辑此规则</button></div>
  </div>;
 }
 return <div className="instance-security">
  <div className="security-toolbar"><p>此实例的全部会话共享这些规则。更改时会暂停运行并重新核验。</p><button type="button" className="button primary" disabled={busy} onClick={()=>capture('add')}>添加规则</button></div>
  {message&&<p className="security-message" role="status">{message}</p>}
  <div className="security-table-scroll" tabIndex={0} aria-label="安全规则记录"><table className="security-rules"><colgroup><col/><col className="security-status-col"/><col className="security-actions-col"/></colgroup><thead><tr><th>安全规则</th><th>当前状态</th><th>操作</th></tr></thead><tbody>
   {policy.rules.map((rule,i)=><tr key={i}><td><p className="security-sentence" data-effect={rule.action==='behavior'?'behavior':rule.effect}>{ruleSentence(rule,resources,false)}</p></td><td><RecordBadge>{resultFor(rule)}</RecordBadge></td><td><div className="security-actions"><button type="button" onClick={()=>showDetail(i)}>详情</button><button type="button" disabled={busy} onClick={()=>capture('edit',i)}>编辑</button><button type="button" className="security-delete" disabled={busy} onClick={()=>{setMessage('');submit(proposalDraft(row,removeRule(policy,i)));}}>删除</button></div></td></tr>)}
   <tr><td><p className="security-sentence">{networkSentence(policy.network)}</p></td><td><RecordBadge>{row.active?'已核验':'待启动核验'}</RecordBadge></td><td><div className="security-actions"><button type="button" onClick={()=>showDetail('network')}>详情</button><button type="button" disabled={busy} onClick={()=>capture('network')}>编辑</button></div></td></tr>
  </tbody></table></div>
  {!policy.rules.length&&<p className="field-note">尚未添加文件、工具或行为规则，资源目录保持默认只读。</p>}
  <details className="security-baseline"><summary>基础保护（只读）</summary><p>全部会话与子进程继承平台底线，不能写入控制目录或自行扩权。已登记资源默认只读，额外写入须有明确授权。</p><p>行为约定用于指导 Agent，不作为强制拦截声明。</p></details>
  {!!pending.length&&<>{pending.length>1&&<label className="security-pending-select">待确认变更<select value={selected.id} onChange={e=>setPendingId(e.target.value)}>{pending.map((p,i)=><option key={p.id} value={p.id}>变更 {i+1}</option>)}</select></label>}<PendingChange proposal={selected} current={policy} busy={busy} onConfirm={confirm}/></>}
 </div>;
}
