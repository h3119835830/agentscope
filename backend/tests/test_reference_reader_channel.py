"""Regression for the real API UID != controlled-runtime UID deployment."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import pytest
import reference_reader_channel as channel
from agentscope_app.instances import workspace_references as refs


def test_mismatched_api_without_channel_fails_closed(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda: 999)
    monkeypatch.setattr(refs, 'READER_CHANNEL', None)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('must not read as API'))
    with pytest.raises(channel.ReaderUnavailable, match='读取服务不可用'):
        refs.run_reader({'root': '/registered', 'paths': ['README.md']}, 1000, 986)


@pytest.mark.parametrize('payload', [
    {'root': '/', 'paths': ['etc/passwd']},
    {'root': '/registered/../outside', 'paths': ['README.md']},
    {'root': '/registered', 'paths': ['README.md'], 'uid': 0},
    {'root': '/registered', 'operation': 'shell', 'command': 'id'},
    {'root': '/registered', 'paths': ['README.md'], 'executable': '/bin/sh'},
])
def test_channel_has_no_identity_command_or_root_escape_fields(payload):
    with pytest.raises(ValueError):
        channel.validate(payload)


def test_client_identity_mismatch_cannot_send():
    left, right = socket.socketpair()
    with left, right:
        client = channel.Client(left, {'uid': 1000, 'gid': 986, 'groups': [986]})
        with pytest.raises(channel.ReaderUnavailable):
            client.read({'root': '/registered', 'paths': ['README.md']}, 1000, 986, 1)
        right.settimeout(.01)
        with pytest.raises(socket.timeout):
            right.recv(1)


def test_malformed_response_breaks_channel_instead_of_reusing_stream():
    left, right = socket.socketpair()
    with left, right:
        client = channel.Client(left, {'uid': 1000, 'gid': 986, 'groups': []})
        def malformed():
            channel.receive(right, channel.MAX_REQUEST)
            channel.send(right, {'unexpected': True}, channel.MAX_RESPONSE)
        thread = threading.Thread(target=malformed);thread.start()
        with pytest.raises(channel.ReaderUnavailable):
            client.read({'root': '/registered', 'paths': ['README.md']}, 1000, 986, 1)
        thread.join()
        assert client.broken


def test_denied_file_does_not_poison_next_request():
    left, right = socket.socketpair()
    with left, right:
        client = channel.Client(left, {'uid': 1000, 'gid': 986, 'groups': []})
        def respond():
            for response in ({'error': 'read_denied'}, {'result': {'files': []}}):
                channel.receive(right, channel.MAX_REQUEST)
                channel.send(right, response, channel.MAX_RESPONSE)
        thread = threading.Thread(target=respond);thread.start()
        with pytest.raises(ValueError, match='无读取权限'):
            client.read({'root': '/registered', 'paths': ['README.md']}, 1000, 986, 1)
        assert client.read({'root': '/registered', 'paths': ['README.md']}, 1000, 986, 1) == {'files': []}
        thread.join()


def test_actual_api_identity_uses_exact_reader_without_gaining_dac(monkeypatch):
    if os.geteuid() != 0:
        pytest.skip('real three-identity regression needs root launcher')
    import grp, pwd
    api = pwd.getpwnam('agentscope-api')
    reader = pwd.getpwnam('happy')
    group = grp.getgrnam('agentscope-task').gr_gid
    with tempfile.TemporaryDirectory(prefix='reference-channel-') as directory:
        root = Path(directory);root.chmod(0o755)
        for source in (Path(channel.__file__), refs.WORKER):
            shutil.copyfile(source, root/source.name);(root/source.name).chmod(0o644)
        allowed = root/'allowed.md';allowed.write_text('synthetic reader-only document')
        os.chown(allowed, reader.pw_uid, group);allowed.chmod(0o600)
        denied = root/'denied.md';denied.write_text('synthetic root-only document');denied.chmod(0o600)
        (root/'alias.md').symlink_to(allowed)
        code = '''
import json,os,sys
sys.path.insert(0,sys.argv[1])
import reference_reader_channel as c
client=c.inherited_client()
assert c.FD_ENV not in os.environ
assert not os.get_inheritable(client.connection.fileno())
uid,gid=int(sys.argv[2]),int(sys.argv[3])
root=sys.argv[1]
try:open(root+'/allowed.md').read()
except PermissionError:pass
else:raise AssertionError('API unexpectedly has reader DAC')
result=client.read({'root':root,'paths':['allowed.md']},uid,gid,5)
assert result['files'][0]['text']=='synthetic reader-only document'
for name in ('denied.md','alias.md','../outside.md'):
 try:client.read({'root':root,'paths':[name]},uid,gid,5)
 except ValueError:pass
 else:raise AssertionError('unsafe read accepted')
assert client.read({'operation':'list','root':root},uid,gid,5)['entries']
print(json.dumps({'api_uid':os.geteuid(),'api_gid':os.getegid(),'api_groups':os.getgroups(),'reader':client.identity,'read':True,'denied':True}))
'''
        # Launch the same installed module shape, not an emulated subprocess.
        monkeypatch.setattr(channel, '__file__', str(root/'reference_reader_channel.py'))
        connection, process = channel.launch(sys.executable, reader.pw_uid, group)
        try:
            result = subprocess.run(
                [sys.executable, '-I', '-c', code, str(root), str(reader.pw_uid), str(group)],
                env={channel.FD_ENV: str(connection.fileno()), 'LANG': 'C.UTF-8'},
                user=api.pw_uid, group=api.pw_gid, extra_groups=[api.pw_gid, group],
                pass_fds=(connection.fileno(),), capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 0, result.stderr
            proof = json.loads(result.stdout)
            assert proof['api_uid'] == api.pw_uid
            assert proof['reader'] == {'uid': reader.pw_uid, 'gid': group, 'groups': []}
            status = Path('/proc', str(process.pid), 'status').read_text()
            assert 'CapEff:\t0000000000000000' in status and 'NoNewPrivs:\t1' in status
        finally:
            connection.close()
            process.wait(timeout=5)
        assert process.returncode == 0
