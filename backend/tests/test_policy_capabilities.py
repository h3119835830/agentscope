import hashlib,json,platform
from pathlib import Path
from types import SimpleNamespace
from broker.policy_capabilities import installed,loaded_features

def test_attestation_requires_matching_binary_kernel_and_root_ownership(tmp_path,monkeypatch):
    binary=tmp_path/'actplane';binary.write_bytes(b'acceptance-binary')
    manifest=tmp_path/'actplane.capabilities.json'
    evidence=dict(schema='agentscope.execution-capabilities.v1',binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),kernel_release=platform.release(),runtime_verified=True,file_suffix=True,max_suffix_bytes=63)
    manifest.write_text(json.dumps(evidence))
    # Ownership is simulated only in this unit test; isolated integration uses root.
    real=Path.stat
    def root_stat(self,**kwargs):
        s=real(self,**kwargs)
        return SimpleNamespace(st_uid=0,st_mode=s.st_mode)
    monkeypatch.setattr(Path,'stat',root_stat)
    monkeypatch.setattr(Path,'lstat',lambda self:root_stat(self,follow_symlinks=False))
    binary.chmod(0o755);manifest.chmod(0o644);tmp_path.chmod(0o755)
    assert installed(binary)['file_suffix']
    for key,value in [('runtime_verified',False),('max_suffix_bytes',64),('kernel_release','other-kernel'),('binary_sha256','0'*64)]:
        manifest.write_text(json.dumps({**evidence,key:value}));assert not installed(binary)['file_suffix']
    manifest.write_text(json.dumps(evidence));binary.write_bytes(b'replaced');assert not installed(binary)['file_suffix']
    binary.write_bytes(b'acceptance-binary');manifest.chmod(0o666);assert not installed(binary)['file_suffix']

def test_loaded_features_are_read_from_kernel_map(monkeypatch):
    import subprocess
    for value in (["0x02","0x00","0x00","0x00"],2,{'value':2}):
        monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps({'value':value})))
        assert loaded_features({'pin_root':'/isolated/pin'})==2
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout=''))
    assert loaded_features({'pin_root':'/isolated/pin'}) is None
