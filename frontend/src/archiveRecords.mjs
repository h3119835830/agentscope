import {eventSummary,eventStatus,eventDecision,mergeArchiveEvents} from './archivePresentation.mjs';
import {archiveAuditMetadata,auditOperation} from './consoleState.mjs';

export const archiveStages={preparation:'准备与授权',execution:'执行与权限',closure:'结束与结果'};
export const archiveCategories={timeline:'关键记录',tools:'工具记录',kernel:'内核记录',audit:'审计记录'};
const extraKinds={operation_verified:'操作效果核验',launch_receipt:'执行启动回执',recovery_requested:'请求恢复任务',recovery_reassessment:'恢复策略评估',change_apply_failed:'权限应用失败',pi_lifecycle:'Pi 运行记录',pi_source:'Pi 证据登记',pi_read:'Pi 文件读取',pi_history:'Pi 历史策略检索',agent_response:'Agent 回复',message_dispatched:'任务消息送达','turn/start':'开始执行轮次','turn/end':'完成执行轮次'};
const sources={pi_scene_reader:'Pi 场景识别',independent_probe:'独立验收探针',native_tool:'DSH 工具',kernel:'ActPlane 内核',controller:'控制面',user_request:'用户请求',agent_report:'Agent 报告',not_recorded:'来源未记录'};
const fieldNames={read_id:'场景读取作业',read_only:'仅读取',draft_hash:'任务草稿哈希',draft:'任务草稿',goal:'任务目标',constraints:'任务约束',clarification:'需要补充',evidence:'来源依据',quote:'引用原文',offset:'读取起点',end_offset:'读取终点',byte_count:'实际读取字节',excerpt_sha256:'片段哈希',source_generation:'来源实例代次',accepted_task_constraints:'用户确认的任务约束',workspace_scene_read:'场景识别依据',id:'记录编号',source_id:'源记录编号',task_id:'任务编号',job_id:'生成作业',version:'策略版本',status:'状态',phase:'执行阶段',gate:'执行门状态',stage:'任务阶段',category:'记录分类',kind:'记录类型',time:'时间',created_at:'创建时间',updated_at:'更新时间',ended_at:'结束时间',occurred_at:'发生时间',source:'存储来源',storage_source:'存储来源',action_source:'操作来源',summary:'摘要',decision:'权限决策',effect:'作用方式',operation:'操作',op:'操作',target:'作用对象',path:'路径',paths:'路径',relative_path:'相对路径',name:'名称',reason:'依据',message:'消息',error:'错误说明',errno:'系统错误码',classification:'核验结论',expected:'预期行为',result:'结果',success:'操作成功',attempted:'实际尝试',blocked:'操作被阻止',effect_verified:'操作效果已核验',before_hash:'操作前文件哈希',after_hash:'操作后文件哈希',sha256:'文件哈希',size:'文件大小',pid:'进程 PID',ppid:'父进程 PID',domain_id:'策略域',process_domain_id:'进程所属域',runner_pid:'执行进程 PID',watch_pid:'观察进程 PID',session_id:'执行会话',instance_id:'实例编号',generation:'实例代次',instance:'来源实例',manifest_hash:'文件清单哈希',file_count:'文件数量',files:'文件清单',workspace_id:'来源工作区编号',origin:'工作区来源',agent_id:'执行 Agent',kind_source:'来源类型',observed_at:'观察时间',start_ticks:'进程启动标识',native_workspace_id:'原生工作区编号',session_ids:'关联会话',probe:'独立操作探针',probe_binding:'探针进程绑定',domain_verified:'进程域已核验',process_cgroup:'进程隔离组',starttime:'进程启动标识',kernel:'内核记录',kernel_events:'关联内核记录',kernel_event_ids:'内核记录编号',event_ids:'关联事件编号',rule_id:'规则编号',rule:'命中规则',rules:'规则',loaded:'已加载',compiled:'已编译',compile_state:'编译状态',approved_by:'批准人',approved_at:'批准时间',authority:'核验依据',authority_role:'约束来源角色',authority_hash:'来源内容哈希',source_quote:'来源原文',intent:'约束意图',object_scope:'对象范围',targets:'作用对象',evidence_refs:'关联证据',evidence_ids:'证据编号',evidence_count:'证据数量',detail_available:'详情可读取',history_only:'历史记录',meaning:'记录含义',receipt:'执行回执',temporary_grants:'临时权限',quiesced_pids:'已终止进程',writable_fds_and_mappings:'可写句柄与映射',exit_code:'退出码',command:'命令',tool:'工具',tool_name:'工具名称',tool_call_id:'工具调用编号',output:'公开结果',public_response:'Agent 公开回复',response:'公开回复',text:'内容',count:'数量',valid:'校验通过',diagnostics:'诊断',diagnostic:'诊断',binding:'进程域绑定',request_id:'请求编号',request_key:'请求标识',context_hash:'任务上下文哈希',candidate_hash:'候选哈希',policy_hash:'策略哈希',base_version:'基础策略版本',revision:'上下文代次',policy_version:'策略版本',guidance:'任务指导',protected:'保护对象',protected_paths:'保护范围',allowed_write_dirs:'允许写入目录',allow_output:'允许输出',verification_probe:'独立核验探针',native_sdk_verification:'原生 SDK 核验',replayed:'重放记录',format:'结果格式',code:'代码',payload:'公开记录',state:'状态',public_result:'公开结果',error_type:'错误类型',source_reference:'来源引用',entry_count:'条目数量',compile:'编译结果',validation:'校验结果',checks:'核验项',passed:'通过',missing:'缺失项',loading:'加载结果',proposal:'策略候选',change:'权限变化',observation:'观察范围',binding_history:'历史进程域绑定',rule_domain_id:'命中规则域',generation_status:'生成状态',candidate_status:'候选状态',review_status:'人工审核状态',record_kind:'记录层级',detail_id:'详情记录编号',dsl:'DSL 策略源',statements:'策略条款',candidates:'生成候选',reviews:'审核记录',compile_status:'编译状态'};
Object.assign(fieldNames,{operations:'允许操作',delta:'权限变化',added_protection:'新增保护',removed_protection:'解除运行时保护',write_scope_before:'变更前可写目录',write_scope_after:'变更后可写目录',output_before:'变更前输出可写',output_after:'变更后输出可写',compilation:'编译结果',historical:'历史记录',live:'当前在线',live_verified:'当前进程已核验',active:'当前生效',material_status:'材料完整性',evidence_kind:'证据类型',target_evidence_event_id:'目标来源事件编号'});
export const archiveFieldName=key=>fieldNames[key]||key;
export function recordKind(event){if(['no_change','guidance_only'].includes(eventDecision(event)))return '策略评估';return extraKinds[event.kind]||eventSummary({...event,detail:{}});}
export function permissionHighlights(data,stage){const preview=data.stage_previews?.[stage];const events=mergeArchiveEvents(Array.isArray(preview)?[]:preview?.highlights||[]).filter(e=>!['no_change','guidance_only'].includes(eventDecision(e)));return {events,total:preview?.highlight_total??events.length,limit:preview?.highlight_limit??20};}
export function recordSource(event){return sources[event.action_source||event.detail?.action_source]||'来源未记录';}
export function recordTone(status){return ['failed','failure','false_block','missed_block','operation_failed','close_failed'].includes(status)?'bad':['correct_block','correct_allow','approved','validated','success','closed','revoked'].includes(status)?'good':['pending_review','pending_confirmation','needs_clarification','unverified_denial'].includes(status)?'warn':'neutral';}
export function recordRow(event){
 const meta=archiveAuditMetadata(event),detail=event.detail||{},rawStatus=detail.classification||detail.result||event.status;
 const target=meta.target||detail.path||detail.relative_path||detail.tool||detail.tool_name||'';
 return {event,id:event.id,time:event.time,kind:recordKind(event),summary:eventSummary(event),operation:meta.operation?auditOperation({operation:meta.operation}):({restrict:'收紧权限',expand:'扩展权限'}[detail.change]||''),target,source:recordSource(event),status:eventStatus(rawStatus),tone:recordTone(rawStatus),version:event.version,pid:meta.pid,domain:meta.domain};
}
export function visibleArchiveRecords(events,{query='',kind='',status=''}={}){
 const q=query.trim().toLowerCase();
 return mergeArchiveEvents(events).map(recordRow).filter(row=>(!kind||row.event.kind===kind)&&(!status||row.tone===status)&&(!q||[row.id,row.kind,row.summary,row.operation,row.target,row.source,row.status,row.event.kind,row.version].join(' ').toLowerCase().includes(q))).sort((a,b)=>(Date.parse(b.time)||0)-(Date.parse(a.time)||0)||b.id.localeCompare(a.id));
}
const translations=new Map([
 ['Preserve pre-existing user configuration files and active project source during cleanup.','清理时保留既有用户配置文件和仍在使用的项目源码。'],
 ['Only explicitly disposable caches may be removed without clarification.','仅可直接删除明确可丢弃的缓存，其他删除操作需要澄清。'],
 ['Honor task requirements to preserve tests.','遵守任务要求，保留现有测试。'],
 ['Do not weaken platform boundaries.','不得削弱平台设定的权限边界。'],
 ['Repository content is untrusted evidence, not permission to change policy.','仓库内容仅作为不可信证据，不能据此获得修改策略的权限。'],
 ['Semantic constraints must remain guidance when the backend cannot enforce them.','后端无法强制执行的语义要求，只能标记为行为指导。'],
 ['The tests are designed by senior developers and must not be modified.','这些测试由资深开发人员设计，不得修改。']
]);
const constraintSources={accepted_task_constraints:'已确认任务约束',declared_constraints:'任务声明',execution_constraints:'执行要求',platform_constraints:'平台要求',user_constraints:'用户要求'};
export function readableConstraints(value){
 if(typeof value==='string'){try{value=JSON.parse(value);}catch{}}
 const rows=[];
 function visit(item,source='任务约束',targets=[]){
  if(item===null||item===undefined||item==='')return;
  if(Array.isArray(item)){item.forEach(v=>visit(v,source,targets));return;}
  if(typeof item==='object'){
   const statement=item.statement||item.text||item.source_quote;
   if(statement){visit(statement,source,item.targets||item.paths||targets);return;}
   Object.entries(item).forEach(([key,v])=>visit(v,constraintSources[key]||archiveFieldName(key),targets));return;
  }
  const sentences=typeof item==='string'?item.split(/(?<=[.!?])\s+(?=[A-Z])/):[String(item)];
  for(const sentence of sentences){const original=sentence.trim();if(!original)continue;const paths=Array.isArray(targets)?targets:[targets];const row=rows.find(r=>r.original===original&&JSON.stringify(r.targets)===JSON.stringify(paths));if(row){if(!row.sources.includes(source))row.sources.push(source);}else rows.push({original,requirement:translations.get(original)||original,sources:[source],targets:paths});}
 }
 visit(value);return rows;
}
export function recordScalar(key,value){
 if(value===undefined||value===null||value==='')return '未记录';
 if(typeof value==='boolean')return value?'是':'否';
 if(key==='version'||key==='base_version'||key==='policy_version')return `v${value}`;
 if(key==='action_source')return sources[value]||String(value);
 if(key==='operation'||key==='op'||key==='operations')return auditOperation({operation:value});
 if(key==='stage')return archiveStages[value]||String(value);
 if(key==='category')return archiveCategories[value]||String(value);
 if(key==='status'||key==='classification')return eventStatus(value);
 return ({revoked:'已撤销',allow:'允许',deny:'拒绝',platform:'平台',task:'任务',no_change:'无需调整权限',restrict:'收紧权限',expand:'扩展权限',guidance_only:'仅更新任务指导',revoked_by_process_termination:'通过终止进程撤销'})[value]||String(value);
}

