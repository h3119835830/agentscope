import json
import pytest
from agentscope_app import db
from agentscope_app.instances import controller as c,store


@pytest.fixture
def row(client,tmp_path):
    value=store.create('offline receipt test','dsh',[str(tmp_path)])
    store.update(value['id'],generation='a'*32,runtime={'supervision':'broker-admission-v1'})
    return store.get(value['id'])


def events(row):
    payload={'generation':row['generation'],'session_id':'session','call_id':'call','tool':'read'}
    return [{'sequence':1,'kind':'tool_start','payload':payload,'created_at':1700000000.0},
            {'sequence':2,'kind':'tool_result','payload':{**payload,'succeeded':True},'created_at':1700000001.0}]


def test_recovery_commit_precedes_ack_and_retry_does_not_duplicate(row,monkeypatch):
    attempts=[]
    def runtime(value,operation,**fields):
        if operation=='events':return {'events':events(row)}
        assert operation=='ack' and fields['sequence']==2
        with db.connect() as con:
            assert con.execute('SELECT COUNT(*) FROM instance_runtime_receipts WHERE instance_id=?',(row['id'],)).fetchone()[0]==2
            assert con.execute('SELECT COUNT(*) FROM instance_leases WHERE instance_id=?',(row['id'],)).fetchone()[0]==0
        attempts.append(operation)
        if len(attempts)==1:raise TimeoutError('ACK was lost')
        return {'ok':True}
    monkeypatch.setattr(c,'runtime_call',runtime)
    with pytest.raises(TimeoutError):c.collect_runtime_events(row)
    c.collect_runtime_events(row)
    assert len([e for e in store.events(row['id']) if e['kind'].startswith('tool_')])==2


def test_changed_generation_never_acknowledges_or_imports_old_queue(row,monkeypatch):
    store.update(row['id'],generation='b'*32)
    operations=[]
    def runtime(value,operation,**fields):operations.append(operation);return {'events':events(row)}
    monkeypatch.setattr(c,'runtime_call',runtime)
    with pytest.raises(ValueError,match='代次'):c.collect_runtime_events(row)
    assert operations==['events']
    assert not [e for e in store.events(row['id']) if e['kind'].startswith('tool_')]


def test_changed_receipt_rolls_back_and_cannot_be_acknowledged(row,monkeypatch):
    batch=events(row)
    monkeypatch.setattr(c,'runtime_call',lambda _,operation,**fields:{'events':batch} if operation=='events' else {'ok':True})
    c.collect_runtime_events(row)
    batch[1]['payload']['succeeded']=False
    operations=[]
    def runtime(value,operation,**fields):operations.append(operation);return {'events':batch}
    monkeypatch.setattr(c,'runtime_call',runtime)
    with pytest.raises(ValueError,match='内容变化'):c.collect_runtime_events(row)
    assert operations==['events']
