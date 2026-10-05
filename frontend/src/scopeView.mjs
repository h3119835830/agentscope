// Presentation only: confirmed snapshots and control-plane state remain authoritative.
export const kinds = {task_grant:'开放任务目录', restrict:'收紧修改范围', expand:'开放报告目录', guidance:'补充任务要求'};
export const stages = [
  {key:'cold',title:'默认只读',note:'仓库不可写'},
  {key:'grant',title:'任务授权',note:'开放修改目录'},
  {key:'restrict',title:'执行收紧',note:'保留 backend'},
  {key:'expand',title:'报告扩权',note:'开放 output'},
  {key:'close',title:'结束撤销',note:'清理临时权限'},
];
export const resources = [
  ['backend','统计逻辑'],['frontend','摘要展示'],['tests','测试文件'],
  ['config','项目配置'],['output','任务报告'],['runtime / tmp','运行与临时文件'],
];
export const statusNames = {queued:'等待分析',running:'分析中',completed:'分析完成',failed:'失败',interrupted:'已中断',
  pending:'待审核',expired:'已过期',approved:'已批准',rejected:'已拒绝',compiled:'已编译',not_checked:'未编译',
  not_applied:'未应用',applying:'应用中',loaded:'已加载',loaded_unverified:'核验失败',confirmed:'已核验',
  unverified:'未核验',not_required:'无需变更'};

export function writable(scope, resource) {
  return resource === 'runtime / tmp' || (resource === 'output' ? !!scope?.allow_output : (scope?.allowed_write_dirs || []).includes(resource));
}
export function scopeDiff(base, next) {
  if (!next) return [];
  return resources.slice(0,5).filter(([r])=>writable(base,r)!==writable(next,r)).map(([resource,label])=>({
    resource,label,before:writable(base,resource)?'可读写':'只读',after:writable(next,resource)?'可读写':'只读',
  }));
}
export function snapshotTitle(snapshot, previous) {
  if (snapshot.revision === 0) return '默认仓库只读';
  const diff=scopeDiff(previous?.payload,snapshot.payload);
  if(diff.some(d=>d.resource==='output'&&d.after==='可读写')) return '开放 output 报告目录';
  if(diff.some(d=>d.after==='只读')) return '收紧文件修改范围';
  return '开放任务修改目录';
}
export function stageEvidence(data) {
  const history=[...(data?.snapshots || [])].sort((a,b)=>a.revision-b.revision);
  const found={};
  history.forEach((s,i)=>{
    if(s.revision===0) found.cold=s;
    const diff=scopeDiff(history[i-1]?.payload,s.payload);
    if(s.revision>0&&diff.some(d=>d.resource!=='output'&&d.after==='可读写')) found.grant ||= s;
    if(diff.some(d=>d.resource==='frontend'&&d.after==='只读')) found.restrict ||= s;
    if(diff.some(d=>d.resource==='output'&&d.after==='可读写')) found.expand ||= s;
  });
  if(data?.session.phase==='ended') found.close={closed:true};
  return stages.map(s=>({...s,evidence:found[s.key]}));
}
export function candidateState(delta, data) {
  const job=data.jobs.find(j=>j.delta_id===delta.id);
  const stale=delta.base_snapshot_id!==data.session.active_snapshot_id ||
    delta.message_revision!==data.session.message_revision || delta.process_epoch!==data.session.process_epoch;
  const blockedExpansion=data.session.phase==='waiting_constraint'&&['task_grant','expand'].includes(delta.proposal?.proposal?.decision);
  const ready=data.session.phase!=='ended'&&!data.session.apply_id&&!blockedExpansion&&delta.review_status==='pending'&&!!delta.proposal_hash&&job?.status==='completed'&&!stale;
  const label=delta.review_status==='pending'?(stale?'需要重新分析':job?.status==='failed'?'分析失败':blockedExpansion?'先落实收紧要求':ready?'待审核':statusNames[job?.status]||'等待分析'):
    delta.verify_status==='confirmed'?'已核验生效':delta.apply_status==='loaded_unverified'?'核验失败':statusNames[delta.review_status]||'状态待回查';
  return {job,stale,ready,label};
}
export function executionState(data, disconnected=false) {
  if(disconnected) return {label:'连接中断',tone:'warn',hint:'重新连接后回查权限状态。'};
  if(data.session.phase==='ended') return {label:'已结束',tone:'neutral',hint:'临时权限已撤销。'};
  if(data.session.gate==='failed') return {label:'执行已暂停',tone:'warn',hint:'权限应用未完成，请查看失败记录。'};
  if(data.session.phase==='waiting_constraint'||data.session.gate==='waiting_constraint')
    return {label:'等待收紧生效',tone:'warn',hint:'Agent 在工具边界等待；拒绝候选仍保留收紧要求。'};
  if(data.session.apply_id) return {label:'正在应用权限',tone:'warn',hint:'应用与核验完成后更新当前权限。'};
  if(data.session.phase==='cold') return {label:'等待任务授权',tone:'neutral',hint:data.current?'冷启动已核验，可提出任务授权。':'先验证默认只读权限。'};
  if(!data.effective) return {label:'执行域待确认',tone:'warn',hint:'当前仅能查看最近核验的权限记录。'};
  return {label:'执行中',tone:'good',hint:'Agent 正在当前权限内执行。'};
}
const recordNames={user_message:'用户更新任务要求',agent_request:'Agent 申请权限',boundary_pause:'落实收紧前暂停执行',
  checkpoint:'保存任务进展',agent_report:'Agent 提交公开报告',candidate:'生成权限候选',review:'审核权限候选',
  analysis_failure:'权限分析失败',apply_failure:'权限应用失败',proposal_diagnostic:'候选需要重新分析',
  asset_manifest:'固定任务项目',boundary_context_delivery:'更新任务上下文',ended:'结束任务并撤销授权'};
