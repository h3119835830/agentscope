// Bound presentation reads without timing out a possibly committed write.
export async function requestJSON(fetcher,url,options={},timeoutMs=10000){
 const read=['GET','HEAD'].includes((options.method||'GET').toUpperCase());
 const controller=read?new AbortController():null;
 const abort=()=>controller.abort(options.signal?.reason);
 if(read&&options.signal){if(options.signal.aborted)abort();else options.signal.addEventListener('abort',abort,{once:true});}
 let timer;
 const request=async()=>{
  const response=await fetcher(url,{...options,...(read?{signal:controller.signal}:{})});
  let data;
  try{data=await response.json();}catch{if(response.ok)throw new Error('返回的数据无法读取，请重试。');data={};}
  if(!response.ok)throw new Error(data.detail||`请求失败 (${response.status})`);
  return data;
 };
 try{
  if(!read)return await request();
  return await Promise.race([request(),new Promise((_,reject)=>{timer=setTimeout(()=>{reject(new Error('读取超时，请重试。'));controller.abort();},timeoutMs);})]);
 }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',abort);}
}

export function singleFlight(load){
 let pending=null;
 return (...args)=>{
  if(!pending)pending=Promise.resolve().then(()=>load(...args)).finally(()=>{pending=null;});
  return pending;
 };
}

export function agentSummary(data){
 const agents=(data.instances||[]).filter(row=>row.mode==='controlled');
 return {agents,stats:{agents:agents.length,verified_agents:agents.filter(row=>row.active&&row.connected).length}};
}

export async function readOverview({api,onAgents,onStatus,onCounts,onError}){
 let agentsLoaded=false;
 await Promise.all([
  api('/api/console/agents').then(data=>{onAgents(agentSummary(data));agentsLoaded=true;}).catch(error=>onError('agents',error)),
  api('/api/status').then(onStatus).catch(error=>onError('status',error)),
 ]);
 // Historical counts must never delay current Agent visibility or replace it.
 if(agentsLoaded)await api('/api/console/summary').then(onCounts).catch(error=>onError('counts',error));
}
