import {operationLabel,effectLabel} from './policyRecordPresentation.mjs';

export const policyRecordFields=['策略名称','作用范围','匹配对象','限制操作','触发条件','处置','状态'];
const list=value=>(Array.isArray(value)?value:String(value??'').split(/[\n,]/)).map(String).map(s=>s.trim()).filter(Boolean);
const statusLabels={draft:'待提交审批',pending:'待审批',approved:'已批准 · 待应用',applied:'已应用',rejected:'已拒绝',stale:'需重新校验',invalid:'校验未通过',failed:'应用失败',applying:'正在应用',unavailable:'审批状态暂不可用'};
export function policyRecord(row,definition={}){
 if(row.unavailable)return {id:row.id,revision:row.revision,name:'配置快照暂不可用',scope:'范围待核验',target:'对象待核验',operation:'操作待核验',conditions:'条件待核验',effect:'处置待核验',status:'配置快照暂不可用',fields:[],template:{},parameters:{},execution:{}};
 const template=row.template||row.template_definition||definition,parameters=row.parameters||{},execution=row.execution||row;
 const fields=(template.parameters||[]).filter(p=>Object.hasOwn(parameters,p.key)&&!['operations','effect'].includes(p.type)&&!['operations','effect'].includes(p.key));
 const subjects=fields.filter(p=>['target','values','endpoint','program'].includes(p.key));
 const targets=subjects.length?subjects:fields.filter(p=>!['exception','producer','checker'].includes(p.key));
 const conditions=fields.filter(p=>!targets.includes(p));
 const describe=items=>items.map(p=>p.label+'：'+list(parameters[p.key]).join('、')).join('；');
 const conditionText=template.id==='RQ1-GENERATED'&&parameters.producer?
  '执行链未经过 '+parameters.producer+' 时触发（仅按程序名匹配）':describe(conditions);
 const operations=list(execution.effective_operations??execution.requested_operations??parameters.operations??template.operation);
 const effect=execution.effect??parameters.effect??template.effect;
 const status=row.execution_support?.applicable===false?'暂不支持 · 仅参数草案':row.configuration_status?.label||statusLabels[row.approval_status??row.status]||'状态待核验';
 return {id:row.id,revision:row.revision,name:row.name||'配置快照暂不可用',
  scope:typeof row.scope==='object'?row.scope.label:row.scope_label|| (row.scope==='system'?'全部受控 Agent':'此 Agent 的全部工作区与会话'),
  target:describe(targets)||'模板固定条件',operation:operations.map(operationLabel).join('、')||'操作未记录',
  conditions:[conditionText,template.fixed_fields?Object.values(template.fixed_fields).join(' '):''].filter(Boolean).join('；')||'无附加条件',
  effect:effect?effectLabel(effect):'处置未记录',
  status:row.approval_operation==='disable'?(row.approval_status==='applied'||row.status==='applied'?'已停用':'停用 · '+status):status,
  fields,template,parameters,execution:Object.fromEntries(['requested_operations','effective_operations','effect','reason','coverage_warning'].filter(key=>Object.hasOwn(execution,key)).map(key=>[key,execution[key]]))};
}

// One authority object is one record; never fan out shared approval IDs.
export function approvalPolicyRows(approvals){
 return approvals.map(approval=>{const record=approval.configuration_records?.length===1?approval.configuration_records[0]:null;return record?{
  ...approval,record_key:approval.id,
  name:record.name||'配置快照暂不可用',policy_record:policyRecord({...record,scope:{...record.scope,label:[approval.target_name,approval.scope_label].filter(Boolean).join(' · ')||record.scope?.label},
   approval_status:approval.status,configuration_status:approval.configuration_status}),configuration_id:record.id,
  batch_size:1
 }:{...approval,record_key:approval.id,batch_size:1,policy_record:legacyApprovalRecord(approval)};});
}

function legacyApprovalRecord(row){
 const clauses=(row.records||[]).flatMap(record=>record.clauses||[]),unique=items=>[...new Set(items.filter(Boolean))];
 const changes=(row.change_items||[]).map(c=>c.label+'：'+c.before+' → '+c.after),removed=(row.document_changes?.removed||[]).map(name=>'停用：'+name);
 return {name:row.name,scope:row.scope_label,target:[...changes,...removed,...unique(clauses.map(c=>c.target))].join('；')||'已保存的策略变更',
  operation:unique(clauses.map(c=>operationLabel(c.operation))).join('、')||'策略配置变更',
  conditions:clauses.length?'按保存的编译条件':'以当前配置核验为准',effect:unique(clauses.map(c=>effectLabel(c.effect))).join('、')||'按已保存配置',
  status:row.configuration_status?.label||statusLabels[row.status]||'状态待核验'};
}
