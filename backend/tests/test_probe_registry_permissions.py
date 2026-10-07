"""Real filesystem admission tests; privileged cases run explicitly as root."""
import grp
import importlib.util
import json
import os
import pwd
import stat
import subprocess
from pathlib import Path

import pytest

source=Path(__file__).parents[1]/'broker/task_runner.py'
spec=importlib.util.spec_from_file_location('probe_permission_runner',source)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

pytestmark=pytest.mark.skipif(os.geteuid()!=0,reason='requires real root ownership and task-group admission')


@pytest.fixture
def workspace(tmp_path):
    root=tmp_path/'r';root.mkdir()
    directory=root/'.actplane';directory.mkdir()
    gid=grp.getgrnam('agentscope-task').gr_gid
    os.chown(directory,0,gid);os.chmod(directory,0o2750)
    return root


def test_umask_077_registry_is_root_task_group_0640_and_api_can_read(workspace):
    record={'pid':123,'domain_id':7,'request_id':'probe-regression','domain_verified':True}
    old=os.umask(0o077)
    try:
        runner.append_probe_record(workspace,record)
    finally:
        os.umask(old)
    target=workspace/'.actplane/probes.jsonl'
    info=target.stat();gid=grp.getgrnam('agentscope-task').gr_gid
    assert (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,gid,0o640)
    assert json.loads(target.read_text())==record
    directory_fd=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
    account=pwd.getpwnam('agentscope-api')
    def api_identity():
        os.setgroups([gid]);os.setgid(gid);os.setuid(account.pw_uid)
    code='import os,sys,json;fd=os.open("probes.jsonl",os.O_RDONLY,dir_fd=int(sys.argv[1]));print(json.loads(os.read(fd,4096))["request_id"]);os.close(fd)'
    try:
        result=subprocess.run(['/usr/bin/python3','-c',code,str(directory_fd)],capture_output=True,text=True,
                              pass_fds=(directory_fd,),preexec_fn=api_identity,check=True)
    finally:
        os.close(directory_fd)
    assert result.stdout.strip()=='probe-regression'


def test_existing_0600_registry_is_repaired_before_append(workspace):
    target=workspace/'.actplane/probes.jsonl'
    target.write_text(json.dumps({'request_id':'before'})+'\n');target.chmod(0o600)
    runner.append_probe_record(workspace,{'request_id':'after'})
    assert stat.S_IMODE(target.stat().st_mode)==0o640
    assert [json.loads(line)['request_id'] for line in target.read_text().splitlines()]==['before','after']


@pytest.mark.parametrize('kind',['symlink','fifo','hardlink','nonroot','writable'])
def test_untrusted_registry_is_rejected_without_modifying_aliased_control_bytes(workspace,kind):
    target=workspace/'.actplane/probes.jsonl';outside=workspace/'other'
    outside.write_text('unchanged');outside.chmod(0o640)
    if kind=='symlink':target.symlink_to(outside)
    elif kind=='fifo':os.mkfifo(target,0o640)
    elif kind=='hardlink':os.link(outside,target)
    else:
        target.write_text('untrusted');target.chmod(0o640)
        if kind=='nonroot':os.chown(target,pwd.getpwnam('agentscope-api').pw_uid,-1)
        else:target.chmod(0o666)
    with pytest.raises((OSError,ValueError)):
        runner.append_probe_record(workspace,{'request_id':'must-not-append'})
    assert outside.read_text()=='unchanged'


def test_symlink_registry_directory_is_rejected(workspace):
    actual=workspace/'.actplane';moved=workspace/'control'
    actual.rename(moved);actual.symlink_to(moved,target_is_directory=True)
    with pytest.raises(OSError):
        runner.append_probe_record(workspace,{'request_id':'must-not-append'})
    assert not (moved/'probes.jsonl').exists()
