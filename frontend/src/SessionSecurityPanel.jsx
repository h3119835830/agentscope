import React,{useEffect,useRef,useState} from 'react';
import RecordBadge from './RecordBadge.jsx';
import PolicyLifecycleDialog from './PolicyLifecycleDialog.jsx';
import {scopeNames,actionNames,effectNames,impact,changeRequest,visibleControls} from './sessionSecurity.mjs';
import './sessionSecurity.css';

export function SecurityChangeDialog({view,draft,busy,onClose,onSubmit}){
 const c=draft.control,network=c?.kind==='network_mode',disabling=draft.operation==='disable';
 const [input,setInput]=useState({scope:c?.scope||'agent',action:c?.rule?.action||'write',
  effect:c?.rule?.effect||'deny',target:c?.rule?.target||'',text:c?.rule?.text||'',network:c?.mode||'model_only',ack:false});
 const scope=c?.scope||input.scope,stale=view?.basis_hash!==draft.basisHash;
 const update=patch=>setInput(old=>{const next={...old,...patch,ack:false};if(next.action==='behavior')next.effect='deny';if(next.action==='network'||next.scope==='system'&&next.effect==='allow')next.effect='deny';return next;});
 return <PolicyLifecycleDialog title={disabling?'停用所属层的约束':network?'配置网络范围':'可视化配置安全约束'} onClose={onClose} busy={busy} confirmLabel="提交候选，前往核对" onConfirm={async()=>{if(stale)throw Error('配置已有更新，请关闭后重新编辑。');await onSubmit(input);}}>
  <div className="session-security-form">
   {c?<p className="session-security-owner">归属：<strong>{scopeNames[scope]}</strong></p>:<label>配置归属<select aria-label="配置归属" value={scope} onChange={e=>update({scope:e.target.value})}><option value="agent">Agent 基线 · 全部会话继承</option><option value="system">系统策略 · 全部受控 Agent</option><option disabled value="workspace">工作区 · 暂不支持独立应用</option><option disabled value="session">当前会话 · 暂不支持独立应用</option></select></label>}
   {disabling?<><p>将停用：<strong>{c.title}</strong></p><code>{c.target}</code>{c.kind==='dsl'&&<p className="inline-notice warning">此操作移除该规则所属的整个 DSL 文档，文档内其他规则也会停用。审批中会展示完整差异。</p>}</>:network?<label>网络范围<select aria-label="网络范围" value={input.network} onChange={e=>update({network:e.target.value})}><option value="model_only">本机控制端、DNS 和模型地址</option><option value="disabled">仅保留本机控制端</option></select></label>:<>
    <div className="session-security-form-pair"><label>操作<select aria-label="约束操作" value={input.action} onChange={e=>update({action:e.target.value})}>{Object.entries(actionNames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>{input.action!=='behavior'&&<label>处置<select aria-label="约束处置" value={input.effect} onChange={e=>update({effect:e.target.value})}>{scope==='agent'&&input.action!=='network'&&<option value="allow">允许</option>}<option value="deny">禁止</option>{input.action==='tool'&&<option value="confirm">确认后允许</option>}</select></label>}</div>
    {input.action!=='behavior'&&<label>{input.action==='network'?'IPv4 地址':input.action==='tool'?'原生工具名称':'文件或目录'}<input aria-label="约束对象" maxLength={1000} value={input.target} onChange={e=>update({target:e.target.value})} placeholder={input.action==='network'?'例如 203.0.113.8':input.action==='tool'?'例如 bash':'已登记资源内的实际路径，例如 /w/0/tests'}/></label>}
    <label>{input.action==='behavior'?'行为约定':'补充说明'}<textarea aria-label="约束说明" rows={3} maxLength={2000} value={input.text} onChange={e=>update({text:e.target.value})}/></label>
    {input.action==='write'&&<label className="session-security-operation-note"><input type="checkbox" checked readOnly/>包含写入、修改和删除；当前后端将它们作为同一操作组。</label>}
    {input.action==='behavior'&&<p className="field-note">行为指导不作内核强制执行声明。</p>}
   </>}
   <p className="session-security-impact">实际影响：<strong>{impact(scope)}</strong>。提交只创建候选；批准后仍须显式应用。</p>
   <label className="session-security-ack"><input type="checkbox" checked={input.ack} onChange={e=>setInput(old=>({...old,ack:e.target.checked}))}/>已核对约束内容与全部影响范围</label>
   {stale&&<p role="alert" className="inline-notice warning">配置或运行代次已变化，请关闭后重新读取。</p>}
  </div>
 </PolicyLifecycleDialog>;
}

export default function SessionSecurityPanel({data,loading,error,post,root,onRefresh,onApprovals,onDetail,onConfigure}){
 const view=data?.security,[scope,setScope]=useState(''),[draft,setDraft]=useState(null),[info,setInfo]=useState(null),[check,setCheck]=useState(false),[busy,setBusy]=useState(false),[submitted,setSubmitted]=useState(null);
 const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 if(error)return null;
 if(loading&&!view)return <p role="status" className="task-empty">正在汇总当前会话的安全约束…</p>;
 if(!view)return <p role="alert" className="inline-notice warning">未取得完整安全视图，请刷新重试；不能将缺少数据解释为没有约束。</p>;
 const controls=visibleControls(view,{scope});
 const edit=(control=null,operation='add')=>{setDraft({control,operation,basisHash:view.basis_hash,requestKey:crypto.randomUUID()});};
 async function submit(input){if(busy)return;const body=changeRequest(view,draft,input,draft.requestKey);setBusy(true);try{const value=await post(root+'/security/proposals',body);if(alive.current){setSubmitted(value);setDraft(null);}}finally{if(alive.current)setBusy(false);}}
 function detail(c){const record=[...(data.records||[]),...(view.evidence_records||[])].find(r=>r.id===c.record_id);if(record){onDetail(record);return;}setInfo(c);}
 return <div className="session-security-panel">
  <div className="session-security-toolbar"><div><strong>当前安全约束</strong><span>{view.controls.length} 项已接入约束</span></div><div className="actions"><button className="button ghost" onClick={()=>{setCheck(true);onRefresh();}}>检查当前配置</button><button className="button primary" disabled={!view.can_propose||!post} onClick={()=>edit()}>添加约束</button></div></div>
  {!view.coverage_complete&&<p role="alert" className="inline-notice warning">安全详情不完整或当前连接仅用于观测，请展开检查结果；未核验内容不计为当前保护。</p>}
  {check&&<section className="session-security-check" aria-label="安全检查结果"><div className="session-security-section-heading"><strong>安全检查结果 · 只读</strong><button className="button tiny ghost" onClick={()=>setCheck(false)}>收起</button></div><dl>{view.checks.map(c=><React.Fragment key={c.name}><dt>{c.name}</dt><dd><span>{c.ok?'已读取／核验':'需要注意'}</span>{c.message}</dd></React.Fragment>)}</dl></section>}
  <div className="session-security-filter"><label>约束归属<select aria-label="筛选约束归属" value={scope} onChange={e=>setScope(e.target.value)}><option value="">全部当前约束</option>{Object.entries(scopeNames).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></label><span>候选和未应用的变更单独处理</span></div>
  <div className="session-security-table-wrap"><table className="session-security-table" aria-label="当前会话全部已接入安全约束"><thead><tr><th>约束与对象</th><th>归属</th><th>执行方式</th><th>当前状态</th><th>操作</th></tr></thead><tbody>{controls.map(c=><tr key={c.id}><td><strong>{c.title}</strong><code>{c.target}</code>{c.effect&&c.kind==='typed'&&<small>{effectNames[c.effect]||c.effect}</small>}</td><td>{scopeNames[c.scope]||c.scope}{c.system_builtin&&<small>系统内置保护</small>}</td><td>{c.method}</td><td><RecordBadge tone={c.status.includes('未核验')||c.status.includes('不完整')?'warn':'neutral'}>{c.status}</RecordBadge></td><td><div className="session-security-row-actions"><button className="button tiny ghost" onClick={()=>detail(c)}>详情</button>{c.can_configure&&<button className="button tiny ghost" onClick={()=>edit(c,'replace')}>配置</button>}{c.can_disable&&<button className="button tiny ghost" onClick={()=>edit(c,'disable')}>{c.kind==='dsl'?'停用文档':'停用'}</button>}{!c.can_configure&&!c.can_disable&&<small>只读</small>}</div></td></tr>)}{!controls.length&&<tr><td colSpan={5}>没有此归属的已接入约束；不代表其他机制没有约束。</td></tr>}</tbody></table></div>
  <div className="session-security-capability"><strong>会话独立配置与停用：暂不支持</strong><p>{view.session_local_reason} 系统和 Agent 规则可以在本面板提交所属层变更，影响范围会明确展示。</p></div>
  {submitted&&<section className="session-security-submitted" aria-label="已提交候选"><strong>候选已提交 · 当前运行配置未改变</strong><span>{impact(submitted.scope)}</span><button className="button primary" onClick={()=>onApprovals(submitted.approval_id)}>查看差异与审批</button></section>}
  {view.pending_changes?.length>0&&<section className="session-security-pending" aria-label="从此会话提交的待处理候选"><strong>从此会话提交的待处理候选</strong>{view.pending_changes.map(p=><div key={p.id}><span>{p.name||'安全配置变更'}<small>{scopeNames[p.scope_type]} · {({pending:'待审批',approved:'已批准 · 待应用',stale:'需重新校验',failed:'应用未完成',blocked:'暂不能应用',applying:'正在应用'})[p.status]||'需要处理'}</small></span><button className="button tiny ghost" onClick={()=>onApprovals(p.id)}>查看审批</button></div>)}</section>}
  <details className="session-security-evidence"><summary>DSL 与执行证据 · {(data.records?.length||0)+(view.evidence_records?.length||0)} 条规则记录</summary><p>完整 DSL、编译映射及实际命中保留在对应规则详情。系统调用匹配与工具 Trace 分别查看，未关联事件不算作本会话命中。</p><div className="actions"><button className="button ghost" onClick={()=>onConfigure('system')}>查看系统配置</button><button className="button ghost" onClick={()=>onConfigure('agent')}>查看 Agent 配置</button></div></details>
  {draft&&<SecurityChangeDialog view={view} draft={draft} busy={busy} onClose={()=>!busy&&setDraft(null)} onSubmit={submit}/>}
  {info&&<PolicyLifecycleDialog title="安全约束详情" confirmLabel="关闭" onClose={()=>setInfo(null)} onConfirm={()=>setInfo(null)}><dl className="session-security-facts">{[['约束',info.title],['保护对象',info.target],['归属',scopeNames[info.scope]],['执行方式',info.method],['当前状态',info.status],['说明',info.description||info.reason]].map(([k,v])=><React.Fragment key={k}><dt>{k}</dt><dd>{v}</dd></React.Fragment>)}</dl>{info.document_id&&<p>此文档的加载映射尚不完整，请前往所属配置核对。</p>}</PolicyLifecycleDialog>}
 </div>;
}
