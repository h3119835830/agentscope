import {agentName,visibleAgentInstances} from './agentInstancePresentation.mjs';
import {operationLabel} from './policyRecordPresentation.mjs';
export function configurationAgentLabel(agent,agents=[]){
 const label=agentName(agent);
 const peers=visibleAgentInstances(agents).filter(a=>a.mode==='controlled'&&agentName(a)===label);
 return peers.length>1?label+' · '+String(agent.id).slice(-6):label;
}

const values=value=>(Array.isArray(value)?value:String(value??'').split('\n')).map(String).map(v=>v.trim()).filter(Boolean);
const unique=items=>[...new Set(items)];
const statusLabels={draft:'草案',pending:'待审批',approved:'已批准待应用',applying:'正在应用',stale:'需重新校验',invalid:'校验未通过',rejected:'已拒绝',failed:'应用失败',blocked:'暂不可应用'};

export function configurationRecordActions(row){
 const inFlight=['pending','approved','applying'].includes(row.status)&&row.approval_current!==false;
 const applied=!!(row.applied_revision||row.applied||row.has_applied_document);
 const unsupported=row.scope==='workspace'||!row.can_submit;
 const submitReason=row.read_only?'历史模板只读，请使用新版模板新增配置':unsupported?(row.execution_support?.applicable===false?'ActPlane 暂不支持此语义，仅保存参数草案':'此配置暂不可提交'):inFlight?'已有变更正在审批或等待应用，请查看审批':row.applied&&!row.has_changes?'当前版本已应用': '';
 const disableReason=(row.scope==='workspace'||(unsupported&&!row.read_only))?'此配置暂不可停用':inFlight?'已有变更正在审批或等待应用，请查看审批':!applied?'尚未应用，无需停用':'';
 const deleteReason=applied?'请先审批并应用停用，再删除子配置':inFlight?'请先在审批中结束待处理变更':row.scope==='workspace'?'历史工作区配置只读':row.archived?'此配置已删除':'';
 return {canSubmit:!submitReason,submitReason,canDisable:!disableReason,disableReason,hasApplied:applied,canDelete:!deleteReason,deleteReason,canView:!!row.approval_id,
  viewTitle:row.approval_id?(row.approval_revision&&row.approval_revision!==row.revision?'查看配置 v'+row.approval_revision+' 的审批（当前草案 v'+row.revision+'）':'查看此配置的审批与应用回执'):'尚无审批记录'};
}

export function configurationDisableSnapshot(row){
 return row.applied_configuration?{...row,...row.applied_configuration}:row;
}

// Summarize the saved child, never the editable defaults of its parent template.
export function configurationRecordSummary(row,template={}){
 const definition=row.template_definition||template,parameters=row.parameters||{},config=row.config||{};
 const fields=(definition.parameters||[]).filter(p=>!['operations','effect'].includes(p.type)&&!['operations','effect'].includes(p.key));
 const targets=fields.flatMap(p=>{
  const value=parameters[p.key]??(p.key==='values'?config.values:undefined);
  return values(value).map(v=>fields.length>1?p.label+'：'+v:v);
 });
 if(!targets.length&&config.values)targets.push(...values(config.values));
 const fixed=!definition.custom&&!row.legacy&&definition.parameters?.length===0;
 const target=targets[0]|| (fixed?'模板固定条件':'查看详情');
 const targetLabel=target+(targets.length>1?' 等 '+targets.length+' 项':'');
 const operations=unique(values(row.effective_operations??row.requested_operations??config.ops??parameters.operations??(definition.custom?'':definition.operation)).flatMap(v=>v.split(',')).map(v=>v.trim()).filter(Boolean));
 const savedEffect=row.effect??parameters.effect??config.effect;
 const recordEffects=(row.records||[]).flatMap(r=>r.effects||[r.effect]).filter(Boolean);
 const fixedEffect=!definition.custom&&!row.legacy&&!(definition.parameters||[]).some(p=>p.type==='effect'||p.key==='effect');
 const effects=unique(savedEffect?[savedEffect]:recordEffects.length?recordEffects:fixedEffect&&definition.effect?[definition.effect]:[]);
 const oldApplied=!!row.applied_revision&&row.applied_revision!==row.revision;
 // Legacy library rows do not carry a proposal status. Applied DSL is separate
 // from a saved revision, and neither is proof of kernel enforcement.
 const applied=!!row.applied&&!row.has_changes&&!oldApplied;
 const changed=row.has_changes||oldApplied;
 const status=row.configuration_status?.label||'状态待核验';
 const state=row.configuration_status?.state;
 const stateTone=state==='applied'?'applied':['invalid','failed','blocked'].includes(state)?'error':['pending','approved','applying','stale'].includes(state)?'pending':'saved';
 const note=oldApplied?'旧版仍应用':applied&&row.status==='pending'?'另有待审批变更':'';
 return {target:targetLabel,targetTitle:targets.join('\n')||target,operation:operations.map(operationLabel).join('、')||'操作见详情',effects,status,stateTone,note};
}
