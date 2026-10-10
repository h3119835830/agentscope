import json,os,stat
from types import SimpleNamespace
from pathlib import Path
import pytest
from broker.instance_runtime import kernel_events

def setup(tmp_path,monkeypatch):
    directory=tmp_path/'.actplane';directory.mkdir(mode=0o750)
    path=directory/'events.jsonl'
    # Unit tests simulate root ownership, retaining actual descriptor/file IO.
    real_fstat=os.fstat;real_stat=Path.stat
    def root_stat(info):
        return SimpleNamespace(st_uid=0,st_mode=info.st_mode,st_dev=info.st_dev,st_ino=info.st_ino,st_size=info.st_size)
    monkeypatch.setattr(os,'fstat',lambda fd:root_stat(real_fstat(fd)))
    monkeypatch.setattr(Path,'stat',lambda p,*a,**kw:root_stat(real_stat(p,*a,**kw)))
    record=dict(workspace=str(tmp_path),domain_id=7,generation='g1',event_start=0,policy_artifact={'bundle_hash':'hash'})
    return path,record

def test_cursor_generation_domain_and_partial_line(tmp_path,monkeypatch):
    path,record=setup(tmp_path,monkeypatch)
    line=lambda domain:json.dumps({'event':'taint_violation','process_domain_id':domain,'rule':{'name':'same'}}).encode()+b'\n'
    path.write_bytes(line(8)+line(7)+b'{"incomplete":');path.chmod(0o600)
    first=kernel_events(record);assert len(first['events'])==1 and first['generation']=='g1' and first['bundle_hash']=='hash'
    again=kernel_events(record,first['cursor']);assert not again['events'] and again['cursor']==first['cursor']
    path.write_bytes(line(8)+line(7)+b'{"incomplete":true}\n'+line(7))
    last=kernel_events(record,first['cursor']);assert len(last['events'])==1 and last['events'][0]['offset']>first['events'][0]['offset']

def test_previous_generation_events_excluded_and_symlink_or_writable_log_rejected(tmp_path,monkeypatch):
    path,record=setup(tmp_path,monkeypatch)
    old=b'{"event":"taint_violation","process_domain_id":7}\n';path.write_bytes(old);path.chmod(0o600)
    record['event_start']=len(old)
    assert not kernel_events(record)['events']
    path.chmod(0o666)
    with pytest.raises(ValueError,match='ownership'):kernel_events(record)
    path.unlink();other=tmp_path/'outside';other.write_bytes(old);path.symlink_to(other)
    with pytest.raises(OSError):kernel_events(record)

def test_new_generation_has_independent_cursor_and_preserves_old_evidence(tmp_path,monkeypatch):
    path,record=setup(tmp_path,monkeypatch)
    line=b'{"event":"taint_violation","process_domain_id":7}\n'
    path.write_bytes(line*40);path.chmod(0o600)
    previous=kernel_events(record)
    next_root=tmp_path/'next-generation';next_events=next_root/'.actplane';next_events.mkdir(parents=True,mode=0o750)
    new_path=next_events/'events.jsonl';new_path.write_bytes(line*3);new_path.chmod(0o600)
    next_record={**record,'workspace':str(next_root),'generation':'g2','event_start':0}
    current=kernel_events(next_record,previous['cursor'])
    assert len(current['events'])==3 and current['events'][0]['offset']==0
    assert current['cursor']['file']!=previous['cursor']['file'] and current['generation']=='g2'
    assert path.read_bytes()==line*40
