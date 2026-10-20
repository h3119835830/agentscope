"""Opt-in real per-template runtime acceptance, synthetic files/localhost only."""
import argparse,copy,hashlib,json,os,platform,pwd,shutil,socket,subprocess,sys,tempfile,threading,time,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OPERATOR=r'''
import json,os,socket,subprocess,sys
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text());p=c["path"]
r={"pid":os.getpid(),"operation":c["operation"]}
try:
 if c.get("read_first"):Path(c["read_first"]).read_bytes()
 if c.get("remote"):
  s=socket.create_connection(("127.0.0.1",c["port"]),timeout=3);s.recv(64);s.close()
 if c["operation"]=="open":
  r["value"]=Path(p).read_text()
 elif c["operation"]=="write":
  fd=os.open(p,os.O_WRONLY);os.write(fd,b"CHANGED");os.close(fd)
 elif c["operation"]=="unlink":os.unlink(p)
 elif c["operation"]=="connect":
  s=socket.create_connection((c["address"],c["port"]),timeout=3);s.sendall(b"SYNTHETIC");s.recv(64);s.close()
 elif c["operation"]=="exec":
  v=subprocess.Popen([c["program"]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);r["exec_pid"]=v.pid;v.communicate();r["exec_returncode"]=v.returncode
 r["ok"]=True
except OSError as e:r.update(ok=False,errno=e.errno,error=type(e).__name__)
print("OP="+json.dumps(r),flush=True)
'''
RUNNER=r'''
import json,os,subprocess,sys
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text())
if c.get("checker_mode") in ("success","failed","changed"):
 v=subprocess.run([c["checker"],"-c","exit 1" if c["checker_mode"]=="failed" else "exit 0"])
 if c["checker_mode"]=="changed":Path(c["invalidate"]).write_text("post-check change")
if c.get("code_read"):Path(c["code_read"]).read_bytes()
for action in c["actions"]:
 command=["/usr/bin/python3",c["operator"],action.get("input","")]
 if action.get("producer"):command=[action["producer"],"-c",'exec "$@"',"asmaker",*command]
 if action.get("git"):command=["/usr/bin/git",*action["git"]]
 v=subprocess.run(command,cwd=action.get("cwd"),capture_output=True,text=True)
 print("RESULT="+json.dumps({"phase":action["phase"],"returncode":v.returncode,"stdout":v.stdout,"stderr":v.stderr}),flush=True)
'''

