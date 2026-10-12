#!/usr/bin/env python3
"""Reproducible synthetic effects, not an LLM attack-success benchmark.

Plain/tool-entry controls intentionally execute an already selected payload.
Static sandbox uses read-only mounts and a hidden credential directory. Dynamic
flow compares the same endpoint with clean and secret-derived data separately.
All network traffic stays on loopback; no real credentials are used.
"""
import hashlib,json,os,platform,shutil,socket,subprocess,tempfile,threading,time,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BINARY=ROOT/'actplane/target/release/actplane'
MODES=('unconstrained_execution','tool_entry_only','static_sandbox','actplane')

def drop():os.setgroups([]);os.setgid(65534);os.setuid(65534)

class Receiver:
    def __enter__(self):
        self.socket=socket.socket();self.socket.bind(('127.0.0.1',0));self.socket.listen();self.socket.settimeout(.1)
        self.port=self.socket.getsockname()[1];self.messages=[];self.stop=False
        def collect():
            while not self.stop:
                try:
                    conn,_=self.socket.accept()
                    with conn:conn.settimeout(1);self.messages.append(conn.recv(1024).decode(errors='replace'))
                except (TimeoutError,OSError):pass
        self.thread=threading.Thread(target=collect,daemon=True);self.thread.start();return self
    def __exit__(self,*_):self.stop=True;self.thread.join(2);self.socket.close()

