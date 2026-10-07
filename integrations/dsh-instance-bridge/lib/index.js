import net from 'node:net';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import z from '@deepseek-ai/schemastery';
export const name='agentscope-instance-bridge';
export const inject=['workspaceController','workspaceRegistry','directoryPickerController'];
export const Config=z.object({
 instanceId:z.string().default('native-dsh'),
 socketPath:z.string().default('/run/agentscope-dsh/instance.sock'),
 roots:z.array(z.string()).default([]),
});
export function generation(instanceId,pid,startTicks){
 return createHash('sha256').update(instanceId+':'+pid+':'+startTicks).digest('hex').slice(0,24);
}
export async function canonicalDirectory(value, roots){
 if(typeof value!=='string'||!path.isAbsolute(value))throw Error('Absolute directory required');
 const canonical=await fs.realpath(value);
 if(canonical!==value||!(await fs.stat(canonical)).isDirectory())throw Error('Canonical directory required');
 if(!roots.some(root=>canonical===root||canonical.startsWith(root+path.sep)))throw Error('Outside operator roots');
 return canonical;
}
export const projectWorkspace=w=>({workspaceId:w.workspaceId||w.id,path:w.path,title:w.title,sessionIds:[...(w.sessionIds||[])],createdAt:w.createdAt,updatedAt:w.updatedAt});
export async function dispatchWorkspaceRequest(ctx, request, state){
 const {config,currentGeneration,roots,ready,revision}=state;
 if(request.version!==1||request.instance_id!==config.instanceId||request.generation!==currentGeneration||!(/^[a-f0-9]{48}$/).test(request.nonce))throw Error('Handshake mismatch');
 if(!ready)throw Error('Workspace baseline unavailable');
 if(request.operation==='observe'){
  const workspaces=[];
  for(const workspace of ctx.workspaceRegistry.list()){
   try{await canonicalDirectory(workspace.path,roots);workspaces.push(projectWorkspace(workspace));}catch{}
  }
  return {workspaces,sync_revision:revision};
 }
 if(request.operation==='workspace-create'){
  const target=await canonicalDirectory(request.path,roots);
  return ctx.workspaceController.create({path:target});
 }
 if(request.operation==='directory-list'){
  const target=await canonicalDirectory(request.path,roots);
  return ctx.directoryPickerController.list(target,AbortSignal.timeout(1200));
 }
 throw Error('Operation unavailable');
}
export async function apply(ctx, config){
 if(!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(config.instanceId))throw Error('Invalid instance identity');
 if(path.dirname(config.socketPath)!=='/run/agentscope-dsh')throw Error('Socket outside fixed runtime directory');
 const runtime=await fs.lstat(path.dirname(config.socketPath));
 if(!runtime.isDirectory()||runtime.uid!==process.getuid()||(runtime.mode&0o077))throw Error('Bridge directory must be owned by DSH service UID with mode 0700');
 const roots=await Promise.all(config.roots.map(async root=>{
  const canonical=await fs.realpath(root);
  if(root!==canonical||root==='/'||!(await fs.stat(root)).isDirectory())throw Error('Invalid operator root');
  return canonical;
 }));
 const raw=await fs.readFile('/proc/self/stat','utf8');
 const startTicks=raw.slice(raw.lastIndexOf(')')+2).split(/\s+/)[19];
 const currentGeneration=generation(config.instanceId,process.pid,startTicks);
 let ready=false, revision=0, disposed=false;
 const lifetime=new AbortController();
 async function follow(){
  while(!disposed){
   ready=false;
   try{
    for await(const frame of ctx.workspaceController.follow(lifetime.signal)){
     if(disposed)break;
     if(!ready&&frame.type!=='baseline')throw Error('Workspace stream missing baseline');
     if(frame.type==='baseline')ready=true;
     revision++;
    }
   }catch{}
   ready=false;
   if(!disposed)await new Promise(resolve=>{const timer=setTimeout(resolve,300);timer.unref?.();});
  }
 }
 const follower=follow();
 const server=net.createServer(channel=>{
  channel.setTimeout(1800,()=>channel.destroy());
  let buffer='',handled=false;
  channel.on('error',()=>{});
  channel.on('data',async chunk=>{
   if(handled)return;
   buffer+=chunk.toString();
   if(buffer.length>16000){handled=true;channel.destroy();return;}
   if(!buffer.includes('\n'))return;
   handled=true;let request;
   try{
    request=JSON.parse(buffer.slice(0,buffer.indexOf('\n')));
    const result=await dispatchWorkspaceRequest(ctx,request,{config,currentGeneration,roots,ready,revision});
    channel.end(JSON.stringify({version:1,nonce:request.nonce,instance_id:config.instanceId,generation:currentGeneration,ok:true,result})+'\n');
   }catch{
    channel.end(JSON.stringify({version:1,nonce:request?.nonce,instance_id:config.instanceId,generation:currentGeneration,ok:false})+'\n');
   }
  });
 });
 // Never replace a live socket or another user's filesystem object.
 try{
  const info=await fs.lstat(config.socketPath);
  if(!info.isSocket()||info.uid!==process.getuid())throw Error('Existing bridge path is not an owned socket');
  const alive=await new Promise(resolve=>{
   const probe=net.connect(config.socketPath);
   probe.once('connect',()=>{probe.destroy();resolve(true);});
   probe.once('error',error=>resolve(error.code!=='ECONNREFUSED'&&error.code!=='ENOENT'));
  });
  if(alive)throw Error('Bridge socket is already active');
  await fs.unlink(config.socketPath);
 }catch(error){if(error.code!=='ENOENT')throw error;}
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(config.socketPath,resolve);});
 await fs.chmod(config.socketPath,0o600);
 ctx.on('dispose',async()=>{
  disposed=true;ready=false;lifetime.abort();server.close();
  await fs.unlink(config.socketPath).catch(()=>{});
  await follower;
 });
}
