export const pages = ['overview','connections','sessions','approvals','workbench','history','strategies'];
export const historySections = ['generate','records','audit'];
export const workbenchSections = ['startup','runtime','overview','audit'];
export const archivePanes = ['overview','startup','runtime','audit','domains','closure'];
const aliases={'agent':'workbench','system':'strategies','agent-bridge':'connections','task':'workbench','scope-demo':'workbench','runtime':'workbench'};
export function readNavigation(href){
 const u=new URL(href),raw=u.searchParams.get('view');let page=aliases[raw]||raw;
 let sessionTab=u.searchParams.get('sessionTab'),sessionCursor=Math.max(0,Number(u.searchParams.get('sessionCursor'))||0);
 const sessions=Object.fromEntries(['sessionAgent','sessionFilterInstance','sessionQuery','sessionInstance','sessionId','sessionWorkspace','connectionInstance','connectionTab','policyScope','policyWorkspace','policyAgent','policySession','approvalId'].map(k=>[k,u.searchParams.get(k)||'']));
 let systemTab=u.searchParams.get('systemTab');const agentPolicyTab=u.searchParams.get('agentPolicyTab');
 if(u.searchParams.get('policyScope')!=='workspace'&&((page==='workbench'&&['policies','configuration','dsl'].includes(agentPolicyTab))||(page==='connections'&&u.searchParams.get('connectionTab')==='policy'))){
  page='strategies';systemTab='policies';sessions.policyAgent=sessions.policyAgent||sessions.connectionInstance;
 }
 // Retired Agent load links select only the original instance's directory,
 // never an unrelated session left in the URL or an inferred latest session.
 if(page==='workbench'&&agentPolicyTab==='loaded'&&!['workspace','system'].includes(sessions.policyScope)&&sessions.policyAgent){
  page='sessions';sessionTab='policies';sessionCursor=0;
  Object.assign(sessions,{sessionFilterInstance:sessions.policyAgent,sessionAgent:'',sessionQuery:'',sessionWorkspace:'',sessionInstance:'',sessionId:''});
 }
 const extra={configurationId:u.searchParams.get('configurationId')||'',approvalRecordId:u.searchParams.get('approvalRecordId')||'',sessionEventKind:u.searchParams.get('sessionEventKind')==='tools'||sessionTab==='traces'?'tools':'kernel'};
 const canonicalSystemTab=['generate','records','audit'].includes(systemTab)?'generations':['policies','templates','generations','labels'].includes(systemTab)?systemTab:({generate:'generations',records:'generations',audit:'generations'}[u.searchParams.get('section')]||'policies');
 return {...sessions,...extra,systemTab:canonicalSystemTab,agentPolicyTab:agentPolicyTab==='runtime'?'runtime':'assistant',sessionTab:['syscalls','traces','events'].includes(sessionTab)?'events':['flow','audit'].includes(sessionTab)?sessionTab:'policies',sessionCursor,connectionsPane:'current',connectionHistory:'',agent:u.searchParams.get('agent')||'native-dsh',workspace:u.searchParams.get('workspace')||'',connectionAgent:u.searchParams.get('connectionAgent')||'',connectionWorkspace:u.searchParams.get('connectionWorkspace')||'',page:pages.includes(page)?page:'overview',historyModuleIndex:Math.max(0,historySections.indexOf(u.searchParams.get('section'))),task:u.searchParams.get('task')||'',workbenchSection:workbenchSections.includes(u.searchParams.get('stage'))?u.searchParams.get('stage'):(raw==='task'?'startup':'overview'),archiveTask:u.searchParams.get('archive')||'',archivePane:archivePanes.includes(u.searchParams.get('archivePane'))?u.searchParams.get('archivePane'):'startup',query:u.searchParams.get('q')||'',filter:u.searchParams.get('filter')||'history',listPage:Math.max(0,Number(u.searchParams.get('listPage'))||0)};
}
export function navigationTarget(href,patch){
 const u=new URL(href),n={...readNavigation(href),...patch};n.page=aliases[n.page]||n.page;
 if(!pages.includes(n.page))throw new RangeError('Unknown module');
 if(!historySections[n.historyModuleIndex])throw new RangeError('Unknown history section');
 if(Object.hasOwn(patch,'approvalId')&&patch.approvalId!==readNavigation(href).approvalId&&!Object.hasOwn(patch,'approvalRecordId'))n.approvalRecordId='';
 u.searchParams.set('view',n.page);u.searchParams.delete('sessionGeneration');
 const sessions=Object.fromEntries(['sessionAgent','sessionFilterInstance','sessionQuery','sessionInstance','sessionId','sessionWorkspace','connectionInstance','connectionTab','policyScope','policyWorkspace','policyAgent','policySession','approvalId','approvalRecordId','sessionTab','sessionCursor','systemTab','agentPolicyTab','configurationId','sessionEventKind'].map(k=>[k,n[k]||'']));
 for(const [key,value] of Object.entries({...sessions,connectionsPane:'',connectionHistory:'',agent:n.agent,workspace:n.workspace,connectionAgent:n.connectionAgent,connectionWorkspace:n.connectionWorkspace,task:n.task,stage:n.workbenchSection,archive:n.archiveTask,archivePane:n.archivePane,q:n.query,filter:n.filter,listPage:n.listPage||'',section:historySections[n.historyModuleIndex]})){if(value)u.searchParams.set(key,value);else u.searchParams.delete(key);}
 return u.pathname+u.search+u.hash;
}
