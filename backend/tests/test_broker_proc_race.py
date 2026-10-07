import ast,json,subprocess
from pathlib import Path
from types import SimpleNamespace


def test_domain_member_exit_race_keeps_live_executor(monkeypatch):
    # Load the real function without executing the broker process setup.
    source=Path(__file__).parents[1]/'broker/main.py'
    function=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='domain_members')
    scope={'Path':Path,'subprocess':subprocess,'json':json}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),scope)
    rows=[{'key':pid,'value':5} for pid in [11,12,13,14]]
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(rows)))
    def read(path,*a,**k):
        pid=int(path.parent.name)
        if pid==12:raise ProcessLookupError(3,'No such process')
        if pid==13:raise FileNotFoundError(2,'No such file')
        return 'State:\t'+('Z' if pid==14 else 'S')+' (process)\n'
    monkeypatch.setattr(Path,'read_text',read)
    assert scope['domain_members']({'pin_root':'/pins/task','domain_id':5})==[11]



def test_failed_watch_launch_closes_resources_and_removes_owned_pins(tmp_path):
    import threading,signal
    source=Path(__file__).parents[1]/'broker/main.py'
    functions=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ('launch','launch_slot')]
    script=tmp_path/'runtime';script.touch()
    pin_root=tmp_path/'owned-pins';pin_root.mkdir()
    processes=[];cleaned=[]
    class Process:
        def __init__(self,command,**kwargs):
            self.pid=100+len(processes);self.returncode=7 if len(processes) else None
            self.stdout=kwargs.get('stdout');processes.append(self)
        def poll(self):return self.returncode
        def terminate(self):self.returncode=-15
        def wait(self,**_):return self.returncode
    scope={'Path':Path,'subprocess':SimpleNamespace(Popen=Process,DEVNULL=-3,STDOUT=-2,TimeoutExpired=subprocess.TimeoutExpired),
        'threading':threading,'LOCK':threading.RLock(),'LAUNCH_LOCK':threading.RLock(),'WEB_PORTS':set(),'contextmanager':__import__('contextlib').contextmanager,'TASKS':{},'DSH':script,'RUNNER':script,'ACTPLANE':script,
        'AGENT':SimpleNamespace(pw_uid=1000),'TASK_GID':1000,'WORKSPACES':tmp_path,'OUTPUTS':tmp_path,
        'checked_task':lambda *_:None,'path_under':lambda path,*_:Path(path),
        'compile_policy':lambda *_:{'policy_path':str(script),'watch_path':str(script),'dsl_path':str(script)},
        'prepare_task_dsh_home':lambda *_:tmp_path/'home','LOG_DIR':tmp_path/'logs',
        'child_env':lambda *_a,**_k:{'ACTPLANE_BPF_PIN_ROOT':str(pin_root)},'user_preexec':lambda:None,
        'signal':signal,'time':__import__('time'),'quiesce_domain':lambda record:cleaned.append(('quiesce',record)),
        'remove_task_engine':lambda record:cleaned.append(('remove',record))}
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),scope)
    import pytest
    with pytest.raises(RuntimeError,match='watch exited 7'):
        scope['launch']('a'*16,1,str(tmp_path/'r'),str(tmp_path/'output'),'task','','',task_token='t'*40)
    assert processes[0].returncode==-15 and processes[1].stdout.closed
    assert len(cleaned)==1 and cleaned[0][0]=='remove' and cleaned[0][1]['pin_root']==str(pin_root)
    assert scope['TASKS']=={}


def test_launch_preparation_does_not_block_other_task_registry_reads():
    import threading,contextlib
    source=Path(__file__).parents[1]/'broker/main.py'
    function=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='launch_slot')
    scope={'LOCK':threading.RLock(),'LAUNCH_LOCK':threading.RLock(),'WEB_PORTS':set(),'TASKS':{},'contextmanager':contextlib.contextmanager}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),scope)
    entered=threading.Event();release=threading.Event();read=threading.Event()
    def launch():
        with scope['launch_slot']('new','managed-web'):
            scope['WEB_PORTS'].add(18020);entered.set();release.wait(2)
    def inspect():
        with scope['LOCK']:read.set()
    a=threading.Thread(target=launch);a.start();assert entered.wait(1)
    b=threading.Thread(target=inspect);b.start()
    try:assert read.wait(.5),'A long launch blocked unrelated status/audit reads'
    finally:release.set();a.join();b.join()
    assert not scope['WEB_PORTS'],'Failed preparation leaked a port lease'
    scope['TASKS']['old']={'task_id':'old','scope_mode':'managed-web','watch':SimpleNamespace(poll=lambda:None),'web_port':18021}
    scope['WEB_PORTS'].add(18021)
    with scope['launch_slot']('different','managed-web'):pass
    assert scope['WEB_PORTS']=={18021}
    import pytest
    with pytest.raises(RuntimeError):
        with scope['launch_slot']('old','managed-web'):pass
    with pytest.raises(RuntimeError):
        with scope['launch_slot']('legacy','cold'):pass


