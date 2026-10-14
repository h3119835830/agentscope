#!/usr/bin/env python3
"""Owned 18186 API/Broker lifecycle acceptance; never changes production Agents."""
import argparse,json,os,pwd,socket,sqlite3,time,urllib.request,urllib.error,uuid
from pathlib import Path
import system_policy_acceptance_service as service
import deploy_policy_semantics as production

STATE=Path('/var/lib/aslife-flow-20261014')
SOURCE=Path('/opt/aslife-flow-20261014')
SOCKET='/run/aslife-flow-20261014/broker.sock'
PORT=18186
EVIDENCE=Path('/var/lib/agentscope-policy-lifecycle-20261014')
REPORT=EVIDENCE/'isolated-lifecycle-flow.json'

def configure():
    service.SOURCE=SOURCE;service.STATE=STATE;service.TASKS=Path('/p14f');service.RUNTIME=Path('/run/aslife-flow-20261014');service.PORT=PORT
    original=service.environment
    def environment():
        env=original();env['ACTPLANE_BPF_PIN_ROOT']='/sys/fs/bpf/aslife-flow-20261014';return env
    service.environment=environment

def api(path,body=None):
    req=urllib.request.Request(f'http://127.0.0.1:{PORT}'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=160) as response:return json.load(response)

def denied(path,body):
    try:api(path,body)
    except urllib.error.HTTPError as error:
        assert error.code==409,(error.code,error.read().decode());return True
    raise AssertionError('Expected conflict before any runtime mutation')

def broker(body):
    uid,gid=os.geteuid(),os.getegid();user=pwd.getpwnam('agentscope-api')
    try:
        os.setegid(user.pw_gid);os.seteuid(user.pw_uid)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(40);connection.connect(SOCKET);connection.sendall(json.dumps(body).encode()+b'\n');data=b''
            while not data.endswith(b'\n'):
                part=connection.recv(65536)
                if not part:raise RuntimeError('Broker closed the evidence connection')
                data+=part
    finally:os.seteuid(uid);os.setegid(gid)
    result=json.loads(data);assert result['ok'],result;return result['result']

def snapshot():
    return {'api':production.service(production.UNIT),'broker':production.service('agentscope-scope-demo-broker.service'),
            'authority':production.authority(),'listeners':production.listeners()}

def live(pid):
    try:return Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[0] not in ('Z','X')
    except FileNotFoundError:return False

def probe(row,effect='block'):
    return broker({'action':'agent-instance-dsl-probe','instance_id':row['id'],'generation':row['generation'],'effect':effect})['probe']

def propose(item,remove=False):
    base=api('/api/security/system/policy-library')
    return api('/api/security/system/policy-library/proposals',{'selections':[] if remove else [{'id':item['id'],'revision':item['revision']}],
        'removals':[item['id']] if remove else [],'base_hash':base['base_hash'],'base_revision':base['base_revision'],'request_key':uuid.uuid4().hex})

def approve(p):
    return api('/api/console/approvals/'+p['id']+'/approve',{'proposal_hash':p['proposal_hash'],'request_key':uuid.uuid4().hex})

def apply(p,receipt,key=None):
    return api('/api/console/approvals/'+p['id']+'/apply',{'proposal_hash':p['proposal_hash'],'approval_hash':receipt['approval_hash'],'request_key':key or uuid.uuid4().hex})

def confirm(p,hash_value=None):
    return api('/api/security/system/dsl/proposals/'+p['id']+'/confirm',{'proposal_hash':hash_value or p['proposal_hash']})

