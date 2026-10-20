import {canOpen,canStart,canCheckEntry} from './agentInstancePresentation.mjs';
import {openAgentPage} from './openAgentPage.mjs';

const endpoint=id=>'/api/agent-instances/'+encodeURIComponent(id);
const identity=row=>[row.id,row.mode,row.generation??null,row.policy_hash??null,row.launch?.hash??null];
const recoverable=row=>canCheckEntry(row)&&!canOpen(row)&&!['starting','updating'].includes(row.gate)
 && !['starting','running','paused'].includes(row.product_status?.runtime?.state);

export async function openConnection({row,post,onRecovery,browser}){
 try{return await openAgentPage({id:row.id,start:canStart(row),post,browser});}
 catch(error){
  // Popup failures, invalid URLs and launch failures must never suggest a restart.
  if(!error.entryUnavailable||!canCheckEntry(row))throw error;
  const current=await post(endpoint(row.id)+'/check');
  if(current.id!==row.id||!recoverable(current))throw error;
  onRecovery({row:structuredClone(current),reason:error.message});
 }
}

// Called only from an explicit confirmation; no start on failed or changed checks.
export async function restartConnection({snapshot,post,browser}){
 return openAgentPage({id:snapshot.id,start:true,post,browser,prepareStart:async()=>{
  const current=await post(endpoint(snapshot.id)+'/check');
  if(JSON.stringify(identity(current))!==JSON.stringify(identity(snapshot)))
   throw Error('连接或运行配置已变化，请取消后重新点击打开');
  if(canOpen(current))return false; // Recovered meanwhile: reuse, do not restart.
  if(!recoverable(current))throw Error('当前运行状态已变化，请取消后重新检查');
  return true;
 }});
}
