export function startupRecoveryPath(task){return `/api/managed/tasks/${encodeURIComponent(task)}/startup/recovery`;}
export function startupRecoveryRequest(recovery,action,selectedCandidate){
 const origin=recovery?.origin;if(!['reuse','rebuild'].includes(action)||!origin?.context_hash||!origin?.manifest_hash)throw new Error('缺少固定上下文或文件清单核验信息，请重新读取恢复状态。');
 if(recovery.eligible!==true)throw new Error(recovery.blocked_reason||'当前任务暂不满足恢复条件。');
 const body={action,expected_context_hash:origin.context_hash,expected_manifest_hash:origin.manifest_hash};
 if(action==='reuse'){const c=selectedCandidate||recovery.candidate||recovery.link;if(c?.status!=='awaiting_review'||!c.task_id||!c.proposal_hash)throw new Error('没有可核验的待审核恢复候选，请重新读取恢复状态。');body.expected_candidate_task_id=c.task_id;body.expected_candidate_proposal_hash=c.proposal_hash;}
 return body;
}

export function pollStartupRecovery({read,onData,onError,schedule=setTimeout,cancel=clearTimeout,interval=3000}){
 let active=true,timer=null;
 async function load(){
  try{const data=await read();if(active)onData(data);}
  catch(error){if(active)onError(error);}
  finally{if(active)timer=schedule(load,interval);}
 }
 load();
 return()=>{active=false;if(timer!==null)cancel(timer);};
}
