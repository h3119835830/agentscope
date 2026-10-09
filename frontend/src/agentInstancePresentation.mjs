export const agentTypes={dsh:'DeepSeek Harness',hermes:'Hermes',codex:'Codex',other:'其他 Agent','hermes-desktop':'Hermes Desktop'};
export const agentName=row=>row.agent_type==='other'?(row.name||agentTypes.other):(agentTypes[row.agent_type]||row.name||'Agent');
export const entryKind=row=>row.entry?.kind||(row.mode==='controlled'&&['dsh','hermes'].includes(row.agent_type)?'web':'process');
export const entryLabel=row=>row.entry?.label||({web:'Web',cli:'CLI',cli_install:'CLI 安装入口',desktop:'桌面应用',process:'进程观测'})[entryKind(row)]||'进程观测';
export const processLabel=row=>row.pid&&['running','discovered'].includes(row.status)?row.pid:'—';
export const observedProcesses=row=>processLabel(row)==='—'?[]:[{pid:row.pid,ppid:row.ppid,role:'observed process',domain_verified:false}];
export const canOpen=row=>entryKind(row)==='web'&&!['unknown','stale'].includes(row.status)&&Boolean(row.connected||row.can_open);
export const canStart=row=>entryKind(row)==='web'&&row.mode==='controlled'&&!canOpen(row);
export function entryAction(row){
 if(canOpen(row))return {label:'打开网页',action:'open'};
 if(canStart(row))return {label:'启动网页',action:'start'};
 if(['cli','cli_install'].includes(entryKind(row)))return {label:'CLI 启动方式',action:'instructions'};
 if(entryKind(row)==='desktop')return {label:'查看桌面入口',action:'instructions'};
 if(entryKind(row)==='web')return {label:'查看入口',action:'instructions'};
 return {label:'查看进程',action:'processes'};
}
export const connectionStatus=row=>canOpen(row)?(row.connected?'已连接':'入口已登记'):
  row.mode==='controlled'&&['open','paused'].includes(row.gate)?'执行暂停':
  ({installed:'已安装，未启动',discovered:'已发现进程',starting:'正在启动',stale:'证据已过期',unknown:'状态未知',paused:'执行暂停',offline:'未运行'})[row.status]||'已登记';

// Group presentation only. Each member retains its own identity and policy.
export function groupAgentInstances(rows){
 const groups=new Map();
 for(const row of rows){
  const key=row.agent_type&&row.agent_type!=='other'?row.agent_type:'other:'+row.id;
  if(!groups.has(key))groups.set(key,{key,name:agentName(row),members:[]});
  groups.get(key).members.push(row);
 }
 const rank=row=>canOpen(row)?(row.active?4:3):canStart(row)?2:1;
 return [...groups.values()].map(group=>{
  const preferred=[...group.members].sort((a,b)=>rank(b)-rank(a))[0];
  return {...group,preferred};
 });
}