def main():
    assert os.geteuid()==0
    parser=argparse.ArgumentParser();parser.add_argument('--resume-protected-profile',action='store_true');args=parser.parse_args()
    configure()
    if args.resume_protected_profile:
        assert json.loads((STATE/'ownership.json').read_text())['task_root']=='/p14f'
        report=json.loads(REPORT.read_text());assert not report.get('passed')
        before=report['production_before'];assert snapshot()==before
        archive=REPORT.with_name('isolated-lifecycle-flow-incomplete.json');assert not archive.exists();archive.write_text(REPORT.read_text());archive.chmod(0o600)
        report['resumed_after']='Test harness approval URL corrected; no application failure'
    else:
        if STATE.exists():raise RuntimeError('Use a fresh owned lifecycle profile; this run is immutable')
        with socket.socket() as check:
            assert check.connect_ex(('127.0.0.1',PORT))!=0,'Isolated port is already owned'
        before=snapshot();report={'started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'production_before':before,'checks':{}}
    try:
        if args.resume_protected_profile:
            row=api('/api/agent-instances/'+report['instance_id']);assert row['generation']==report['protected_identity']['generation'] and row['active']
            item=next(i for i in api('/api/security/system/policy-library')['items'] if i['name']=='中文测试：保护验收依据');assert item['applied']
            path='/api/agent-instances/'+row['id']
        else:
            service.start('/var/lib/agentscope-scope-demo/bin/actplane.capabilities.json')
            resource=Path('/s/instance-resources/aslife-flow-20261014');assert not resource.exists();resource.mkdir(mode=0o755)
            for effect in ('block','notify'):
                p=resource/('.agentscope-dsl-'+effect+'.txt');p.write_text('synthetic lifecycle canary\n');p.chmod(0o644)
            row=api('/api/agent-instances',{'name':'策略生命周期中文测试','agent_type':'dsh','resources':[str(resource)],'mode':'controlled','environment':'wsl'})
            report['instance_id']=row['id'];path='/api/agent-instances/'+row['id']
            item=api('/api/security/system/policy-library',{'kind':'structured','base_revision':0,'config':{'name':'中文测试：保护验收依据','mode':'suffix','values':'.agentscope-dsl-block.txt','ops':['open'],'effect':'block','reason':'测试依据禁止读取，其他测试文件允许读取','template_id':''}})
            p=propose(item);assert p['state']=='pending'
            receipt=approve(p)
            assert not api('/api/security/system/dsl')['documents']
            assert not api(path)['active']
            assert apply(p,receipt)['resumed_count']==0
            report['checks']['approve_alone_does_not_apply']=True
            row=api(path+'/start',{});assert row['active'];report['protected_identity']={k:row.get(k) for k in ('id','pid','generation','domain_id','dsl_hash')}
        blocked=probe(row);allowed=probe(row,'notify');assert not blocked['outcome']['read_completed'] and allowed['outcome']['read_completed']
        events=[]
        for _ in range(30):
            events=broker({'action':'agent-instance-kernel-events','instance_id':row['id'],'generation':row['generation']})['events']
            events=[e for e in events if e['event'].get('pid')==blocked['pid'] and e['event'].get('blocked')]
            if events:break
            time.sleep(.2)
        assert events,'No matching kernel denial event'
        report.update(before_removal={'blocked_probe':blocked,'legal_probe':allowed,'kernel_events':events})
        report['checks']['active_configuration_cannot_be_archived']=denied('/api/security/system/policy-library/'+item['id']+'/archive',{'revision':item['revision']})
        removal=propose(item,True);assert removal['state']=='pending'
        view=api('/api/console/approvals/'+removal['id']);assert view['name']=='停用 中文测试：保护验收依据'
        report['checks']['named_removal_approval']=True
        stale=propose(item,True)
        report['checks']['wrong_confirmation_rejected']=denied('/api/security/system/dsl/proposals/'+removal['id']+'/confirm',{'proposal_hash':'0'*64})
        pending=probe(row);assert not pending['outcome']['read_completed'] and api(path)['generation']==row['generation']
        report['while_pending']=pending
        receipt=approve(removal)
        approved=probe(row);assert not approved['outcome']['read_completed'] and api(path)['generation']==row['generation']
        report['approved_not_applied']=approved;report['checks']['approved_removal_keeps_protection']=True
        key=uuid.uuid4().hex;result=apply(removal,receipt,key);assert result['state']=='applied' and result['resumed_count']==1
        after=api(path);assert after['active'] and after['generation']!=row['generation'] and not live(row['pid'])
        unblocked=probe(after);assert unblocked['outcome']['read_completed']
        report['after_removal']={'application':result,'probe':unblocked,'identity':{k:after.get(k) for k in ('id','pid','generation','domain_id','dsl_hash')}}
        report['checks']['old_candidate_rejected']=denied('/api/security/system/dsl/proposals/'+stale['id']+'/confirm',{'proposal_hash':stale['proposal_hash']})
        assert apply(removal,receipt,key)['idempotent'];report['checks']['application_retry_idempotent']=True
        report['checks']['stale_stop_rejected']=denied(path+'/stop',{k:row[k] for k in ('generation','policy_hash')})
        assert live(after['pid']) and api(path)['generation']==after['generation']
        archived=api('/api/security/system/policy-library/'+item['id']+'/archive',{'revision':item['revision']})
        with sqlite3.connect(STATE/'demo.sqlite3') as con:
            assert con.execute('SELECT archived FROM system_policy_library WHERE id=?',(item['id'],)).fetchone()[0]
            assert con.execute('SELECT COUNT(*) FROM system_policy_library_versions WHERE id=?',(item['id'],)).fetchone()[0]>0
        report['checks']['inactive_delete_retains_history']=True
        api(path+'/stop',{k:after[k] for k in ('generation','policy_hash')})
        time.sleep(2);closed=api(path)
        assert closed['gate']=='closed' and not closed['active'] and not live(after['pid'])
        assert broker({'action':'agent-instance-observe','instance_id':row['id']})['connected'] is False
        report['checks']['stop_terminates_and_does_not_restart']=True
        report['closed_identity']={k:closed.get(k) for k in ('id','pid','generation','gate','active')}
        report['production_after']=snapshot();report['checks']['production_unchanged']=report['production_after']==before
        assert report['checks']['production_unchanged']
        report['passed']=True
    finally:
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2));REPORT.chmod(0o600)
        print(json.dumps({'passed':report.get('passed',False),'report':str(REPORT),'checks':report['checks']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