def owned(path,uid,gid):
 os.chown(path,uid,gid);return path

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--only',default='');parser.add_argument('--engine',default='/var/lib/agentscope-scope-demo/bin/actplane');args=parser.parse_args()
 import fcntl
 acceptance_lock=open('/var/tmp/agentscope-template-runtime-acceptance.lock','a')
 fcntl.flock(acceptance_lock,fcntl.LOCK_EX)
 assert os.geteuid()==0
 out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
 state=Path(tempfile.mkdtemp(prefix='asrt-',dir='/var/tmp'));state.chmod(0o755)
 os.environ['AGENTSCOPE_STATE_DIR']=str(state/'state')
 os.environ['AGENTSCOPE_BROKER_SOCKET']=str(state/'absent.sock')
 for k in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_RUNTIME_DIR'):os.environ.pop(k,None)
 sys.path.insert(0,str(ROOT/'backend'))
 from agentscope_app import db
 from agentscope_app.instances import template_catalog as catalog,template_configurations as tc,template_versions
 db.init_db()
 with db.connect() as con:template_versions.init(con)
 owner=pwd.getpwnam('happy');uid,gid=owner.pw_uid,owner.pw_gid
 tools=state/'bin';tools.mkdir()
 for name,source in [('asprobe','/usr/bin/python3'),('aschild','/bin/true'),('asmaker','/bin/sh'),('ascheck','/bin/sh')]:
  shutil.copy2(source,tools/name)
 operator=state/'operation.py';operator.write_text(OPERATOR)
 runner=state/'runner.py';runner.write_text(RUNNER)
 engine=Path(args.engine).resolve(strict=True)
 pin=Path('/sys/fs/bpf')/('asrt-'+uuid.uuid4().hex);assert not pin.exists()
 env={'PATH':'/usr/bin:/bin','HOME':owner.pw_dir,'SUDO_UID':str(uid),'SUDO_GID':str(gid),'ACTPLANE_BPF_PIN_ROOT':str(pin),
      'ACTPLANE_RESERVE_OPEN_RULES':'1','ACTPLANE_RESERVE_PATH_SUFFIX':'1','ACTPLANE_RESERVE_FILE_FLOW':'1','ACTPLANE_HOOK_PROFILE':'full'}
 listener=socket.socket();listener.bind(('0.0.0.0',0));listener.listen();listener.settimeout(.2)
 port=listener.getsockname()[1];received=[];stop=threading.Event()
 def serve():
  while not stop.is_set():
   try:conn,address=listener.accept()
   except socket.timeout:continue
   except OSError:break
   with conn:
    conn.settimeout(.3)
    try:data=conn.recv(64)
    except socket.timeout:data=b''
    received.append({'peer':address[0],'destination':conn.getsockname()[0],'data':data.decode(errors='replace')})
    try:conn.sendall(b'SYNTHETIC-REPLY')
    except OSError:pass
 thread=threading.Thread(target=serve,daemon=True);thread.start()
 report={'schema':'agentscope.template-runtime-acceptance.v1','scope':'Independent engines, synthetic files/repositories and localhost receiver only; no DSH, formal Broker, approvals or policy loads.',
         'binary_sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),'kernel_release':platform.release(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'cases':[]}
 def write_report():
  report['passed']=bool(report['cases']) and all(c['passed'] for c in report['cases'])
  (out/'runtime-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 def run(t,effect,mode='default',operation=None,token=None):
  n=len(report['cases']);case_id=t['id'].lower()+'-'+effect+'-'+mode+(('-'+operation) if operation else '')+(('-'+token) if token else '')
  home=state/('c'+str(n));home.mkdir();home.chmod(0o755)
  work=home/'w';work.mkdir();owned(work,uid,gid);work.chmod(0o755)
  protected=work/'protected';protected.write_text('ORIGINAL');owned(protected,uid,gid)
  control=work/'public';control.write_text('PUBLIC');owned(control,uid,gid)
  source=work/'source';source.write_text('SOURCE');owned(source,uid,gid)
  target=protected;op=operation or ('open' if t['operation'] in ('read','open') else t['operation'])
  values={p['key']:copy.deepcopy(p['default']) for p in t['parameters']};kind=t['renderer']
  for p in t['parameters']:
   if p['key']=='effect':values[p['key']]=effect
   elif p['key']=='target':values[p['key']]=str(source if kind in ('flow','workflow','git-check') else protected)
   elif p['key']=='program':values[p['key']]='aschild'
   elif p['key']=='endpoint':values[p['key']]='127.0.0.2'
   elif p['key']=='producer':values[p['key']]='asmaker'
   elif p['key']=='checker':values[p['key']]='ascheck'
   elif p['key']=='operations':values[p['key']]=[operation or t['operation']]
   elif p['key']=='exit_code':values[p['key']]='0'
   elif p['key']=='tokens':values[p['key']]=[token or ('--no-verify' if t['id']=='GIT-BYPASS' else 'clean')]
  modified=copy.deepcopy(t);modified['effect']=effect
  if kind=='system':
   preset=next(p for p in catalog.SYSTEM_CATALOG if p['id']==t['system_preset'])
   smode=preset['mode']
   if smode=='suffix':target=work/'private.env';target.write_text('ORIGINAL');owned(target,uid,gid);values['values']='.env'
   elif smode in ('tail','filename'):
    tail={'SYS-ssh':'.ssh/id_rsa','SYS-cloud':'.aws/credentials','SYS-instructions':'AGENTS.md'}[t['id']]
    target=work/tail;target.parent.mkdir(parents=True,exist_ok=True);target.parent.chmod(0o777);target.write_text('ORIGINAL');owned(target,uid,gid);values['values']=tail
   elif smode=='directory':
    directory=work/'guarded';directory.mkdir();owned(directory,uid,gid);target=directory/'file';target.write_text('ORIGINAL');owned(target,uid,gid);values['values']=str(directory)
   elif smode=='exact':values['values']=str(target)
   elif smode in ('exec','remote'):values['values']='aschild';op='exec'
   elif smode=='endpoint':values['values']='127.0.0.2';op='connect'
   elif smode=='flow':
    source=work/'private.env';source.write_text('SOURCE');owned(source,uid,gid);values['values']='.env';op='connect'
  if kind=='boundary':
   values['target']=str(work)+'/**';values['exception']=str(control);op='write'
  if kind=='lineage':op='write'
  if kind=='remote':op='exec'
  actions=[]
  def action(phase,p,**extra):
   input_path=home/(phase+'.json')
   data={'operation':op,'path':str(p),'program':str(tools/'aschild'),'port':port,'address':'127.0.0.2' if phase=='match' else '127.0.0.1',**extra}
   input_path.write_text(json.dumps(data));actions.append({'phase':phase,'input':str(input_path)})
  action('control',control)
  action('match',target)
  if kind=='exec' or (kind=='system' and smode=='exec'):
   data=json.loads((home/'control.json').read_text());data['program']='/bin/true';(home/'control.json').write_text(json.dumps(data))
  if kind=='lineage':
   actions[0]['producer']=str(tools/'asmaker')
   action('control-after',control)
  if kind=='flow' or (kind=='system' and smode=='flow'):
   # The control connects without reading the source; the match reads it first.
   data=json.loads((home/'match.json').read_text());data['read_first']=str(source);(home/'match.json').write_text(json.dumps(data))
  if kind=='remote' or (kind=='system' and smode=='remote'):
   data=json.loads((home/'match.json').read_text());data['remote']=True;(home/'match.json').write_text(json.dumps(data))
  git_mode=kind in ('git-command','git-check','git-tokens','git','workflow')
  git_before=git_after=None
  config={'operator':str(operator),'actions':actions}
  if git_mode:
   repo=work/'repo';repo.mkdir();owned(repo,uid,gid)
   def git(*argv):
    return subprocess.run(['/usr/bin/git',*argv],cwd=repo,user=uid,group=gid,capture_output=True,text=True,check=True).stdout.strip()
   git('init','-q');git('config','user.name','Synthetic Acceptance');git('config','user.email','synthetic@example.invalid')
   git('commit','--allow-empty','-qm','initial');bare=work/'bare';git('init','--bare','-q',str(bare));git('remote','add','origin',str(bare))
   untracked=repo/'untracked';untracked.write_text('SYNTHETIC');owned(untracked,uid,gid)
   git_before=git('rev-parse','HEAD')
   command=t.get('command','commit' if kind=='workflow' else token or 'clean')
   argv={'commit':['commit','--allow-empty','-m','synthetic'],'push':['push','origin','HEAD:refs/heads/test'],'reset':['reset','--soft','HEAD'],'clean':['clean','-fd'],'stash':['stash','list'],'--no-verify':['commit','--no-verify','--allow-empty','-m','synthetic']}[command]
   actions[:]=[{'phase':'control','git':['status','--porcelain'],'cwd':str(repo)},{'phase':'match','git':argv,'cwd':str(repo)}]
   if 'program' in values:values['program']='git'
   if kind in ('git-check','workflow'):
    config.update(checker_mode=mode,checker=str(tools/'ascheck'),invalidate=str(source))
    if kind=='workflow':config['code_read']=str(source)
  normalized={p['key']:tc.normalize_parameter(p,values[p['key']],modified) for p in modified['parameters']}
  document,*_=tc.render_document(modified,normalized,'acceptance',t['name'],'Synthetic acceptance '+t['id'])
  dsl='source AGENT = exec "**/asprobe"\n'+document['original_dsl']
  policy=home/'policy.yaml';policy.write_text('version: 1\npolicy: |\n'+''.join('  '+line+'\n' for line in dsl.splitlines()))
  input_path=home/'runner.json';input_path.write_text(json.dumps(config))
  before={'exists':target.exists(),'text':target.read_text() if target.is_file() else None,'received':len(received)}
  started=time.monotonic()
  result=subprocess.run([str(engine),'--policy',str(policy),'run','--',str(tools/'asprobe'),str(runner),str(input_path)],cwd=home,env=env,capture_output=True,text=True,timeout=60)
  observations=[json.loads(l[7:]) for l in result.stdout.splitlines() if l.startswith('RESULT=')]
  event_paths=list(home.glob('.actplane/runs/*/events.jsonl'))
  events=[json.loads(l) for p in event_paths for l in p.read_text().splitlines() if l.strip()]
  events=[e for e in events if e.get('event')=='taint_violation']
  after={'exists':target.exists(),'text':target.read_text() if target.is_file() else None,'received':received[before['received']:]}
  if git_mode:
   git_after={'head':git('rev-parse','HEAD'),'untracked_exists':untracked.exists(),'remote_ref':subprocess.run(['/usr/bin/git','--git-dir',str(bare),'rev-parse','--verify','refs/heads/test'],capture_output=True,text=True).stdout.strip()}
  checks=[];expected_match=not ((kind=='git-check' and mode=='success') or (kind=='workflow' and mode in ('success','failed')))
  # The retired workflow only observes execution, never a successful exit code.
  for observation in observations:
   is_match=observation['phase']=='match' and expected_match
   if observation['phase']!='match' or not is_match or effect=='notify':
    checks.append(observation['returncode']==0)
    if observation['stdout'].startswith('OP='):
     v=json.loads(observation['stdout'][3:]);checks.append(v['ok'] and v.get('exec_returncode',0)==0)
   elif effect=='kill':
    nested=json.loads(observation['stdout'][3:]) if observation['stdout'].startswith('OP=') else {}
    checks.append(observation['returncode']==-9 or nested.get('exec_returncode')==-9)
   else:
    try:v=json.loads(observation['stdout'][3:]);checks.append(v.get('errno')==1)
    except Exception:checks.append(False)
  checks.append(len(observations)==len(actions));checks.append(result.returncode==0)
  matched=[e for e in events if e.get('effect')==effect]
  checks.append(bool(matched)==expected_match)
  checks.append(not any(e.get('pid')==v.get('pid') for e in events for o in observations if o['phase']=='control' for v in ([json.loads(o['stdout'][3:])] if o['stdout'].startswith('OP=') else [])))
  if effect=='block' and expected_match:
   checks.append(all(e.get('blocked') is True for e in matched))
   if op in ('write','unlink') and not git_mode:checks.append(after['exists'] and after['text']==before['text'])
  if effect=='kill' and expected_match:checks.append(any(e.get('killed') is True for e in matched))
  if effect=='notify':checks.append(all(not e.get('blocked') and not e.get('killed') for e in matched))
  if op=='connect' and not git_mode:
   checks.append(any(v['destination']=='127.0.0.1' for v in after['received']))
   if effect!='kill':checks.append(any(v['destination']=='127.0.0.2' for v in after['received']) == (effect=='notify'))
  if effect=='notify' and not git_mode:
   if op=='write':checks.append(after['text'].startswith('CHANGED'))
   if op=='unlink':checks.append(not after['exists'])
  if effect=='notify' and git_mode:
   if command in ('commit','--no-verify'):checks.append(git_after['head']!=git_before)
   if command=='push':checks.append(git_after['remote_ref']==git_before)
   if command=='clean':checks.append(not git_after['untracked_exists'])
  record={'id':case_id,'template_id':t['id'],'version':t['version'],'effect':effect,'mode':mode,'operation':op,'parameters':values,'dsl':dsl,
          'expected_match':expected_match,'passed':all(checks),'checks':checks,'cli_exit':result.returncode,'observations':observations,'kernel_events':events,
          'event_file_owners':[p.stat().st_uid for p in event_paths],'before':before,'after':after,'git_before':git_before,'git_after':git_after,'seconds':round(time.monotonic()-started,3)}
  report['cases'].append(record);write_report()
  (out/(case_id+'-stdout.txt')).write_text(result.stdout);(out/(case_id+'-stderr.txt')).write_text(result.stderr)
  print(json.dumps({k:record[k] for k in ('id','passed','cli_exit')})+' events='+str(len(events)),flush=True)
 try:
  only=set(args.only.split(',')) if args.only else None
  for public in catalog.public_catalog():
   if only and public['id'] not in only:continue
   t=catalog.get(public['id'],public['version'])
   if t['renderer']=='unsupported':continue
   if t['id']=='RQ1-CHECK':
    for effect in ('notify','kill'):
     for mode in ('missing','success','failed','changed'):run(t,effect,mode)
    continue
   effects=t.get('allowed_effects',['block','notify','kill'])
   if t['id']=='RQ1-GIT':effects=['notify','kill']
   for effect in effects:
    if t['renderer']=='git-check':
     for mode in ('missing','success','failed','changed'):run(t,effect,mode)
    elif t['renderer']=='git-tokens':
     for token in next(p for p in t['parameters'] if p['key']=='tokens')['options']:run(t,effect,token=token)
    elif any(p['key']=='operations' for p in t['parameters']) and t['operation']!='exec':
     for operation in t.get('allowed_operations',['write','unlink']):run(t,effect,operation=operation)
    else:run(t,effect)
 finally:
  stop.set();listener.close();thread.join(timeout=2)
  if pin.exists():
   assert pin.parent==Path('/sys/fs/bpf') and pin.name.startswith('asrt-');shutil.rmtree(pin)
  report['pin_removed']=not pin.exists();write_report()
 print(json.dumps({'passed':report['passed'],'cases':len(report['cases']),'state':str(state),'output':str(out)}),flush=True)
 if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
