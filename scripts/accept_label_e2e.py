"""Isolated API/Broker/DSH/kernel acceptance, no model calls or deployed edits.

The test-only DSH wrapper invokes one fixed registered tool through the native
tool registry. It does not modify the product plugin or expose an execution API
in the product. The isolated model hostname is loopback; the independent
receiver listens on the existing model_only HTTPS port. No firewall is widened.
"""
import argparse,http.client,json,os,pwd,secrets,shutil,signal,socket,subprocess,sys,tempfile,threading,time,urllib.request,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PYTHON='/opt/agentscope/.venv/bin/python'

WRAPPER=r'''
import http from 'node:http';
import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {defineTool} from '@deepseek-ai/dsh-tools';
import {apply as original} from './product.js';
export {name,inject} from './product.js';
export function apply(ctx){
 original(ctx);
 ctx.tools.register(defineTool({name:'accept_label_flow_probe',description:'Fixed synthetic acceptance workload',parameters:{},
 output:{schema:{type:'string'},render:(_a,v)=>[{type:'text',text:v}]},
 execute:()=>new Promise((resolve,reject)=>{
  const p=spawn('/usr/bin/python3',['/w/0/probe.py','workload','/w/0','443']);
  let stdout='',stderr='';p.stdout.on('data',c=>stdout+=c);p.stderr.on('data',c=>stderr+=c);
  p.on('error',reject);p.on('close',code=>code===0?resolve(stdout):reject(Error('Probe exit '+code+': '+stderr)));
 })}));
 const server=http.createServer(async(req,res)=>{
  try{
   let body='';for await(const c of req){body+=c;if(body.length>1000)throw Error('bounded test request');}
   const data=JSON.parse(body),found=await ctx.sessionController.resolveAgent(data.session_id);
   if(found.error)throw found.error;
   const result=await ctx.tools.execute({agent:found.agent,name:'accept_label_flow_probe',arguments:{},callId:randomUUID(),signal:AbortSignal.timeout(30000)});
   res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result));
  }catch(e){res.writeHead(409);res.end(JSON.stringify({error:e.message}));}
 });
 server.listen(process.env.DSH_HOME+'/acceptance.sock');
 ctx.on('dispose',()=>server.close());
}
'''


def broker(state):
    sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/broker')]
    import main as b
    import instance_runtime
    b.REPO_ROOT=state/'facade'
    # Test-only provider resolution. The actual cgroup allowlist still allows
    # model IP:443 only, and the receiver is outside the controlled cgroup.
    instance_runtime.model_hosts=lambda _:['127.0.0.1']
    b.main()


