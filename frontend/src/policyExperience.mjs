import {operationLabel} from './policyRecordPresentation.mjs';
import {appendHandoff} from './agentPolicyHandoff.mjs';
export const approvalLabel=s=>({pending:'待审批',approved:'已批准 · 待应用',blocked:'暂不能应用',stale:'需重新校验',invalid:'校验未通过',failed:'应用未完成',applying:'应用中',applied:'已应用',rejected:'已拒绝'})[s]||'状态待核验';
export const disposition=e=>({block:'阻止',notify:'记录并提醒',kill:'终止违规进程'})[e]||e;
export function candidateView(result){
 const clauses=(result.artifact?.policy_ir?.rules||[]).flatMap(r=>r.clauses||[]),targets=[...new Set(clauses.map(c=>c.pattern).filter(Boolean))],operations=[...new Set(clauses.map(c=>operationLabel(c.operation)))],effects=[...new Set(clauses.map(c=>disposition(c.effect)))];
 const first=targets[0]?.split('/').filter(Boolean).at(-1),text=result.record?.statement?.text_zh||result.record?.statement?.text_original||'策略候选';
 const stale=!!result.artifact?.actplane_dsl&&!!result.submission_blockers?.length;
 return {text,targets,operations,effects,title:first?first+' · '+operations.join('、'):'待完善的策略',ready:!!result.artifact?.actplane_dsl&&!stale&&(!result.compile_state||result.compile_state==='compiled'),stale,clauses};
}
const sorted=v=>Array.isArray(v)?v.map(sorted):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])])):v;
export const sameDocuments=(a,b)=>JSON.stringify(sorted([...a].sort((x,y)=>x.id.localeCompare(y.id))))===JSON.stringify(sorted([...b].sort((x,y)=>x.id.localeCompare(y.id))));
export async function submitCandidate(candidate,api,post){
 if(!candidate?.targetId||candidate.targetId==='system')throw Error('请选择对应的 Agent');
 if(['workspace','session'].includes(candidate.scopeType)){
  if(candidate.target?.instance_id!==candidate.targetId||candidate.target?.scope!==candidate.scopeType)throw Error('候选与当前策略范围不一致，请重新生成。');
  const artifact=candidate.document?.generation_binding?.artifact_id;
  if(!artifact||!candidate.candidate_hash)throw Error('候选目标尚未核验，请重新生成。');
  return post('/api/agent-instances/'+encodeURIComponent(candidate.targetId)+'/policy-candidates/'+encodeURIComponent(artifact)+'/proposals',{candidate_hash:candidate.candidate_hash,request_key:candidate.id});
 }
 if(candidate.scopeType!=='agent')throw Error('未知策略范围，请重新选择。');
 const base='/api/agent-instances/'+encodeURIComponent(candidate.targetId)+'/dsl',current=await api(base),documents=appendHandoff(current,candidate,candidate.targetId);
 const existing=(current.proposals||[]).find(p=>p.state==='pending'&&p.base_hash===current.document_hash&&p.base_revision===current.revision&&sameDocuments(p.documents,documents));
  if(existing){const checked=await api('/api/console/approvals/'+encodeURIComponent(existing.id));if(checked.can_approve||checked.can_apply)return existing;}
 return post(base+'/proposals',{documents,base_hash:current.document_hash,base_revision:current.revision,request_key:crypto.randomUUID()});
}

export function generatedScope(result){
 const ctx=result.record?.resolved_context||{},target=ctx.policy_target;
 if(!target)return '旧候选范围待重新确认';
 if(target.scope==='workspace')return target.workspace_id?'工作区：'+(ctx.environment_binding?.values?.workspace?.name||ctx.environment_binding?.values?.workspace?.host||'身份待核验'):'工作区身份待核验';
 if(target.scope==='session')return (ctx.session_name||'当前会话')+'及其子进程';
 return target.scope==='system'?'全部受控 Agent':'全部工作区与会话';
}
