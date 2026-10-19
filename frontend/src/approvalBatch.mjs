// Bulk actions reuse the exact single-record contracts, without merging authority.
export const approvalNeedsAttention=status=>['invalid','failed','stale','blocked'].includes(status);
export const batchActionFor=tab=>({pending:'approve',approved:'apply',attention:'revalidate'})[tab];
export const batchActionLabel=action=>({approve:'批量批准',apply:'批量应用',revalidate:'批量重新校验'})[action];
const endpoint=id=>'/api/console/approvals/'+encodeURIComponent(id);
const canonical=value=>JSON.stringify(sort(value));
const sort=value=>Array.isArray(value)?value.map(sort):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,sort(value[k])])):value;
const binding=data=>canonical(Object.fromEntries(['id','kind','scope_id','scope_type','target','candidate_hash','baseline','approval_hash'].map(k=>[k,data[k]??null])));
const eligible=(data,action)=>action==='approve'?data.status==='pending'&&data.can_approve:action==='apply'?data.status==='approved'&&data.can_apply&&data.approval_hash:approvalNeedsAttention(data.status)&&data.revalidation?.available;
function validate(data,row,action){
 if(data.id!==row.id||data.scope_id!==row.scope_id||data.scope_type!==row.scope_type)throw Error('记录的作用范围已变化，请刷新后重新选择。');
 if(!eligible(data,action))throw Error(action==='revalidate'?(data.revalidation?.reason||'此记录需返回所属配置处理，不能批量重新校验。'):'记录状态已变化，当前不能执行此操作。');
}
export async function prepareApprovalBatch(rows,action,api){
 if(!['approve','apply','revalidate'].includes(action))throw Error('未知批量操作');
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
  const owners=new Map();for(const entry of entries)if(!entry.error){const key=canonical([entry.data.scope_type,entry.data.scope_id]);owners.set(key,(owners.get(key)||0)+1);}
  for(const entry of entries)if(!entry.error&&owners.get(canonical([entry.data.scope_type,entry.data.scope_id]))>1)entry.error='同一范围选择了多项变更，请只选一项，或先在所属配置中合并后提交。';
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
   const body=batch.action==='revalidate'?{plan_hash:entry.plan.plan_hash,request_key:entry.requestKey}:{proposal_hash:entry.data.candidate_hash||entry.data.proposal_hash,request_key:entry.requestKey,...(batch.action==='apply'?{approval_hash:entry.data.approval_hash}:{})};
   const value=await post(endpoint(entry.id)+'/'+batch.action,body);
   const resultId=batch.action==='revalidate'?value.id:entry.id;
   try{const current=await api(endpoint(resultId));results.push({...entry,outcome:'success',resultId,status:current.status});}
   catch{results.push({...entry,outcome:'unverified',resultId,message:'请求已提交，状态暂未读回；请刷新查看结果。'});}
  }catch(error){results.push({...entry,outcome:'failed',message:error.message});}
  onProgress([...results]);
 }
 return results;
}