def test_root_relay_waits_for_exact_pid_admission_before_reading_code(tmp_path):
    import os,time,pytest
    if os.geteuid()!=0:pytest.skip('Root relay admission is tested under root')
    source=Path(__file__).parents[1]/'broker/main.py'
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RELAY_BOOTSTRAP' for t in n.targets))
    code=ast.literal_eval(node.value)
    gate=tmp_path/'ready';marker=tmp_path/'executed';runner=tmp_path/'runner.py'
    runner.write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")\n')
    child=subprocess.Popen(['/usr/bin/python3','-c',code,str(gate),'nonce',str(runner)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        time.sleep(.15)
        assert child.poll() is None and not marker.exists()
        gate.write_text('nonce');gate.chmod(0o600)
        child.communicate(timeout=3)
        assert child.returncode==0 and marker.read_text()=='executed' and not gate.exists()
    finally:
        if child.poll() is None:child.kill();child.communicate()
    marker.unlink();gate.write_text('forged');gate.chmod(0o600)
    denied=subprocess.run(['/usr/bin/python3','-c',code,str(gate),'nonce',str(runner)],capture_output=True,timeout=3)
    assert denied.returncode==78 and not marker.exists()
    gate.unlink();other=tmp_path/'other';other.write_text('nonce');other.chmod(0o600);gate.symlink_to(other)
    denied=subprocess.run(['/usr/bin/python3','-c',code,str(gate),'nonce',str(runner)],capture_output=True,timeout=3)
    assert denied.returncode!=0 and not marker.exists()


def test_process_scope_revokes_holder_missing_from_kernel_map(tmp_path):
    import os,signal,time,uuid,pytest,re
    if os.geteuid()!=0 or not os.access('/sys/fs/cgroup',os.W_OK):pytest.skip('Writable cgroup v2 is required')
    source=Path(__file__).parents[1]/'broker/main.py'
    names={'task_cgroup','create_task_cgroup','cgroup_state','kill_task_cgroup','quiesce_domain','remove_task_engine'}
    functions=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
    profile='agentscope-test-'+uuid.uuid4().hex[:12]
    scope={'Path':Path,'RUNTIME':Path('/run')/profile,'re':re,'time':time,'os':os,'signal':signal,'domain_members':lambda _:[]}
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),scope)
    record={'task_id':'a'*16,'domain_id':9,**scope['create_task_cgroup']('a'*16,9)}
    target=tmp_path/'held';original=b'unchanged content';target.write_bytes(original)
    code='import sys,os,mmap,time;sys.stdin.read(1);f=os.open(sys.argv[1],os.O_RDWR);m=mmap.mmap(f,0);print("ready",flush=True);time.sleep(30)'
    child=subprocess.Popen(['/usr/bin/python3','-c',code,str(target)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        (Path(record['process_cgroup'])/'cgroup.procs').write_text(str(child.pid));child.stdin.write('1');child.stdin.flush()
        assert child.stdout.readline().strip()=='ready'
        killed=scope['quiesce_domain'](record)
        assert child.pid in killed and child.wait(timeout=3)==-signal.SIGKILL
        assert target.read_bytes()==original
        assert scope['cgroup_state'](Path(record['process_cgroup']))['populated']=='0'
        forged={**record,'process_cgroup':'/sys/fs/cgroup/init.scope'}
        with pytest.raises(RuntimeError,match='identity mismatch'):scope['task_cgroup'](forged)
    finally:
        if child.poll() is None:child.kill();child.wait()
        scope['remove_task_engine'](record)
        (Path('/sys/fs/cgroup')/profile).rmdir()


def test_probe_pre_execution_binding_rejects_missing_or_wrong_domain(monkeypatch):
    import pytest
    source=Path(__file__).parents[1]/'broker/task_runner.py'
    function=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='verify_probe_binding')
    scope={'Path':Path,'subprocess':subprocess,'json':json}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),scope)
    args=SimpleNamespace(pin_root='/pins/task',process_cgroup='/sys/fs/cgroup/task-7',domain_id=7)
    monkeypatch.setattr(subprocess,'run',lambda *_a,**_k:SimpleNamespace(returncode=1,stdout=''))
    with pytest.raises(RuntimeError,match='no verified kernel domain'):scope['verify_probe_binding'](args,123)
    monkeypatch.setattr(subprocess,'run',lambda *_a,**_k:SimpleNamespace(returncode=0,stdout=json.dumps({'value':8})))
    with pytest.raises(RuntimeError,match='domain mismatch'):scope['verify_probe_binding'](args,123)
    monkeypatch.setattr(subprocess,'run',lambda *_a,**_k:SimpleNamespace(returncode=0,stdout=json.dumps({'value':7})))
    monkeypatch.setattr(Path,'read_text',lambda p:'0::/wrong-scope\n')
    with pytest.raises(RuntimeError,match='process scope mismatch'):scope['verify_probe_binding'](args,123)
