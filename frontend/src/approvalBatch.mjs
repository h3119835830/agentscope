// Bulk actions reuse the exact single-record contracts, without merging authority.
export const approvalNeedsAttention=status=>['invalid','failed','stale','blocked'].includes(status);
export const batchActionFor=tab=>({pending:'approve',approved:'apply',attention:'revalidate'})[tab];
export const batchActionLabel=action=>({approve:'批量批准',apply:'批量应用',revalidate:'批量重新校验',clear:'清理记录',restore:'恢复记录'})[action];
const endpoint=id=>'/api/console/approvals/'+encodeURIComponent(id);
const canonical=value=>JSON.stringify(sort(value));
const sort=value=>Array.isArray(value)?value.map(sort):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,sort(value[k])])):value;
const binding=data=>canonical(Object.fromEntries(['id','kind','scope_id','scope_type','target','candidate_hash','baseline','approval_hash','clearance_hash'].map(k=>[k,data[k]??null])));
const eligible=(data,action)=>action==='clear'?data.can_clear&&!data.cleared:action==='restore'?data.can_restore&&data.cleared:action==='approve'?data.status==='pending'&&data.can_approve:action==='apply'?data.status==='approved'&&data.can_apply&&data.approval_hash:approvalNeedsAttention(data.status)&&data.revalidation?.available;
function validate(data,row,action){
 if(data.id!==row.id||data.scope_id!==row.scope_id||data.scope_type!==row.scope_type)throw Error('记录的作用范围已变化，请刷新后重新选择。');
 if(!eligible(data,action))throw Error(action==='clear'?'待审批、待应用或正在应用的记录不能直接清理；请先处理相应变更。':action==='restore'?'记录的清理状态已变化，请刷新后重试。':action==='revalidate'?(data.revalidation?.reason||'此记录需返回所属配置处理，不能批量重新校验。'):'记录状态已变化，当前不能执行此操作。');
}
export async function prepareApprovalBatch(rows,action,api){
 if(!['approve','apply','revalidate','clear','restore'].includes(action))throw Error('未知批量操作');
 const unique=[...new Map(rows.map(row=>[row.id,row])).values()],entries=new Array(unique.length);let cursor=0;
 async function read(){
  while(cursor<unique.length){const index=cursor++,row=unique[index];let data=row;try{
   data=await api(endpoint(row.id));validate(data,row,action);
   const plan=action==='revalidate'?await api(endpoint(row.id)+'/revalidation'):null;
   if(plan&&plan.source_id!==row.id)throw Error('重新校验预览与原记录不一致。');
   entries[index]={id:row.id,data,plan,binding:binding(data),requestKey:crypto.randomUUID()};
  }catch(error){entries[index]={id:row.id,data,error:error.message};}}
 }
 await Promise.all(Array.from({length:Math.min(4,unique.length)},read));
 if(action==='approve'){
  const conflicts=new Set();
  for(const [i,a] of entries.entries())for(const b of entries.slice(i+1)){
   if(a.error||b.error||a.data.scope_type!==b.data.scope_type||a.data.scope_id!==b.data.scope_id)continue;
   const first=a.data.approval_unit?.configuration_id,second=b.data.approval_unit?.configuration_id;
   if(!first||!second||first===second){conflicts.add(a.id);conflicts.add(b.id);}
  }
  for(const entry of entries)if(conflicts.has(entry.id))entry.error='同一范围存在重叠策略变更，请保留一项后处理。';
 }
 return {action,entries};
}
export async function executeApprovalBatch(batch,api,post,onProgress=()=>{}){
 const results=[];
 for(const entry of batch.entries){
  if(entry.error){results.push({...entry,outcome:'skipped',message:entry.error});onProgress([...results]);continue;}
  try{
   const fresh=await api(endpoint(entry.id));validate(fresh,entry.data,batch.action);
   if(binding(fresh)!==entry.binding)throw Error('候选、范围、基线或批准回执已变化，请重新打开批量预览。');
   const body=['clear','restore'].includes(batch.action)?{expected_hash:entry.data.clearance_hash,request_key:entry.requestKey}:batch.action==='revalidate'?{plan_hash:entry.plan.plan_hash,request_key:entry.requestKey}:{proposal_hash:entry.data.candidate_hash||entry.data.proposal_hash,request_key:entry.requestKey,...(batch.action==='apply'?{approval_hash:entry.data.approval_hash}:{})};
   const value=await post(endpoint(entry.id)+'/'+batch.action,body);
   const resultId=batch.action==='revalidate'?value.id:entry.id;
   try{const current=await api(endpoint(resultId));results.push({...entry,outcome:'success',resultId,status:current.status,cleared:current.cleared});}
   catch{results.push({...entry,outcome:'unverified',resultId,message:'请求已提交，状态暂未读回；请刷新查看结果。'});}
  }catch(error){results.push({...entry,outcome:'failed',message:error.message});}
  onProgress([...results]);
 }
 return results;
}
