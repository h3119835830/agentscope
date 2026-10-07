import http from 'node:http';
import {createRequester} from './transport.js';
import {publicEvent,restorePublicSession,publicQuestionAnswer,acceptedUserMessages,receivedOperationFeedback} from './public-session.js';
import {createExecutionLane} from './execution-lane.js';
import {randomUUID, timingSafeEqual} from 'node:crypto';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
import {installTaskSandbox,TASK_TOOLS} from './task-sandbox.js';
import {runtimeObservation} from './runtime-observation.js';
import {verifyTaskSandbox} from './verify-task-sandbox.js';
export const name='agentscope-managed-native-web';
export const inject=['tools','sessions','sessionController','connection','workspaceRegistry','sandboxPolicy','sandbox','subprocess','fs','systemPrompt'];
const text = value => typeof value === 'string' ? value : (value?.content || value?.message?.content || []).filter(x=>x.type==='text').map(x=>x.text).join('\n');
export function apply(ctx) {
 const task=process.env.AGENTSCOPE_TASK_ID, token=process.env.AGENTSCOPE_TASK_TOKEN;
 const base=process.env.AGENTSCOPE_URL, workspace=process.env.AGENTSCOPE_MANAGED_WORKSPACE;
 const port=Number(process.env.AGENTSCOPE_NATIVE_PORT), secret=process.env.AGENTSCOPE_NATIVE_TOKEN;
 let compaction=null;
 ctx.inject(['compaction'],child=>{compaction=child.compaction;child.on('dispose',()=>{compaction=null;});});
 let sid=null, turn=0, transportError=null, pending=Promise.resolve(); const starts=new Map(); const visible=[];
 const transport={retry_count:0,recovered_calls:0,state:'connected'};
 const request=createRequester({onRetry:()=>{transport.retry_count++;transport.state='retrying';},onRecovery:()=>{transport.recovered_calls++;transport.state='connected';}});
 async function api(path,args) {
  return request(base+'/api/plugin/tasks/'+task+'/managed/'+path,{method:args?'POST':'GET',headers:{'content-type':'application/json',authorization:'Bearer '+token},body:args?JSON.stringify({args}):undefined});
 }
 for(const key of Object.keys(process.env))if(key.startsWith('AGENTSCOPE_')||key.startsWith('ACTPLANE_'))delete process.env[key];
 const acquire=createExecutionLane();
 installTaskSandbox(ctx,workspace);
 ctx.on('system-prompt/assemble',async(assembly,context,next)=>{
  const result=await next();result.tools=result.tools.filter(tool=>TASK_TOOLS.has(tool.name));return result;
 });
 const resolvePolicy=ctx.sandboxPolicy.resolve.bind(ctx.sandboxPolicy);
 ctx.sandboxPolicy.resolve=request=>{
  const policy=resolvePolicy(request);
  return request?.session?.id===sid?{...policy,mode:policy.mode==='danger-full-access'?'workspace-write':policy.mode,workspaceRoot:workspace}:policy;
 };
 ctx.on('approval/request',async(req,next)=>{
  if(req.agent?.id!==sid)return next();
  await api('change',{kind:'guidance',text:'Native DSH requested '+req.toolName+': '+(req.reason||'permission review')+'. Evaluate supported OS targets; no unconfined retry is authorized by this request.',request_key:'approval:'+String(req.callId||randomUUID())});
  return 'rejected';
 });
 ctx.on('session/event',(session,event)=>{
  if(!sid || sid!==session.id)return;
  const type=event.type, data=event.data||event;
  try {const observation=runtimeObservation(session,event);if(observation)pending=pending.then(()=>api('events',observation)).catch(e=>{transportError=e;console.error('Runtime observation transport:',e.message);});}
  catch(e){transportError=e;}
  for(const received of receivedOperationFeedback(session,event))pending=pending.then(()=>api('events',received)).catch(e=>{transportError=e;});
  for(const accepted of acceptedUserMessages(session,event))pending=pending.then(()=>api('events',accepted)).catch(e=>{transportError=e;console.error('AgentScope accepted-message transport:',e.message);});
  const answered=publicQuestionAnswer(session,event);
  if(answered)pending=pending.then(()=>api('events',{kind:'user_question_answer',session_id:session.id,event_key:'question:'+answered.call_id,...answered})).catch(e=>{transportError=e;console.error('AgentScope question evidence transport:',e.message);});
  if(type==='turn/start')turn=data.turn;
  if(!['turn/start','turn/end','user/message','assistant/message'].includes(type))return;
  if(type==='user/message' && !['user','user-question-reply'].includes(data.source?.kind))return;
  const publicText=type==='assistant/message'?text(data.message):type==='user/message'?text(data):'';
  const payload={kind:'native_event',session_id:session.id,event_key:String(session.id)+':'+String(event.seq),type,data:{turn:data.turn,reason:data.reason,request_id:data.source?.rpcId},text:publicText};
  visible.push(publicEvent(session.id,event,turn));if(visible.length>300)visible.shift();
  pending=pending.then(()=>api('events',payload)).catch(e=>{transportError=e;console.error('AgentScope native evidence transport:',e.message);});
 });
 ctx.on('tools/pre-execute',async(exec,next)=>{
  if(!sid || exec.agent?.id!==sid)return {kind:'deny',reason:'Only the bound managed session can execute tools.'};
  if(!TASK_TOOLS.has(exec.name))return {kind:'deny',reason:'This tool is unavailable in the task execution environment.'};
  return next();
 });
 // DSH preflights a whole parallel batch before dispatch. Serialize the bodies,
 // and release before post-processing, which may also await the whole batch.
 ctx.on('tools/execute',async(exec,next)=>{
  if(exec.parent)return next();
  const release=await acquire(exec.signal);
  if(!release)throw new DOMException('Managed tool cancelled','AbortError');
  let started=false;
  try{
   await pending;if(transportError)throw transportError;let state;
   while(!exec.signal.aborted){
    state=await api('gate');
    if(state.gate==='open')break;
    if(['failed','closed'].includes(state.gate))throw Error('AgentScope execution stopped: '+state.gate);
    await new Promise(resolve=>setTimeout(resolve,250));
   }
   exec.signal.throwIfAborted();
   let argumentsObject=exec.arguments;try{if(typeof argumentsObject==='string')argumentsObject=JSON.parse(argumentsObject);}catch{argumentsObject={};}
   const start={session_id:sid,call_id:String(exec.callId),name:exec.name,pid:process.pid,native_sdk_verification:String(exec.callId).startsWith('managed-verification:'),kind:'tool_start',event_key:String(exec.callId),started:{turn},target:argumentsObject&&typeof argumentsObject==='object'?String(argumentsObject.path||argumentsObject.filePath||argumentsObject.file_path||''):'',serialized:true};
   starts.set(exec.callId,start);await api('events',start);started=true;
   let result;
   try{result=await next();return result;}
   finally{
    await api('events',{kind:'tool_result',event_key:String(exec.callId),session_id:sid,call_id:String(exec.callId),name:exec.name,pid:process.pid,succeeded:!!result&&!result.isError,started:start.started});
   }
  }finally{if(!started)starts.delete(exec.callId);release();}
 });
 ctx.on('tools/post-execute',async(exec,result,next)=>{
  if(exec.parent)return next();
  const start=starts.get(exec.callId);if(!start)return next();starts.delete(exec.callId);
  {
   const response=await api('feedback',{call_id:String(exec.callId)});
   const downstream=await next();
   if(!response.events.length)return downstream;
   const message='[ActPlane operation feedback] '+JSON.stringify(response.events)+'\nAdjust the task operation using the available project materials. Ask the user if the task cannot be completed within this execution environment.';
   await api('events',{kind:'feedback_offer',event_key:String(exec.callId),session_id:sid,call_id:String(exec.callId),name:exec.name,feedback:message,event_ids:response.events.map(e=>e.id)});
   return {...downstream,additionalContexts:[createUserMessage({content:[{type:'text',text:message}],source:{kind:'context'}}),...(downstream.additionalContexts||[])]};
  }
 });
 const server=http.createServer(async(req,res)=>{
  try{
   const supplied=req.headers.authorization||'',expected='Bearer '+secret;
   if(supplied.length!==expected.length || !timingSafeEqual(Buffer.from(supplied),Buffer.from(expected))){res.writeHead(401);res.end('{}');return;}
   let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>18000)throw Error('request too large');}
   const data=JSON.parse(raw||'{}');const signal=AbortSignal.timeout(30000);let result;
   if(data.operation==='create'){
    const registered=await ctx.workspaceRegistry.create(workspace,'任务工作区');
    const created=await ctx.sessionController.create({workspaceId:registered.id,agentPreset:'standard',...(data.session_id?{sessionId:data.session_id}:{})});sid=created.sessionId;const found=await ctx.sessionController.resolveAgent(sid);if(found.error)throw found.error;const restored=restorePublicSession(found.agent.session);turn=restored.turn;visible.splice(0,visible.length,...restored.events);result=created;
   }else{
    if(!sid || data.session_id!==sid)throw Error('session binding mismatch');
    if(data.operation==='open_url')result={url:ctx.connection.authenticatedUrl('http://127.0.0.1:'+String(port-100)+'/')};
    else if(data.operation==='prompt')result=await ctx.sessionController.prompt({sessionId:sid,requestId:data.request_id||randomUUID(),mode:'queue',content:[{type:'text',text:data.text}],clientTimeZone:'Asia/Shanghai'},signal);
    else if(data.operation==='compact'){
      const found=await ctx.sessionController.resolveAgent(sid);if(found.error)throw found.error;
      if(found.agent.status!=='idle'||(await api('gate')).gate!=='open')throw Error('Wait for the native session and analysis gate');
      if(!compaction)throw Error('Native compaction engine unavailable.');
      const compacted=await compaction.compactNow(found.agent,AbortSignal.timeout(60000));
      await ctx.parallel('session/flush',found.agent.session);await pending;if(transportError)throw transportError;
      result={compacted:!!compacted,session_id:sid,source:'native_manual_compaction',private_content_exported:false};
     }
     else if(data.operation==='verify_task_sandbox'){
      const found=await ctx.sessionController.resolveAgent(sid);if(found.error)throw found.error;
      if(found.agent.status!=='idle'||(await api('gate')).gate!=='open')throw Error('Wait for the native session and analysis gate');
      result=await verifyTaskSandbox(ctx,found.agent,workspace,signal);
     }
     else if(data.operation==='verify_delayed_open'){
     const found=await ctx.sessionController.resolveAgent(sid);if(found.error)throw found.error;
     if(found.agent.status!=='idle')throw Error('Native session must be idle for independent verification');
     const state=await api('gate');
     if(state.gate!=='open')throw Error('Execution is paused');
     const callId='managed-verification:'+randomUUID(),output=workspace+'/.managed-late-'+randomUUID()+'.txt';
     const program='import os,time;time.sleep(8)\ntry:\n fd=os.open('+JSON.stringify(data.target)+',os.O_WRONLY);os.close(fd);result="allowed"\nexcept PermissionError: result="blocked"\nopen('+JSON.stringify(output)+',"w").write(result)';
     const quote=value=>"'"+value.replaceAll("'","'\\''")+"'";
     if(!ctx.tools.get('bash',found.agent)?.parameters?.properties?.run_in_background)throw Error('Native fixed verification requires the registered bash background-job capability');
     const command='python3 -c '+quote(program);
     const execution=await ctx.tools.execute({callId,name:'bash',arguments:{command,description:'Verify a delayed protected-file open without writing',workdir:workspace,run_in_background:true},agent:found.agent,signal});
     if(execution.isError)throw Error('Native fixed verification tool failed: '+String(execution.error?.message||'unknown').slice(0,800));
     result={call_id:callId,result_path:output,target:data.target,source:'native_sdk_fixed_probe',attempted_by_agent:false};
    }
    else if(data.operation==='observe'){const snapshot=await ctx.sessionController.inspect(sid,signal);if(snapshot?.error)throw Error('Native session unavailable');result={session_id:sid,status:'observed',events:visible,turn,active_tools:starts.size,transport:{...transport},observational:true};}
     else if(data.operation==='inspect'){const found=await ctx.sessionController.resolveAgent(sid);if(found.error)throw found.error;result={session_id:sid,events:visible,turn,active_tools:starts.size,status:found.agent.status,transport:{...transport}};}
    else if(data.operation==='flush'){const found=await ctx.sessionController.resolveAgent(sid);if(found.error)throw found.error;await found.agent.whenIdle();await ctx.parallel('session/flush',found.agent.session);await pending;if(transportError)throw transportError;result={flushed:true};}
    else if(data.operation==='resume'){const found=await ctx.sessionController.resolveAgent(sid);if(found.error)throw found.error;found.agent.followup(createUserMessage({content:[{type:'text',text:data.text}],source:{kind:'context'}}));await ctx.parallel('session/flush',found.agent.session);await pending;if(transportError)throw transportError;result={accepted:true,persisted:true};}
    else if(data.operation==='cancel'){result=ctx.sessionController.cancel({sessionId:sid});}
    else throw Error('unsupported native operation');
   }
   res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify(result));
  }catch(e){res.writeHead(409,{'content-type':'application/json'});res.end(JSON.stringify({error:e.message}));}
 });
 server.listen(port,'127.0.0.1');ctx.on('dispose',()=>server.close());
}
