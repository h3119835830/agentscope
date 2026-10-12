#!/usr/bin/env python3
"""Isolated two-instance and held-FD/mmap revocation; never live production."""
import hashlib,json,os,time,uuid
from pathlib import Path
from accept_execution_independence import api,broker,STATE,identity
from accept_value_dsh import BASE,IDENT,post

def main():
 assert os.getuid()==0
 # A fresh domain also removes any held probes from an interrupted lab run.
 post('/stop',{});a=post('/start',{});assert a['active']
 other=BASE.parent/'asvalue-other-20261012';(other/'README.md').write_text('Independent synthetic resource B.\n')
 rows=api('/api/agent-instances')['instances']
 b=next((r for r in rows if r['resources']==[str(other)]),None)
 if b is None:b=api('/api/agent-instances',{'name':'Value isolated sibling','agent_type':'dsh','resources':[str(other)],'mode':'controlled','environment':'wsl'})
 bid=b['id']
 if not b.get('active'):b=api('/api/agent-instances/'+bid+'/start',{})
 assert b['active'] and b['pid']!=a['pid'] and b['domain_id']!=a['domain_id']
 before_b={k:b[k] for k in ('pid','generation','policy_hash','domain_id')}
 held_file=BASE/'.agentscope-held-handle-probe';held_file.write_text('Synthetic held-FD and mmap canary.\n');held_file.chmod(0o666)
 initial=hashlib.sha256(held_file.read_bytes()).hexdigest()
 held=broker('handle-probe',IDENT,target=str(held_file))['hold']
 assert held['fd'] and held['writable_mapping']
 old=api('/api/agent-instances/'+IDENT+'/policy');policy=old['policy']
 policy['rules'].append({'action':'write','target':str(held_file),'effect':'deny','text':'Synthetic permission revocation'})
 change=post('/policy/proposals',{'generation':old['generation'],'base_hash':old['policy_hash'],'request_key':'revoke-'+uuid.uuid4().hex,'policy':policy})
 if change['state']=='pending':change=post('/policy/proposals/'+change['id']+'/confirm',{'proposal_hash':change['proposal_hash']})
 assert change['state']=='applied'
 current=api('/api/agent-instances/'+IDENT);assert current['active'] and current['generation']!=a['generation']
 def dead(pid):
  try:return identity(pid)['state'] in ('Z','X')
  except FileNotFoundError:return True
 assert dead(held['pid']) and dead(held['child_pid']) and held_file.exists()
 assert hashlib.sha256(held_file.read_bytes()).hexdigest()==initial
 sibling=api('/api/agent-instances/'+bid+'/check',{})
 assert sibling['active'] and {k:sibling[k] for k in before_b}==before_b
 report={'schema':'agentscope.value-revocation.v1','verified_at':time.time(),'instance_a':IDENT,'instance_b':bid,'old_generation':a['generation'],'new_generation':current['generation'],'held_handles':held,'old_holder_and_child_terminated':True,'canary_unchanged':True,'sibling_unchanged':before_b,'passed':True,
 'limit':'Platform revocation by generation replacement, not in-place mmap revocation. Different cgroups/domains and unmounted resources do not prove native sessions are individually isolated.'}
 (STATE/'value-revocation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report))
 api('/api/agent-instances/'+bid+'/stop',{})

if __name__=='__main__':main()
