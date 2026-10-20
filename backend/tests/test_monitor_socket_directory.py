"""Validate the privileged monitor boundary without requiring root in pytest."""
import stat
from pathlib import Path
from types import SimpleNamespace
import pytest
from broker.instance_runtime import monitor_socket_directory


@pytest.mark.parametrize('owner,mode,symlink',[
    (1000,stat.S_IFDIR|0o700,False),
    (0,stat.S_IFDIR|0o755,False),
    (0,stat.S_IFREG|0o700,False),
    (0,stat.S_IFDIR|0o700,True),
])
def test_untrusted_socket_directory_rejected(monkeypatch,owner,mode,symlink):
    monkeypatch.setattr(Path,'mkdir',lambda *a,**k:None)
    monkeypatch.setattr(Path,'lstat',lambda _:SimpleNamespace(st_uid=owner,st_mode=mode))
    monkeypatch.setattr(Path,'is_symlink',lambda _:symlink)
    with pytest.raises(ValueError,match='Untrusted'):
        monitor_socket_directory('/run/test')


def test_short_trusted_directory_and_unix_length(monkeypatch):
    calls=[]
    monkeypatch.setattr(Path,'mkdir',lambda self,**k:calls.append((self,k)))
    monkeypatch.setattr(Path,'lstat',lambda _:SimpleNamespace(st_uid=0,st_mode=stat.S_IFDIR|0o700))
    monkeypatch.setattr(Path,'is_symlink',lambda _:False)
    assert monitor_socket_directory('/run/test')==Path('/run/test/sockets')
    assert calls[0][1]=={'mode':0o700,'exist_ok':True}
    with pytest.raises(ValueError,match='too long'):
        monitor_socket_directory('/run/'+('x'*80))
