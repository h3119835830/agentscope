#!/usr/bin/env python3
"""Real isolated policy-worker deadline and recovery acceptance; no provider streams."""
import argparse,json,os,signal,sqlite3,time
from pathlib import Path
from managed_control import api
from managed_acceptance import wait,probe
STATE=Path('/var/lib/agentscope-scope-demo')
def live(pid):
    try:return Path('/proc/'+str(pid)+'/stat').read_text().split(') ',1)[1].split()[0] not in ('Z','X')
    except FileNotFoundError:return False

def run(after=None,keep_open=False):
    if after:
        deadline=time.monotonic()+1800
        while time.monotonic()<deadline:
            with sqlite3.connect(STATE/'demo.sqlite3') as con:
                row=con.execute('select state_json from managed_tasks where task_id=?',(after,)).fetchone()
            if row and json.loads(row[0])['phase']=='ended':break
            time.sleep(3)
        else:raise TimeoutError('main acceptance did not finish; fault test postponed')
    task=api('/api/managed/scenarios/safety-delete-config/tasks',{})['id']
    proof={'schema':'ManagedPiTimeoutAcceptance/1','task_id':task,'fault':'SIGSTOP isolated Pi process group; no credential or model stream captured'}
    print(json.dumps({'stage':'starting_timeout_fixture','task_id':task}),flush=True)
    api('/api/managed/tasks/'+task+'/start',{});x,n=wait(task)
    state=x['state'];sid=state['session_id'];baseline=state['baseline_hash'];version=state['version'];native_pid=x['execution']['executor']['pid']
    job=api('/api/managed/tasks/'+task+'/changes',{'text':'只读汇报现行范围，保留全部当前约束，不请求新权限。','request_key':'deadline-fault-check'})['id']
    end=time.monotonic()+45;pid=None
    while time.monotonic()<end:
        for entry in Path('/proc').iterdir():
            if not entry.name.isdecimal():continue
            try:args=(entry/'cmdline').read_bytes().split(b'\x00')
            except (FileNotFoundError,PermissionError,ProcessLookupError):continue
            if args and args[0].endswith(b'/bwrap') and any(job.encode()+b'-' in a for a in args) and os.getpgid(int(entry.name))==int(entry.name):
                pid=int(entry.name);break
        if pid:break
        time.sleep(.1)
    if not pid:raise AssertionError('running isolated Pi process group was not observed')
    os.killpg(pid,signal.SIGSTOP);start=time.monotonic()
    print(json.dumps({'stage':'real_pi_group_stopped','task_id':task,'pi_pid':pid,'deadline_seconds':180}),flush=True)
    end=start+215
    while time.monotonic()<end:
        x=api('/api/managed/tasks/'+task);state=x['state']
        if state['phase']=='failed':break
        time.sleep(1)
    assert state['phase']=='failed' and state['gate']=='failed' and 'bounded analysis deadline' in state['error'],state.get('error')
    assert state['version']==version and state['baseline_hash']==baseline and not live(native_pid) and not live(pid)
    proof.update(deadline_verified=True,elapsed_seconds=round(time.monotonic()-start,2),failed_closed=True,error=state['error'],policy_version_unchanged=version,baseline_hash=baseline,session_id=sid,old_native_pid=native_pid,pi_pid=pid,process_groups_stopped=True)
    api('/api/managed/tasks/'+task+'/start',{});x,n=wait(task)
    assert x['state']['session_id']==sid and x['state']['baseline_hash']==baseline
    target=x['state']['protected'][0];result=probe(task,target,'write','deny')
    assert result['classification']=='correct_block'
    proof.update(recovered_same_session=True,recovered_same_baseline=True,new_native_pid=x['execution']['executor']['pid'],new_domain=x['state']['binding']['domain_id'],recovery_kernel_probe='correct_block',keep_open=keep_open)
    if not keep_open:proof['closure']=api('/api/managed/tasks/'+task+'/close',{})
    out=STATE/'report/pi-timeout-recovery.json';out.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'stage':'timeout_recovery_passed','task_id':task,'elapsed_seconds':proof['elapsed_seconds'],'same_session':True,'baseline_retained':True,'keep_open':keep_open}),flush=True)
    return proof
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--after');p.add_argument('--keep-open',action='store_true');a=p.parse_args();run(a.after,a.keep_open)