def refresh(state):
    """Restart only the identity-checked isolated API; leave its Agent running."""
    assert os.geteuid()==0 and state.resolve().parent==Path('/var/tmp') and state.name.startswith('lf-')
    record=json.loads((state/'acceptance.json').read_text());assert record['state']==str(state)
    for item in record['processes']:
        p=Path('/proc')/str(item['pid'])
        if not p.exists():continue
        assert p.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19]==item['start_ticks']
        command=p.joinpath('cmdline').read_bytes().split(b'\0')
        if b'uvicorn' not in command:continue
        assert b'18173' in command and p.joinpath('cwd').resolve()==ROOT
        env=dict(v.split('=',1) for v in p.joinpath('environ').read_bytes().decode().split('\0') if '=' in v)
        assert env['AGENTSCOPE_STATE_DIR']==str(state/'api')
        os.kill(item['pid'],signal.SIGTERM)
        for _ in range(100):
            if not p.exists():break
            time.sleep(.1)
        owner=pwd.getpwnam('happy')
        def demote():os.setgroups([]);os.setgid(owner.pw_gid);os.setuid(owner.pw_uid)
        process=subprocess.Popen([PYTHON,'-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port','18173'],
            cwd=ROOT,env=env,preexec_fn=demote,start_new_session=True,stdout=(state/'api.log').open('a'),stderr=subprocess.STDOUT)
        item.update(pid=process.pid,start_ticks=Path('/proc',str(process.pid),'stat').read_text().rsplit(') ',1)[1].split()[19])
        (state/'acceptance.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
        print('Isolated API restarted; Agent and Broker unchanged.')
        return
    raise ValueError('No matching isolated API')


def cleanup(state):
    """Stop only the acceptance services whose saved PID birth identity matches."""
    assert os.geteuid()==0 and state.resolve().parent==Path('/var/tmp') and state.name.startswith('lf-')
    record=json.loads((state/'acceptance.json').read_text())
    assert record['state']==str(state) and not record.get('production_changed')
    live=[]
    for item in record['processes']:
        process=Path('/proc')/str(item['pid'])
        if not process.exists():continue
        assert process.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19]==item['start_ticks']
        assert process.joinpath('cwd').resolve()==ROOT
        env=dict(v.split('=',1) for v in process.joinpath('environ').read_bytes().decode().split('\0') if '=' in v)
        assert env['AGENTSCOPE_STATE_DIR']==str(state/'api')
        live.append(item['pid'])
    if live and record.get('agent_id'):
        request=urllib.request.Request('http://127.0.0.1:18173/api/agent-instances/'+record['agent_id']+'/stop',
                                       data=b'{}',headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=30) as response:
            result=json.load(response)
        assert not result.get('active'),result
    for pid in reversed(live):
        os.kill(pid,signal.SIGTERM)
        for _ in range(100):
            process=Path('/proc')/str(pid)
            if not process.exists() or process.joinpath('stat').read_text().rsplit(') ',1)[1].split()[0]=='Z':
                break
            time.sleep(.1)
        else:raise RuntimeError('Isolated service did not stop; no forced cleanup')
    record['preview_stopped']=True
    (state/'acceptance.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print('Isolated Agent, API and Broker stopped; evidence preserved.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--keep-preview',action='store_true')
    args=parser.parse_args()
    assert os.geteuid()==0
    for port in (18173,443):
        with socket.socket() as check:
            check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);check.bind(('127.0.0.1',port))
    state=Path(tempfile.mkdtemp(prefix='lf-',dir='/var/tmp'));state.chmod(0o755)
    owner=pwd.getpwnam('happy')
    api_state=state/'api';api_state.mkdir();os.chown(api_state,owner.pw_uid,owner.pw_gid)
    resource=Path(tempfile.mkdtemp(prefix='lf-resource-',dir='/home/happy/projects'))
    resource.chmod(0o755);os.chown(resource,owner.pw_uid,owner.pw_gid)
    for name,text in [('secret.txt','SYNTHETIC_SECRET_NOT_A_CREDENTIAL'),('public.txt','PUBLIC')]:
        p=resource/name;p.write_text(text);os.chown(p,owner.pw_uid,owner.pw_gid)
    shutil.copyfile(ROOT/'scripts/accept_label_flow.py',resource/'probe.py')
    profile=state/'empty-dsh';profile.mkdir();(profile/'.credentials.yaml').write_text('version: 1\nrefs: {}\nrecords: {}\n')
    facade=state/'facade';(facade/'integrations').mkdir(parents=True)
    (facade/'backend').symlink_to(ROOT/'backend',target_is_directory=True)
    shutil.copytree(ROOT/'integrations/dsh-managed-web',facade/'integrations/dsh-managed-web')
    plugin=facade/'integrations/dsh-instance-runtime';shutil.copytree(ROOT/'integrations/dsh-instance-runtime',plugin)
    (plugin/'lib/index.js').rename(plugin/'lib/product.js');(plugin/'lib/index.js').write_text(WRAPPER)
    base='http://127.0.0.1:18173'
    env={k:v for k,v in os.environ.items() if not k.startswith(('AGENTSCOPE_','ACTPLANE_','DSH_'))}
    env.update(AGENTSCOPE_STATE_DIR=str(api_state),AGENTSCOPE_TASK_ROOT=str(state/'tasks'),
        AGENTSCOPE_POLICY_DIR=str(state/'policies'),AGENTSCOPE_RUNTIME_DIR=str(state/'run'),
        AGENTSCOPE_LOG_DIR=str(state/'logs'),AGENTSCOPE_BROKER_SOCKET=str(state/'run/broker.sock'),
        AGENTSCOPE_DSH_HOME=str(profile),AGENTSCOPE_APP_USER='happy',AGENTSCOPE_AGENT_USER='happy',
        AGENTSCOPE_TASK_GROUP='agentscope-task',AGENTSCOPE_CONTROL_GROUP='happy',AGENTSCOPE_CONTROLLED_INSTANCE_PROFILE='isolated-acceptance',
        ACTPLANE_BIN=str(ROOT/'actplane/target/release/actplane'),ACTPLANE_BPF_PIN_ROOT='/sys/fs/bpf/'+state.name,
        DSH_BIN='/opt/agentscope/dsh/node_modules/.bin/dsh',AGENTSCOPE_EXEC_PATH='/opt/agentscope/bin:/usr/local/bin:/usr/bin:/bin',
        AGENTSCOPE_PUBLIC_URL=base,AGENTSCOPE_UI_DIST=str(ROOT/'frontend/dist'),AGENTSCOPE_DEV_NO_AUTH='1',
        AGENTSCOPE_ADMIN_TOKEN=secrets.token_urlsafe(32),AGENTSCOPE_INSTANCE_WORKER='1',
        AGENTSCOPE_SCOPE_WORKER='0',AGENTSCOPE_HISTORY_WORKER='0',PYTHONPATH=str(ROOT/'backend'))
    # API-created directories are separate from root-owned runtime/policies.
    for name in ('tasks','policies','logs'):
        p=state/name;p.mkdir();os.chown(p,owner.pw_uid,owner.pw_gid)
    processes=[]
    def launch(command,log,api=False):
        def demote():os.setgroups([]);os.setgid(owner.pw_gid);os.setuid(owner.pw_uid)
        p=subprocess.Popen(command,cwd=ROOT,env=env,stdout=(state/log).open('w'),stderr=subprocess.STDOUT,
                           start_new_session=True,preexec_fn=demote if api else None)
        processes.append(p);return p
    def call(path,body=None):
        request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                                       headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=120) as response:return json.load(response)
        except urllib.error.HTTPError as e:raise RuntimeError(path+': '+e.read().decode()) from None
    def approve(ident):
        record=call('/api/console/approvals/'+ident)
        approval=call('/api/console/approvals/'+ident+'/approve',{'proposal_hash':record['candidate_hash'],'request_key':uuid.uuid4().hex})
        assert call('/api/console/approvals/'+ident)['status']=='approved'
        return call('/api/console/approvals/'+ident+'/apply',{'proposal_hash':record['candidate_hash'],'approval_hash':approval['approval_hash'],'request_key':uuid.uuid4().hex})
    receiver=socket.socket();receiver.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);receiver.bind(('127.0.0.1',443));receiver.listen();receiver.settimeout(.2)
    received=[];done=threading.Event()
    def receive():
        while not done.is_set():
            try:
                connection,_=receiver.accept()
                with connection:
                    connection.settimeout(2);received.append(connection.recv(4096))
            except socket.timeout:pass
            except OSError:break
    thread=threading.Thread(target=receive,daemon=True);thread.start()
    report={'state':str(state),'resource':str(resource),'production_changed':False,'model_requests':0,'native_test_tool':True,
            'provider_test_resolution':'127.0.0.1:443','checks':[]}
    success=False;agent=None
    try:
        launch([PYTHON,__file__,'broker',str(state)],'broker.log')
        launch([PYTHON,'-m','uvicorn','agentscope_app.main:app','--host','127.0.0.1','--port','18173'],'api.log',True)
        for _ in range(80):
            try:
                if call('/api/health')['ok']:break
            except Exception:time.sleep(.2)
        else:raise RuntimeError('isolated API not ready')
        agent=call('/api/agent-instances',{'name':'标签信息流隔离验收','agent_type':'dsh','resources':[str(resource)],'mode':'controlled','environment':'wsl'})
        ident=agent['id'];report['agent_id']=ident
        p=call('/api/agent-instances/'+ident+'/policy/proposals',{'policy':{'network':'model_only','rules':[{'action':'write','effect':'allow','target':str(resource),'text':'仅合成验收目录可写'}]},'base_hash':agent['policy_hash'],'request_key':uuid.uuid4().hex})
        approve('instance:'+p['id'])
        catalogue=call('/api/policy-templates?scope_id='+ident)['catalog']
        template=next(t for t in catalogue if t['id']=='SECRET-EGRESS')
        saved=call('/api/policy-template-configurations',{'scope_id':ident,'scope':'agent','workspace_id':None,
            'template_id':template['id'],'template_version':template['version'],'name':'合成秘密禁止外发',
            'reason':'合成验收：读取来源后禁止新 IPv4 连接','parameters':{'target':'/w/0/secret.txt','endpoint':'127.0.0.1'},
            'base_revision':0,'request_key':uuid.uuid4().hex})
        report['configuration_id']=saved['id'];report['source_refs']=saved['label_source_refs']
        assert not call('/api/agent-instances/'+ident+'/dsl')['documents']
        # Native provenance reports the first available *matched* label. The
        # production template also matches AGENT, so this isolated provenance
        # acceptance uses the same frozen SECRET source but a SECRET-only rule.
        # It remains a normal manually approved DSL candidate.
        current=call('/api/agent-instances/'+ident+'/dsl')
        document=dict(saved['document'])
        assert 'if AGENT and SECRET' in document['original_dsl']
        document['original_dsl']=document['original_dsl'].replace('if AGENT and SECRET','if SECRET')
        p=call('/api/agent-instances/'+ident+'/dsl/proposals',
               {'documents':[document],'base_hash':current['document_hash'],'base_revision':current['revision'],
                'request_key':uuid.uuid4().hex})
        report['approval_id']=p['id'];approve(p['id'])
        report['checks'].append('source registration, explicit frozen source, separate approval and application, SECRET-only provenance fixture')
        active=call('/api/agent-instances/'+ident+'/start',{})
        assert active['active'],active.get('security')
        report['generation']=active['generation']
        created=call('/api/agent-instances/'+ident+'/sessions',{'resource':str(resource)})
        session_id=created.get('sessionId') or created.get('session_id') or created.get('id')
        if not session_id:
            sessions=call('/api/agent-instances/'+ident+'/sessions')['sessions'];session_id=sessions[0]['id']
        report['session_id']=session_id
        connection=http.client.HTTPConnection('localhost',timeout=60)
        sock=socket.socket(socket.AF_UNIX);sock.connect(str(state/'tasks/instances'/ident/'state/.dsh/acceptance.sock'))
        connection.sock=sock
        connection.request('POST','/',json.dumps({'session_id':session_id}),{'Content-Type':'application/json'})
        response=connection.getresponse();result=json.loads(response.read());connection.close()
        report['tool_result']=result;assert response.status==200 and not result.get('isError'),result
        root='/api/agent-instances/'+ident+'/sessions/'+session_id
        data=None
        for _ in range(30):
            data=call(root+'/information-flow?view=shared_domain&label=SECRET')
            if data['state']=='available':break
            time.sleep(.3)
        report['flow']=data
        assert data['state']=='available',data
        assert any(r['labels']==['SECRET'] and r['provenance_state']=='reported_first_origin'
                   and r['provenance']['origin_target'].endswith('/secret.txt')
                   and r['match']['operation']=='connect' and r['match']['target']=='127.0.0.1'
                   and r['match']['actual_action']=='block' for r in data['records']),data
        assert received==[b'public-control'],{'receiver_connections':len(received)}
        report['receiver_public_only']=True
        report['current_session_flow']=call(root+'/information-flow?view=session&label=SECRET')
        report['checks'].append('real native tool, kernel propagation, native single-hop provenance, root audit, broker collection and evidence API')
        report.update(passed=True,preview_url=base+'/?view=sessions&sessionInstance='+ident+'&sessionId='+session_id+'&sessionTab=flow')
        success=True
    except Exception as error:
        report.update(passed=False,error=str(error));raise
    finally:
        done.set();receiver.close();thread.join(3)
        report['processes']=[{'pid':p.pid,'start_ticks':Path('/proc',str(p.pid),'stat').read_text().rsplit(') ',1)[1].split()[19]} for p in processes if p.poll() is None]
        (state/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({k:report[k] for k in ('passed','state','error','agent_id','session_id','preview_url') if k in report},ensure_ascii=False),flush=True)
        if not(success and args.keep_preview):
            if agent:
                try:call('/api/agent-instances/'+agent['id']+'/stop',{})
                except Exception:pass
            for p in reversed(processes):
                if p.poll() is None:p.terminate();p.wait(timeout=20)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='broker':broker(Path(sys.argv[2]))
    elif len(sys.argv)>1 and sys.argv[1]=='refresh':refresh(Path(sys.argv[2]))
    elif len(sys.argv)>1 and sys.argv[1]=='cleanup':cleanup(Path(sys.argv[2]))
    else:main()
