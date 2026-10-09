import http from 'node:http';
import {randomUUID,timingSafeEqual} from 'node:crypto';
import {defineTool} from '@deepseek-ai/dsh-tools';
export const name='agentscope-instance-runtime';
export const inject=['tools','sessions','sessionController','connection','workspaceRegistry','sandboxPolicy','agents'];
export function apply(ctx){
 const id=process.env.AGENTSCOPE_INSTANCE_ID,token=process.env.AGENTSCOPE_INSTANCE_TOKEN,generation=process.env.AGENTSCOPE_GENERATION;
 const base=process.env.AGENTSCOPE_INSTANCE_URL,secret=process.env.AGENTSCOPE_NATIVE_TOKEN,port=Number(process.env.AGENTSCOPE_NATIVE_PORT);
 const webPort=Number(process.env.AGENTSCOPE_WEB_PORT),resources=JSON.parse(process.env.AGENTSCOPE_RESOURCES);
 const calls=new Map();
 async function api(path,body){
  const response=await fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json',authorization:'Bearer '+token},body:JSON.stringify({generation,...body}),signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('AgentScope control unavailable; tool execution paused');
  return response.json();
 }
 const output={schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]};
 ctx.tools.register(defineTool({name:'agentscope_instance_scope',description:'读取此实例全部会话共享的策略、资源目录与候选基准。',parameters:{},output,execute:async()=>JSON.stringify(await api('/scope',{}))}));
 ctx.tools.register(defineTool({name:'agentscope_instance_propose',description:'提交类型化实例策略候选。校验后的收紧自动应用并重启此实例；扩权等待用户确认。不能提交 DSL 或自行批准。',parameters:{policy_json:{type:'string',required:true,description:'完整策略 JSON，含 rules 和 network，先读取当前实例 Scope。'},base_hash:{type:'string',required:true,description:'刚读取的 policy_hash'},request_key:{type:'string',required:true,description:'本次候选唯一幂等键，重试时保持不变'}},output,execute:async(args)=>JSON.stringify(await api('/policy/proposals',{policy:JSON.parse(args.policy_json),base_hash:args.base_hash,request_key:args.request_key}))}));
 const resolvePolicy=ctx.sandboxPolicy.resolve.bind(ctx.sandboxPolicy);
 ctx.sandboxPolicy.resolve=request=>{
  const p=resolvePolicy(request);
  return {...p,mode:'danger-full-access'};
 };
 // The entire native process already lives in a root-created mount namespace.
 // All sessions and tool subprocesses inherit the same ActPlane domain/cgroup.
 ctx.on('tools/execute',async(exec,next)=>{
  if(exec.parent)return next();
  const sid=exec.agent?.session?.id||exec.agent?.id;
  if(!sid)throw Error('Cannot attribute this tool to a native session');
  const call=String(exec.callId||randomUUID());
  const event={session_id:sid,call_id:call,tool:exec.name};
  const admission=await api('/lease',event);
  if(!admission.allowed)throw Error(admission.reason||'Instance tool denied');
  calls.set(call,event);
  let succeeded=false;
  try{const result=await next();succeeded=!!result&&!result.isError;return result;}
  finally{calls.delete(call);await api('/result',{...event,succeeded});}
 });
 const server=http.createServer(async(req,res)=>{
  try{
   const expected='Bearer '+secret,supplied=req.headers.authorization||'';
   if(expected.length!==supplied.length||!timingSafeEqual(Buffer.from(expected),Buffer.from(supplied)))throw Error('Unauthorized');
   let raw='';for await(const c of req){raw+=c;if(raw.length>18000)throw Error('Request too large');}
   const data=JSON.parse(raw||'{}');let result;
   if(data.operation==='observe'){
    const sessions=[];
    for(const w of ctx.workspaceRegistry.list())for(const sid of w.sessionIds||[]){
     const live=ctx.agents.get(sid);
     sessions.push({id:sid,resource:w.path,process_ids:live?[process.pid]:[],mapping:'native_registry',status:live?.status||'stored'});
    }
    result={pid:process.pid,sessions,inflight:calls.size};
   }else if(data.operation==='open_url')result={url:ctx.connection.authenticatedUrl('http://127.0.0.1:'+webPort+'/')};
   else if(data.operation==='flush'){
    for(const w of ctx.workspaceRegistry.list())for(const sid of w.sessionIds||[]){
     const found=await ctx.sessionController.resolveAgent(sid);
     if(!found.error)await ctx.parallel('session/flush',found.agent.session);
    }
    result={ok:true};
   }else if(data.operation==='create'){
    if(!resources.includes(data.resource))throw Error('Resource not registered');
    let workspace=ctx.workspaceRegistry.list().find(w=>w.path===data.resource);
    if(!workspace)workspace=await ctx.workspaceRegistry.create(data.resource,'实例资源');
    result=await ctx.sessionController.create({workspaceId:workspace.workspaceId||workspace.id,agentPreset:'standard'});
   }else{
    const found=await ctx.sessionController.resolveAgent(data.session_id);if(found.error)throw found.error;
    if(data.operation==='prompt')result=await ctx.sessionController.prompt({sessionId:data.session_id,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:data.text}],clientTimeZone:'Asia/Shanghai'},AbortSignal.timeout(30000));
    else if(data.operation==='inspect')result={session_id:data.session_id,status:found.agent.status};
    else if(data.operation==='cancel')result=await ctx.sessionController.cancel({sessionId:data.session_id});
    else if(data.operation==='flush'){await ctx.parallel('session/flush',found.agent.session);result={ok:true};}
    else throw Error('Operation unavailable');
   }
   res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result));
  }catch(error){res.writeHead(409);res.end(JSON.stringify({error:error.message}));}
 });
 server.listen(port,'127.0.0.1');
 ctx.on('dispose',()=>server.close());
}