export function recordsFor(data, category='scope') {
  const history=[...data.snapshots].sort((a,b)=>a.revision-b.revision);
  let rows=category==='scope'?history.map((s,i)=>({
    id:'snapshot-'+s.id,time:s.confirmed_at,title:snapshotTitle(s,history[i-1]),result:'v'+s.revision+' 已核验',tone:'good',value:s,snapshot:s,
  })):[];
  const sources=category==='scope'?['ended','review','boundary_pause','agent_request','analysis_failure','apply_failure','proposal_diagnostic']:
    category==='agent'?['tool_result','agent_report','checkpoint','boundary_context_delivery']:['kernel'];
  for(const e of data.events.filter(e=>sources.includes(e.source)&&(category!=='kernel'||e.payload.event?.blocked===true))) {
    let title=recordNames[e.source]||'操作记录',result='已记录',tone='neutral';
    if(e.source==='tool_result'){title='Agent 工具操作';result=e.payload.succeeded===true?'成功':e.payload.succeeded===false?'失败':'结果待回查';tone=e.payload.succeeded===true?'good':'warn';}
    if(e.source==='kernel'){
      const event=e.payload.event;
      const probe=history.some(s=>s.verification?.probe?.probe_pid && s.verification.domain_id===event.domain_id &&
        [event.pid,event.ppid].includes(s.verification?.probe?.probe_pid));
      title=probe?'拦截核验探针':'拦截执行操作';result='已拒绝';tone='warn';
    }
    if(e.source==='ended'){result='授权已撤销';tone='good';}
    if(e.source==='review'){result=['approve','approved'].includes(e.payload.decision)?'已批准':['reject','rejected'].includes(e.payload.decision)?'已拒绝':'已审核';}
    if(['analysis_failure','apply_failure'].includes(e.source)){result='失败';tone='warn';}
    if(e.source==='agent_report') result='Agent 自报';
    if(e.source==='boundary_pause') {result='等待收紧';tone='warn';}
    rows.push({id:'event-'+e.id,time:e.occurred_at,title,result,tone,value:e});
  }
  return rows.sort((a,b)=>new Date(b.time)-new Date(a.time));
}
export function proposalSummary(delta) {
  const decision=delta.proposal?.proposal?.decision;
  if(!decision)return '分析尚未完成。';
  if(['guidance_only','no_change'].includes(decision))return '补充任务指导或无需变更，文件权限保持不变。';
  return ({task_grant:'为修复统计逻辑和完善摘要，申请开放任务修改目录。',
    restrict:'按本次用户要求收紧修改范围；核验前 Agent 会等待。',
    expand:'申请写入任务报告。扩权会重启 Agent，并恢复已保存的公开任务进展。',
    guidance:'依据本次任务要求生成候选；具体允许范围以下列差异为准。'})[delta.kind];
}
