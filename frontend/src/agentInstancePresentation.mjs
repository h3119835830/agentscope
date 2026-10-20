export const agentTypes={dsh:'DeepSeek Harness',hermes:'Hermes',codex:'Codex',other:'其他 Agent','hermes-desktop':'Hermes Desktop'};
export const agentName=row=>row.display_name||[row.name,agentTypes[row.agent_type]||'Agent'].filter((v,i,a)=>v&&a.indexOf(v)===i).join(' · ')+(row.id?' · '+String(row.id).replace(/^instance-/,'').slice(0,8):'');
export const agentProcessLabel=agentName;
export const entryKind=row=>row.entry?.kind||(row.mode==='controlled'&&['dsh','hermes'].includes(row.agent_type)?'web':'process');
export const entryLabel=row=>row.entry?.label||({terminal:'终端',web:'Web',cli:'CLI',cli_install:'CLI 安装入口',desktop:'桌面应用',process:'进程观测'})[entryKind(row)]||'进程观测';
export const processLabel=row=>row.pid&&['running','discovered'].includes(row.status)?row.pid:'—';
export const observedProcesses=row=>processLabel(row)==='—'?[]:[{pid:row.pid,ppid:row.ppid,role:'observed process',domain_verified:false}];
export const canOpen=row=>['web','terminal'].includes(entryKind(row))&&!['unknown','stale'].includes(row.status)&&Boolean(row.connected||row.can_open);
export const canStart=row=>['web','terminal'].includes(entryKind(row))&&row.mode==='controlled'&&!canOpen(row)&&row.product_status?.runtime?.state==='stopped';
// An unknown observation must not remove the read-only entry check, or imply a start.
export const canCheckEntry=row=>row.mode==='controlled'&&Boolean(row.id)&&['web','terminal'].includes(entryKind(row));
export function entryAction(row){
 if(canOpen(row))return {label:'打开',action:'open'};
 if(canStart(row))return {label:'启动并打开',action:'start'};
 if(canCheckEntry(row))return {label:'打开',action:'check'};
 if(['cli','cli_install'].includes(entryKind(row)))return {label:'CLI 启动方式',action:'instructions'};
 if(entryKind(row)==='desktop')return {label:'查看桌面入口',action:'instructions'};
 if(entryKind(row)==='web')return {label:'查看入口',action:'instructions'};
 return {label:'查看进程',action:'processes'};
}
export const connectionStatus=row=>row.product_status?.runtime?.label||'状态未知';

// Group presentation only. Each member retains its own identity and policy.
export function groupAgentInstances(rows){
 const groups=new Map();
 for(const row of rows){
  const key=row.agent_type&&row.agent_type!=='other'?row.agent_type:'other:'+row.id;
  if(!groups.has(key))groups.set(key,{key,name:agentTypes[row.agent_type]||agentName(row),members:[]});
  groups.get(key).members.push(row);
 }
 const rank=row=>canOpen(row)?(row.active?4:3):canStart(row)?2:1;
 return [...groups.values()].map(group=>{
  const preferred=[...group.members].sort((a,b)=>rank(b)-rank(a))[0];
  return {...group,preferred};
 });
}

// Keep every configurable instance reachable after removing the instance picker.
export function visibleAgentInstances(rows){
 return groupAgentInstances(rows).flatMap(group=>{
  const controlled=group.members.filter(row=>row.mode==='controlled');
  return controlled.length?controlled:[group.preferred];
 });
}
