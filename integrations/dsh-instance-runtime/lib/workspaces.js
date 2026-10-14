import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import path from 'node:path';
const inside=(value,base)=>value===base||value.startsWith(base+'/');
export const projectWorkspace=w=>({id:w.workspaceId||w.id,name:w.title||path.basename(w.path),path:w.path,session_ids:[...(w.sessionIds||[])]});
export async function filesForWorkspace(workspaces,id,relative,roots,denies=[]){
 const workspace=workspaces.find(w=>(w.workspaceId||w.id)===id);
 if(!workspace)throw Error('工作区不属于当前 Agent');
 if(typeof relative!=='string'||relative.startsWith('/')||relative.split('/').some(p=>p==='..'||p==='.')||relative.length>2000)throw Error('目录路径不合法');
 const root=await fs.realpath(workspace.path);
 if(!roots.some(base=>inside(root,base)))throw Error('此原生工作区超出已授权文件范围，请在安全配置中调整');
 let directory=root;
 const handles=[];
 try{
  let handle=await fs.open(root,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);handles.push(handle);
  for(const part of relative.split('/').filter(Boolean)){
   directory=path.join(directory,part);
   handle=await fs.open('/proc/self/fd/'+handle.fd+'/'+part,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);handles.push(handle);
  }
  if(denies.some(base=>inside(directory,base)))throw Error('系统或 Agent 策略禁止读取此目录');
  const anchored='/proc/self/fd/'+handle.fd;
  const entries=await fs.readdir(anchored,{withFileTypes:true});
  const files=[];
  for(const entry of entries.sort((a,b)=>Number(b.isDirectory())-Number(a.isDirectory())||a.name.localeCompare(b.name)).slice(0,500)){
   const target=path.join(directory,entry.name),blocked=denies.some(base=>inside(target,base));
   let info;
   try{info=blocked?null:await fs.lstat(anchored+'/'+entry.name)}catch(error){if(error.code==='ENOENT')continue;throw error}
   files.push({name:entry.name,path:[relative,entry.name].filter(Boolean).join('/'),kind:entry.isSymbolicLink()?'symlink':entry.isDirectory()?'directory':'file',size:info?.size??null,blocked});
  }
  return {workspace:projectWorkspace(workspace),path:relative,files,truncated:entries.length>500};
 }catch(error){
  if(['EACCES','EPERM'].includes(error.code))throw Error('系统或 Agent 策略禁止读取此目录');
  if(['ENOTDIR','ELOOP','ENOENT'].includes(error.code))throw Error('目录已变化或包含符号链接，请刷新工作区');
  throw error;
 }finally{for(const handle of handles.reverse())await handle.close()}

}
