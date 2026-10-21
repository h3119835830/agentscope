import React,{useEffect,useState,useRef} from 'react';
import PolicyLifecycleDialog from './PolicyLifecycleDialog.jsx';
import {configurationAgentLabel} from './policyConfigurationPresentation.mjs';
import './writePermissions.css';

export default function WritePermissionDialog({agent,agents,api,post,onClose,onApprovals}){
 const [data,setData]=useState(null),[paths,setPaths]=useState(''),[reason,setReason]=useState(''),[error,setError]=useState(''),[ack,setAck]=useState(false),[busy,setBusy]=useState(false);
 const [shortPaths,setShortPaths]=useState(''),[protectedPaths,setProtectedPaths]=useState('');
 const request=useRef(null);
 useEffect(()=>{let alive=true;api('/api/agent-instances/'+encodeURIComponent(agent.id)+'/write-permissions').then(v=>{if(alive)setData(v);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[api,agent.id]);
 async function submit(){
  if(!data||data.instance_id!==agent.id||!ack)return;
  const lines=value=>value.split('\n').map(p=>p.trim()).filter(Boolean);
  const body={paths:lines(paths),short_paths:lines(shortPaths),protected_paths:lines(protectedPaths),reason:reason.trim(),generation:data.generation,base_hash:data.policy_hash};
  const fingerprint=JSON.stringify(body);if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,key:crypto.randomUUID()};
  setBusy(true);setError('');
  try{const result=await post('/api/agent-instances/'+encodeURIComponent(agent.id)+'/write-permissions/proposals',{...body,request_key:request.current.key});onClose();onApprovals(result.approval_id);}
  catch(e){setError(e.message);}finally{setBusy(false);}
 }
 return <PolicyLifecycleDialog title="申请最小目录写权限" confirmLabel="提交人工审批" busy={busy} confirmDisabled={!data||data.instance_id!==agent.id||!paths.trim()||!reason.trim()||!ack||(shortPaths.trim()&&!protectedPaths.trim())} onClose={onClose} onConfirm={submit}>
  <div className="write-permission-form">
  <p>目标：{configurationAgentLabel(agent,agents)} · 此 Agent 的全部会话</p>
  <p>仅填写必要的源码与验收产物目录，不填写工作区根目录或测试目录。已有禁止规则、系统保护及其他权限保持不变。</p>
  {!data&&!error&&<p role="status">正在读取当前执行权限…</p>}
  {error&&<p role="alert" className="spl-error">{error}</p>}
  <label>申请写入目录（每行一个，需已存在）<textarea aria-label="申请写入目录" rows={3} maxLength={16000} disabled={busy} value={paths} onChange={e=>setPaths(e.target.value)}/></label>
  <label>必要性说明<input aria-label="写权限必要性说明" maxLength={1000} disabled={busy} value={reason} onChange={e=>setReason(e.target.value)}/></label>
  <details><summary>路径过长或需要多个独立写入目录</summary>
   <p>可同时申请短路径映射。映射不会开放父目录；写入仍限于上方列出的目录。目录须已存在，不会移动或覆盖场景文件。审批详情会显示原目录与短路径，应用会重建此 Agent 的执行进程。</p>
   <label>需要缩短的项目目录（每行一个）<textarea aria-label="短路径映射目录" rows={2} disabled={busy} value={shortPaths} onChange={e=>setShortPaths(e.target.value)}/></label>
   <label>仍受保护的测试目录（每行一个）<textarea aria-label="受保护测试目录" rows={2} disabled={busy} value={protectedPaths} onChange={e=>setProtectedPaths(e.target.value)}/></label>
   <p>申请映射时，上方每个可写目录也会单独建立短路径。测试不能位于可写目录内；已有 DSL 引用当前路径时，须先经审批停用并应用。</p>
  </details>
  <details><summary>当前权限与表达限制</summary>{data&&<><p>每个已登记资源目前支持 {data.limits.write_ranges_per_resource} 个连续写入范围，精确匹配路径最多 {data.limits.exact_path_bytes} 字节。无法精确表达时拒绝提交，不扩大到共同父目录。</p><ul>{data.effective_policy.rules.filter(r=>r.action==='write').map((r,i)=><li key={i}>{r.effect==='allow'?'允许':'禁止'}修改与删除：{r.target}</li>)}</ul><p>{data.application}</p></>}</details>
  <label className="write-permission-ack"><input type="checkbox" checked={ack} disabled={busy} onChange={e=>setAck(e.target.checked)}/><span>我已核对目录；本次只提交审批，批准后还须单独应用。测试保持受保护。</span></label>
  </div>
 </PolicyLifecycleDialog>;
}