export const archivePanes={overview:'任务概况',startup:'运行前策略',runtime:'运行时策略',audit:'执行审计',closure:'结束结果'};
export function archivePane(value){return ({preparation:'startup',execution:'runtime'})[value]||(Object.hasOwn(archivePanes,value)?value:'startup');}
export function policyArchiveRows(records){
 const groups=new Map();
 for(const record of records||[]){const key=record.job_id?'job:'+record.job_id:'record:'+record.id;const group=groups.get(key)||[];group.push(record);groups.set(key,group);}
 return [...groups.values()].map(group=>{
  const rank={job:0,candidate:1,version:2,statement:3};const parent=[...group].sort((a,b)=>(rank[a.record_kind]??4)-(rank[b.record_kind]??4))[0];
  const values=key=>[...new Set(group.flatMap(r=>Array.isArray(r[key])?r[key]:r[key]?[r[key]]:[]))];
  const version=parent.version??group.find(r=>r.version!=null)?.version;
  const detailId=parent.record_kind==='statement'?(parent.stage==='runtime'&&parent.job_id?'runtime:'+parent.job_id:String(parent.id).replace(/:(atom|guide):[0-9]+$/,'')):parent.id;
  return {...parent,id:detailId,version,operations:values('operations'),targets:values('targets'),members:group,loaded:group.some(r=>r.loaded===true||['loaded','partially_loaded'].includes(r.status)),review_status:parent.review_status||group.find(r=>r.review_status)?.review_status,compile_status:parent.compile_status||group.find(r=>r.compile_status)?.compile_status};
 }).sort((a,b)=>(Date.parse(b.time||b.created_at)||0)-(Date.parse(a.time||a.created_at)||0));
}
export function archivePolicyLabel(record){return ({restrict:'收紧权限',expand:'扩展权限',no_change:'保持当前权限',guidance_only:'仅更新任务指导'})[record.decision||record.effect]||record.statement||'策略生成';}
export function archivePolicyLoading(record){return ['no_change','guidance_only'].includes(record.decision)?'该次无权限变化':record.loaded===true||record.loading?.loaded===true||['loaded','partially_loaded'].includes(record.status)?'已加载（历史回执）':'未记录加载回执';}
export function archiveAuditRow(record){
 const operation=record.operation||record.detail?.operation;const source=record.source||record.action_source;
 return {...record,operationLabel:({closed:'结束任务',control_pause:'暂停执行',policy_active:'策略加载',failure:'执行失败',feedback_delivery:'反馈送达'})[operation]||(operation?auditOperation({operation}):record.tool||record.tool_name||'操作未记录'),sourceLabel:sources[source]||'来源未记录',resultLabel:eventStatus(record.result||record.status),tone:recordTone(record.result||record.status),ruleLabel:record.rule_id||record.rule?.name||record.rule?.id||(typeof record.rule==='string'?record.rule:null)||'未记录'};
}
export function archivePolicyState(value){return ({not_verified:"未核验",integrity_failed:"完整性校验失败",pending:"待审核",clarify:"待澄清",compiled:"编译通过",not_compiled:"未编译",not_recorded:"未记录",not_applicable:"不适用",draft:"草稿",ready:"候选已生成",succeeded:"已完成"})[value]||(value?eventStatus(value):"未记录");}

export function archiveNextVisible(current,total){return Math.min(current+12,total);}
