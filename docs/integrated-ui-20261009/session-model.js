// Prototype fixtures. Identity, policy selection and observed state stay separate.
const taskDrafts={coding:taskDraft,research:clone(taskDraft)};
const sessionRecords=Object.freeze([
  {id:'S-DEMO',name:'登录表单修复',agent:'编码 Agent',instanceId:'DSH-CODE-01',workspace:'/workspace',scope:'D-A',taskKey:'coding',parentId:null,lastActivity:'2026-10-09 10:20（样例）'},
  {id:'S-DEMO-TEST',name:'登录表单修复 · 测试',agent:'测试 Agent',instanceId:'DSH-CODE-01',workspace:'/workspace/tests',scope:'D-A1',taskKey:'coding',parentId:'S-DEMO',lastActivity:'2026-10-09 10:21（样例）'},
  {id:'S-RESEARCH',name:'研究任务 B',agent:'研究 Agent',instanceId:'DSH-RESEARCH-01',workspace:'/workspace/research',scope:'D-B',taskKey:'research',parentId:null,lastActivity:'2026-10-09 09:30（样例）'}
].map(s=>Object.freeze({...s,nativeRef:null})));
const sessionsById=Object.fromEntries(sessionRecords.map(s=>[s.id,s]));
const sessionForScope=scope=>sessionRecords.find(s=>s.scope===scope);
const taskInfo=Object.fromEntries(sessionRecords.filter(s=>!s.parentId).map(s=>[s.taskKey,{...s,root:s.scope}]));
const sessionRuntime=Object.fromEntries(sessionRecords.map(s=>[s.id,{connection:s.id==='S-RESEARCH'?'disconnected':'connected',executor:s.id==='S-RESEARCH'?'stopped':'idle'}]));
const currentSession=()=>sessionForScope(domain);
function policyRulesForScope(scope){
  const draft=taskDrafts[scope==='D-B'?'research':'coding'];
  const local=scope==='D-B'?['P13','P15']:['P06','P11','P15'];
  return [
    ...['P01','P02','P04'].map(id=>({...sessionBaseline[id],inherited:true,sourceLabel:'平台底线',sourceDetail:'基线 v0.1'})),
    ...local.map(id=>({...draft[id],inherited:scope==='D-A1',sourceLabel:scope==='D-A1'?'父任务':id==='P15'?'用户设置':'场景 Agent',sourceDetail:scope==='D-A1'?'来自 D-A':''})),
    ...(scope==='D-A1'?[{...draft.C01,inherited:false,sourceLabel:'场景 Agent',sourceDetail:'本会话新增'}]:[])
  ];
}
function sessionStateText(id){
  if(pendingSessionOpens.has(id))return '正在打开原生会话';
  const r=sessionRuntime[id];
  if(r.executor==='stopped')return '已停止（样例）';
  if(r.connection==='disconnected')return '连接中断（样例）';
  return r.executor==='running'?'执行中（样例）':'空闲（样例）';
}
function relationModel(view,taskKey){
  const task=taskInfo[taskKey],coding=taskKey==='coding',child=sessionsById['S-DEMO-TEST'];
  let nodes=[],edges=[];
  if(view==='agents'){
    nodes=[{id:'session-agent',kind:'agent',type:'会话 Agent · 进程内对象',name:task.agent,meta:task.id+' · '+sessionStateText(task.id),x:50,y:25,scope:task.scope,sessionIds:[task.id],identity:'进程内对象 · 无独立 PID',note:'Agent 对象与聊天 Session 关联；回复结束后可以进入空闲。'}];
    if(coding){nodes.push({id:'shell-tool',kind:'process',type:'工具调用',name:'shell / pytest',meta:'调用时按需启动工具进程',x:25,y:190,sessionIds:[task.id],identity:'工具调用 · PID 待观测',note:'工具归属与实际策略绑定需可信执行记录。'},{id:'test-agent',kind:'agent',type:'子 Agent · 进程内对象',name:child.agent,meta:child.id+' · 进程内委派',x:75,y:190,scope:child.scope,sessionIds:[child.id],identity:'进程内对象 · 无独立 PID',note:'子 Agent 有独立逻辑会话 ID，但不默认拥有独立 OS 进程或策略域绑定。'});edges=[['session-agent','shell-tool','调用工具'],['session-agent','test-agent','委派 · 进程内']];}
  }else if(view==='processes'){
    const pid=coding?210:310,ids=sessionRecords.filter(s=>s.instanceId===task.instanceId).map(s=>s.id);
    nodes=[{id:'host-process',kind:'process',type:'共享宿主进程',name:'DSH Web',meta:`PID ${pid}（样例）· 可承载多个会话`,x:50,y:25,pid,ppid:'未观测',sessionIds:ids,identity:`PID ${pid} / 父 PID 未观测`,note:'共享宿主不是会话专属进程。这里展示所选关联会话的配置；不能据此认定全部策略已绑定到该 PID。'}];
    if(coding){nodes.push({id:'shell-process',kind:'process',type:'工具子进程',name:'shell',meta:'PID 211（样例）· 存活待观测',x:50,y:167,pid:211,ppid:210,sessionIds:[task.id],identity:'PID 211 / 父 PID 210',note:'会话归属为样例；持久 shell 或后台任务可能继续存活，需另行观测。'},{id:'test-process',kind:'process',type:'工具后代进程',name:'pytest',meta:'PID 212（样例）· 存活待观测',x:50,y:310,pid:212,ppid:211,sessionIds:[task.id],identity:'PID 212 / 父 PID 211',note:'父子关系不证明实际策略已生效；规则加载和 OS 绑定分别核验。'});edges=[['host-process','shell-process','启动工具'],['shell-process','test-process','运行测试']];}
  }else{
    nodes=[{id:'d0',kind:'domain',type:'平台规则来源',name:'平台底线 D0',meta:'v0.1 · 3 条继承规则',x:50,y:25,scope:'D0',sessionIds:[],identity:'平台规则来源'},{id:'task-domain',kind:'domain',type:'任务域',name:coding?'编码任务 D-A':'研究任务 D-B',meta:`${policyRulesForScope(task.scope).length} 条目标规则 · 未绑定`,x:50,y:167,scope:task.scope,sessionIds:[task.id],identity:'目标域 '+task.scope}];
    edges=[['d0','task-domain','继承平台底线']];
    if(coding){nodes.push({id:'child-domain',kind:'domain',type:'子 Agent 域',name:'测试子域 D-A1',meta:'7 条目标规则 · 未绑定',x:50,y:310,scope:child.scope,sessionIds:[child.id],identity:'目标域 D-A1'});edges.push(['task-domain','child-domain','继承任务约束']);}
  }
  return {nodes:nodes.map(n=>({...n,selected:n.scope===domain})),edges};
}
