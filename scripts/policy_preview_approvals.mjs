// Read-only historical replay. Never create an approval from an assistant label.
export function verifyApprovalReplay(generations,configurations,approvals,details){
 let verified=0;
 for(const g of generations)for(const snapshot of g.configuration_snapshots||[]){
  if(snapshot.approval_status!=='applied')continue;
  const configuration=configurations.find(c=>c.id===snapshot.id&&c.revision===snapshot.revision);
  const approval=approvals.records.find(a=>a.id===configuration?.approval_id);
  const detail=details[approval?.id];
  if(!configuration?.approval_current||configuration.approval_revision!==snapshot.revision||!approval||approval.scope_id!==snapshot.scope.id||approval.status!=='applied'||detail?.status!=='applied'||detail.scope_id!==snapshot.scope.id)throw Error('已应用配置缺少对应范围、版本的真实审批回执，不能启动不完整预览');
  if(snapshot.approval_operation!=='disable'&&!detail.documents?.some(d=>d.id===snapshot.id))throw Error('审批回执未包含此精确配置，不能按同名记录补齐');
  verified++;
 }
 return verified;
}
function readOnly(record){
 return {...record,read_only:true,replay:true,can_approve:false,can_apply:false,can_reject:false,can_clear:false,can_restore:false,revalidation:null};
}
export function approvalResponse(url,scopeId,page,clearedPage,details){
 const base='/api/console/approvals';
 if(url.pathname===base){
  const source=url.searchParams.get('cleared')==='true'?clearedPage:page;
  const records=source.records.filter(r=>r.scope_id===scopeId).map(readOnly);
  return {status:200,body:{...source,records,read_only:true,replay:true,cleared_count:clearedPage.records.filter(r=>r.scope_id===scopeId).length}};
 }
 if(url.pathname.startsWith(base+'/')){
  let id;try{id=decodeURIComponent(url.pathname.slice(base.length+1));}catch{return {status:400,body:{detail:'审批记录地址无效。'}};}
  const detail=details[id];
  return detail&&detail.scope_id===scopeId?{status:200,body:readOnly(detail)}:{status:404,body:{detail:'此隔离快照未包含该目标的审批记录。'}};
 }
 return null;
}
