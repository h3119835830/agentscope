#!/usr/bin/env python3
"""Isolated live BPF regression: thread churn must not exhaust process-domain bindings."""
import os,sys,time,json,subprocess,signal,re,shutil,hashlib
from pathlib import Path
binary=Path(sys.argv[1]);label=sys.argv[2]
if not re.fullmatch(r'[a-z0-9-]{1,32}',label):raise ValueError('Use a fresh simple evidence label')
root=Path('/var/lib/agentscope-normalization-v1/report')/('thread-check-'+label);root.mkdir(exist_ok=True)
pin=Path('/sys/fs/bpf')/('agentscope-thread-check-'+label)
cgroup=Path('/sys/fs/cgroup')/('agentscope-thread-check-'+label)
assert not pin.exists() and not cgroup.exists();cgroup.mkdir(mode=0o700)
locked=root/'locked';locked.write_text('protected fixture\n');original=locked.read_bytes()
worker=root/'worker.py'
child_code="import os,json,time,sys,mmap;from pathlib import Path;p=Path(sys.argv[1]);blocked=False\ntry:\n p.open('ab').write(b'UNTRACKED_CHILD_WRITE')\nexcept PermissionError:blocked=True\nf=os.open(sys.argv[2],os.O_RDWR);m=mmap.mmap(f,0);Path(sys.argv[3]).write_text(json.dumps({'pid':os.getpid(),'blocked':blocked}));time.sleep(90)"
worker.write_text("import threading,time,subprocess,sys\nfrom pathlib import Path\nr=Path(sys.argv[1])\nwhile not (r/'go').exists():time.sleep(.01)\nfor i in range(20000):\n t=threading.Thread(target=lambda:None);t.start();t.join()\nc=subprocess.Popen(['/usr/bin/python3','-c',"+repr(child_code)+",str(r/'locked'),str(r/'held'),str(r/'child.json')])\ntime.sleep(90)\n")
(root/'held').write_text('holdable fixture\n');(root/'go').unlink(missing_ok=True);(root/'child.json').unlink(missing_ok=True)
dsl='source AGENT = exec "**"\nrule locked:\n  block write file "'+str(locked)+'" if AGENT\n'
policy=root/'policy.yaml';policy.write_text('version: 1\npolicy: |\n'+''.join('  '+l+'\n' for l in dsl.splitlines()))
delta=root/'delta.dsl';delta.write_text(dsl)
env=os.environ.copy();env.update(ACTPLANE_BPF_PIN_ROOT=str(pin),SUDO_UID='0',SUDO_GID='0')
anchor=subprocess.Popen(['/usr/bin/sleep','infinity']);env['ACTPLANE_ATTACH_PID']=str(anchor.pid)
watch=None
try:
 watch=subprocess.Popen([str(binary),'--policy',str(policy),'watch'],env=env,stdout=(root/'watch.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
 deadline=time.monotonic()+30
 while not (root/'.actplane/control.json').exists():
  if watch.poll() is not None:raise RuntimeError('Watch exited: '+(root/'watch.log').read_text()[-1500:])
  if time.monotonic()>deadline:raise TimeoutError('Watch did not become ready')
  time.sleep(.1)
 command=[str(binary),'--policy',str(policy),'control','launch-child','--child-id','987654321','--delta',str(delta),'--','/usr/bin/python3',str(worker),str(root)]
 result=subprocess.run(command,env=env,capture_output=True,text=True,check=True,timeout=35)
 pid=int(re.search(r'Launched pid (\d+)',result.stdout).group(1));(cgroup/'cgroup.procs').write_text(str(pid));(root/'go').touch()
 deadline=time.monotonic()+90
 while not (root/'child.json').exists():
  if time.monotonic()>deadline:raise TimeoutError('Thread churn did not finish')
  time.sleep(.1)
 child=json.loads((root/'child.json').read_text())
 data=subprocess.run(['/usr/sbin/bpftool','-j','map','dump','pinned',str(pin/'maps/cap_task')],capture_output=True,text=True,check=True,timeout=5)
 rows=json.loads(data.stdout)
 def integer(v):return v if isinstance(v,int) else int.from_bytes(bytes(int(x,16) if isinstance(x,str) else x for x in v),'little')
 members={integer(r['key']):integer(r['value']) for r in rows}
 receipt={'label':label,'engine_hash':hashlib.sha256(binary.read_bytes()).hexdigest(),'threads':20000,'map_entries':len(rows),'dead_thread_entries':sum(not Path('/proc',str(p)).exists() for p in members),'child_pid':child['pid'],'child_domain':members.get(child['pid']),'protected_write_blocked':child['blocked'],'protected_integrity':locked.read_bytes()==original}
 (root/'result.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
finally:
 if cgroup.exists():
  (cgroup/'cgroup.kill').write_text('1')
  deadline=time.monotonic()+5
  while 'populated 1' in (cgroup/'cgroup.events').read_text() and time.monotonic()<deadline:time.sleep(.02)
  cgroup.rmdir()
 if watch and watch.poll() is None:watch.send_signal(signal.SIGINT);watch.wait(timeout=10)
 if anchor.poll() is None:anchor.terminate();anchor.wait(timeout=5)
 if pin.exists():
  assert pin.resolve().parent==Path('/sys/fs/bpf') and pin.name=='agentscope-thread-check-'+label
  shutil.rmtree(pin)
