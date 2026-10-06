import {randomUUID} from 'node:crypto';
import {dirname} from 'node:path';
// Fixed independent acceptance surface. No caller-selected command or host read.
export async function verifyTaskSandbox(ctx,agent,workspace,signal) {
 const root=dirname(workspace),report=workspace+'/.task-sandbox-proof.json';
 const python=String.raw`import os,socket,json,sys
r={}
paths=['/opt/agentscope-history-v1','/opt/agentscope/actplane','/var/lib/agentscope-scope-demo','/run/agentscope-scope-demo','/root',ROOT+'/.dsh',ROOT+'/.runtime-control',ROOT+'/.sandbox-root',ROOT+'/.public-runtime']
r['hidden_host_paths']=all(not os.path.exists(p) for p in paths)
r['no_control_environment']=not any(k.startswith(('AGENTSCOPE_','ACTPLANE_','DSH_')) for k in os.environ)
r['private_process_namespace']=len([p for p in os.listdir('/proc') if p.isdigit()])<=4
s=socket.socket();s.settimeout(.2)
try:s.connect(('127.0.0.1',18003));r['private_network_namespace']=False
except OSError:r['private_network_namespace']=True
try:
 fd=os.open(WORKSPACE+'/.bashrc',os.O_WRONLY);os.close(fd);r['protected_open_denied']=False
except PermissionError:r['protected_open_denied']=True
import pytest
r['public_python_dependencies']=True
open(WORKSPACE+'/.task-legal-write.txt','w').write('legal task output in workspace\n')
r['legal_workspace_write']=open(WORKSPACE+'/.task-legal-write.txt').read()=='legal task output in workspace\n'
open(REPORT,'w').write(json.dumps(r))
print('TASK_SANDBOX_PROBE_COMPLETED')
`;
 const program='ROOT='+JSON.stringify(root)+'\nWORKSPACE='+JSON.stringify(workspace)+'\nREPORT='+JSON.stringify(report)+'\n'+python;
 const quote=v=>"'"+v.replaceAll("'","'\\''")+"'";
 const calls=[];
 for(const [name,args] of [
  ['read',{file_path:root+'/.public-runtime/control-canary.txt'}],
  ['read',{file_path:workspace+'/project_a/main.py'}],
  ['grep',{pattern:'def',path:workspace+'/project_a/main.py'}],
  ['bash',{command:'/opt/task-python/bin/python -c '+quote(program),description:'Fixed task sandbox acceptance probe',workdir:workspace}]
 ]) {
  const callId='managed-verification:'+randomUUID();
  const value=await ctx.tools.execute({callId,name,arguments:args,agent,signal});
  for(const message of value.additionalContexts||[])agent.followup(message);
  await ctx.parallel('session/flush',agent.session);
  calls.push({call_id:callId,name,is_error:!!value.isError,error_code:value.error?.code});
 }
 return {report_path:report,calls,source:'native_sdk_fixed_probe',attempted_by_agent:false};
}
