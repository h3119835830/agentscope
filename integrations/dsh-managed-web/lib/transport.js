/** Retry transient control-plane outages without releasing the execution gate. */
export function createRequester({fetchImpl=fetch,now=()=>Date.now(),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),budgetMs=30000,onRetry=()=>{},onRecovery=()=>{}}={}) {
 return async(url,options={})=>{
  const deadline=now()+budgetMs;let retries=0;
  for(;;){
   try{
    const response=await fetchImpl(url,{...options,signal:AbortSignal.timeout(Math.max(1,Math.min(10000,deadline-now())))});
    const raw=await response.text();let value;
    try{value=JSON.parse(raw);}catch{const error=Error('AgentScope transport returned HTTP '+response.status);error.status=response.status;throw error;}
    if(!response.ok){const error=Error(value.detail||String(response.status));error.status=response.status;throw error;}
    if(retries)onRecovery({retries});return value;
   }catch(error){
    if(error.status && ![502,503,504].includes(error.status))throw error;
    if(now()>=deadline)throw Error('Control-plane transport unavailable; execution remains paused',{cause:error});
    retries++;onRetry({attempt:retries,status:error.status||'network'});
    await sleep(Math.min(250,deadline-now()));
   }
  }
 };
}