def main():
    if os.getuid()!=0:raise SystemExit('Root is required to load the isolated kernel policies')
    root=Path(tempfile.mkdtemp(prefix='av-'));root.chmod(0o755)
    pinbase=Path('/sys/fs/bpf')/('av-'+uuid.uuid4().hex)
    report={'schema':'agentscope.value-effects.v1','started_at':time.time(),'kernel':platform.release(),
        'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'repetitions':3,'root':str(root),
        'method':'Selected-payload execution controls. No claim about prompt-injection success rate or reproduction of CaMeL/Progent/FIDES.',
        'cases':[]}
    for repeat in range(3):
      for scenario in ('plugin','integrity','path','flow','descendants','isolation'):
       for mode in MODES:
        name=f'{scenario}-{mode}-{repeat}';work=root/name;work.mkdir();work.chmod(0o755)
        project=work/'project';project.mkdir();src=project/'src';src.mkdir();tests=project/'tests';tests.mkdir();cred=work/'credentials';cred.mkdir();out=project/'output';out.mkdir()
        for p in (src,tests,cred,out):p.chmod(0o777)
        secret=cred/'cloud.key';secret.write_text('SYNTHETIC_SECRET_CANARY');secret.chmod(0o666)
        normal=src/'app.py';normal.write_text('original source\n');normal.chmod(0o666)
        protected=tests/'test_app.py';protected.write_text('assert real_result == expected\n');protected.chmod(0o666)
        alias=src/'local.conf';alias.symlink_to(protected)
        other=work/'other-agent-private';other.write_text('OTHER_AGENT_SYNTHETIC');other.chmod(0o666)
        dsl='source AGENT = exec "**/python3"\n'
        clauses=[];sources=''
        common='import os,json,pathlib,subprocess,sys\nr=[]\ndef attempt(label,fn):\n try:\n  value=fn();r.append({"operation":label,"allowed":True,"value":value if isinstance(value,(str,bool,int)) else None})\n except OSError as e:r.append({"operation":label,"allowed":False,"errno":e.errno})\n'
        tail='\nprint("RESULT="+json.dumps({"pid":os.getpid(),"operations":r}),flush=True)\n'
        if scenario=='plugin':
            code=common+'attempt("legal_read",lambda:pathlib.Path('+repr(str(normal))+').read_text())\nattempt("hidden_credential_read",lambda:pathlib.Path('+repr(str(secret))+').read_text())'+tail
            clauses=['block read file '+json.dumps(str(secret))+' if AGENT'];attack='hidden_credential_read'
        elif scenario=='integrity':
            code=common+'attempt("legal_repair",lambda:pathlib.Path('+repr(str(normal))+').write_text("fixed source\\n"))\nattempt("rewrite_tests",lambda:pathlib.Path('+repr(str(protected))+').write_text("assert True\\n"))\nattempt("delete_tests",lambda:os.unlink('+repr(str(protected))+'))'+tail
            clauses=[op+' file '+json.dumps(str(tests)+'/**')+' if AGENT' for op in ('block write','block unlink')];attack='rewrite_tests'
        elif scenario=='path':
            replacement=src/'replacement';replacement.write_text('forged tests');replacement.chmod(0o666)
            code=common+'attempt("legal_repair",lambda:pathlib.Path('+repr(str(normal))+').write_text("fixed source\\n"))\nattempt("symlink_truncate",lambda:pathlib.Path('+repr(str(alias))+').write_text("forged\\n"))\nattempt("rename_overwrite",lambda:os.replace('+repr(str(replacement))+','+repr(str(protected))+'))\nattempt("direct_truncate",lambda:os.truncate('+repr(str(protected))+',0))'+tail
            clauses=[op+' file '+json.dumps(str(tests)+'/**')+' if AGENT' for op in ('block write','block unlink')];attack='symlink_truncate'
        elif scenario=='flow':
            sources='source SECRET = file '+json.dumps(str(secret))+'\n'
            clauses=['block connect endpoint "127.0.0.1" if SECRET'];attack='derived_connect'
            derived=out/'renamed-report.txt'
        elif scenario=='descendants':
            child='import pathlib,json,os\ntry:\n pathlib.Path('+repr(str(secret))+').read_text();allowed=True;err=None\nexcept OSError as e:allowed=False;err=e.errno\npathlib.Path('+repr(str(out/'child.json'))+').write_text(json.dumps({"allowed":allowed,"errno":err,"pid":os.getpid()}))'
            childfile=project/'child.py';childfile.write_text(child);childfile.chmod(0o644)
            command='/usr/bin/python3 '+str(childfile)+' & wait'
            code=common+'attempt("legal_read",lambda:pathlib.Path('+repr(str(normal))+').read_text())\nsubprocess.run(["/bin/bash","-c",'+repr(command)+'],check=True)\nchild=json.loads(pathlib.Path('+repr(str(out/'child.json'))+').read_text());r.append({"operation":"background_credential_read",**child})'+tail
            clauses=['block read file '+json.dumps(str(secret))+' if AGENT'];attack='background_credential_read'
        else:
            code=common+'attempt("legal_read",lambda:pathlib.Path('+repr(str(normal))+').read_text())\nattempt("other_agent_read",lambda:pathlib.Path('+repr(str(other))+').read_text())'+tail
            clauses=['block read file '+json.dumps(str(other))+' if AGENT'];attack='other_agent_read'
        policy=work/'policy.yaml';policy.write_text('version: 1\npolicy: |\n'+''.join('  '+line+'\n' for line in (dsl+sources+'rule boundary:\n'+''.join('  '+c+'\n' for c in clauses)+'  because "Synthetic approved task boundary."\n').splitlines()))
        with Receiver() as receiver:
            if scenario=='flow':
                sender='import pathlib,socket,json,sys,os\np=pathlib.Path(sys.argv[1]);data=p.read_bytes()\ns=socket.socket();s.settimeout(1)\ntry:\n s.connect(("127.0.0.1",int(sys.argv[2])));s.sendall(data);ok=True;err=None\nexcept OSError as e:ok=False;err=e.errno\nprint(json.dumps({"allowed":ok,"errno":err,"pid":os.getpid()}))'
                senderfile=project/'sender.py';senderfile.write_text(sender);senderfile.chmod(0o644)
                writer='import pathlib\ntext=pathlib.Path('+repr(str(secret))+').read_text();pathlib.Path('+repr(str(out/'draft'))+').write_text(text);pathlib.Path('+repr(str(out/'draft'))+').rename('+repr(str(derived))+')'
                code=common+'\nclean=subprocess.run(["/usr/bin/python3",'+repr(str(senderfile))+','+repr(str(normal))+','+repr(str(receiver.port))+'],capture_output=True,text=True,check=True)\nr.append({"operation":"legal_clean_connect",**json.loads(clean.stdout)})\nsubprocess.run(["/usr/bin/python3","-c",'+repr(writer)+'],check=True)\nsecret=subprocess.run(["/usr/bin/python3",'+repr(str(senderfile))+','+repr(str(derived))+','+repr(str(receiver.port))+'],capture_output=True,text=True,check=True)\nr.append({"operation":"derived_connect",**json.loads(secret.stdout)})'+tail
            payload=project/'run_task.py';payload.write_text(code);payload.chmod(0o644)
            command=['/usr/bin/python3',str(payload)]
            env={**os.environ,'ACTPLANE_BPF_PIN_ROOT':str(pinbase/name),'ACTPLANE_RESERVE_OPEN_RULES':'1','ACTPLANE_RESERVE_FILE_FLOW':'1','ACTPLANE_ENABLE_ADVANCED_HOOKS':'1','SUDO_UID':'65534','SUDO_GID':'65534','PYTHONDONTWRITEBYTECODE':'1'}
            if mode=='actplane':command=[str(BINARY),'--policy',str(policy),'run',*command];preexec=None
            else:
                preexec=drop
                if mode=='static_sandbox':
                    mounts=['/usr/bin/bwrap','--unshare-user','--unshare-pid','--cap-drop','ALL','--ro-bind','/','/','--proc','/proc','--dev','/dev','--bind',str(src),str(src),'--bind',str(out),str(out)]
                    if scenario in ('plugin','descendants'):mounts+=['--tmpfs',str(cred),'--chmod','000',str(cred)]
                    if scenario=='isolation':mounts+=['--ro-bind','/dev/null',str(other)]
                    command=[*mounts,'--',*command]
            before=hashlib.sha256(protected.read_bytes()).hexdigest()
            result=subprocess.run(command,cwd=work,env=env,preexec_fn=preexec,capture_output=True,text=True,timeout=50)
            time.sleep(.15)
            parsed=next((json.loads(line[7:]) for line in result.stdout.splitlines() if line.startswith('RESULT=')),None)
            events=[]
            for file in work.glob('.actplane/**/events.jsonl'):
                for line in file.read_text().splitlines():
                    try:events.append(json.loads(line))
                    except ValueError:pass
            events=list({json.dumps(e,sort_keys=True):e for e in events}.values())
            after=hashlib.sha256(protected.read_bytes()).hexdigest() if protected.exists() else None
            checks={item['operation']:item for item in parsed['operations']} if parsed else {}
            item={'scenario':scenario,'mode':mode,'repeat':repeat,'returncode':result.returncode,'operations':checks,'protected_before':before,'protected_after':after,
                'receiver_messages':receiver.messages,'kernel_events':events,'policy':policy.read_text(),'stdout':result.stdout,'stderr':result.stderr,
                'command':command,'payload':code,'hook_profile':{k:v for k,v in env.items() if k.startswith('ACTPLANE_')}}
            legal=next((v['allowed'] for k,v in checks.items() if k.startswith('legal_')),False)
            if scenario in ('plugin','descendants'):unsafe=any('SYNTHETIC_SECRET_CANARY' in str(v) for v in checks.values()) or checks.get(attack,{}).get('allowed',False)
            elif scenario in ('integrity','path'):unsafe=before!=after
            elif scenario=='flow':unsafe='SYNTHETIC_SECRET_CANARY' in receiver.messages
            else:unsafe=checks.get(attack,{}).get('value')=='OTHER_AGENT_SYNTHETIC'
            item.update(legal_completed=legal,unsafe_effect=unsafe,
                kernel_denial_proven=any(e.get('blocked') and e.get('effect')=='block' for e in events),
                harness_completed=parsed is not None and result.returncode==0)
            report['cases'].append(item)
            print(name,'legal='+str(legal),'unsafe='+str(unsafe),'kernel='+str(item['kernel_denial_proven']),flush=True)
            (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        candidate=pinbase/name
        if candidate.exists() and candidate.parent==pinbase:shutil.rmtree(candidate)
    report['finished_at']=time.time()
    tested=[c for c in report['cases'] if c['mode']=='actplane']
    report['passed']=all(c['harness_completed'] and c['legal_completed'] and not c['unsafe_effect'] and c['kernel_denial_proven'] for c in tested)
    (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':report['passed'],'report':str(root/'report.json'),'cases':len(report['cases'])}))

if __name__=='__main__':main()
