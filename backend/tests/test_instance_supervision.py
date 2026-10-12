"""Admission authority, durable offline results, replay safety and capacity."""
import os
import sqlite3
import pytest
from broker import instance_supervision as module


@pytest.fixture
def admission(tmp_path):
    directory=tmp_path/'root-only';directory.mkdir(mode=0o700)
    value=module.Admission(directory,'a'*32,{'rules':[
        {'action':'tool','target':'danger','effect':'deny'}]},'b'*64,owner=os.getuid())
    value.verified();value.set_gate(True,'已批准')
    return value


def body(call='call-1',**values):
    return {'generation':'a'*32,'session_id':'s-1','call_id':call,'tool':'read',**values}


def test_offline_admission_persists_before_response_and_replays_cannot_execute(admission):
    assert admission.lease(body())['allowed']
    with sqlite3.connect(admission.database) as con:
        assert con.execute('SELECT kind FROM events').fetchone()[0]=='tool_start'
    assert admission.lease(body())['idempotent']
    assert admission.result(body(succeeded=True))['queued']
    assert admission.result(body(succeeded=True))['idempotent']
    assert not admission.lease(body())['allowed']
    events=admission.events()
    assert [e['kind'] for e in events]==['tool_start','tool_result']
    admission.acknowledge(events[-1]['sequence'])
    assert admission.events()==[]
    assert not admission.lease(body())['allowed'] # ACK must preserve a tombstone.
    assert admission.result(body(succeeded=True))['idempotent']


def test_policy_gate_and_fresh_proof_are_independent_of_console(admission,monkeypatch):
    assert not admission.lease(body(tool='danger'))['allowed']
    admission.set_gate(False,'正在撤权')
    assert not admission.lease(body())['allowed']
    admission.verified();admission.set_gate(True,'保护已核验')
    monkeypatch.setattr(module.time,'monotonic',lambda:admission.last_verified+3.1)
    assert not admission.lease(body())['allowed']
    with pytest.raises(ValueError,match='freshly'):admission.set_gate(True,'旧证明')


def test_identity_and_unadmitted_results_cannot_be_forged(admission):
    with pytest.raises(ValueError):admission.lease(body(generation='c'*32))
    with pytest.raises(ValueError):admission.lease(body(policy={'rules':[]}))
    with pytest.raises(ValueError):admission.lease(body(succeeded=True))
    with pytest.raises(ValueError):admission.result(body(succeeded=True))
    assert admission.lease(body())['allowed']
    assert not admission.lease(body(session_id='other'))['allowed']
    with pytest.raises(ValueError):admission.result(body(succeeded='true'))
    admission.result(body(succeeded=False))
    with pytest.raises(ValueError):admission.result(body(succeeded=True))


def test_queue_reserves_results_and_pauses_new_work(admission,monkeypatch):
    monkeypatch.setattr(module,'MAX_EVENTS',4)
    assert admission.lease(body('1'))['allowed']
    assert admission.lease(body('2'))['allowed']
    assert not admission.lease(body('3'))['allowed']
    admission.result(body('1',succeeded=True));admission.result(body('2',succeeded=False))
    events=admission.events();assert len(events)==4
    admission.acknowledge(events[-1]['sequence'])
    assert admission.lease(body('3'))['allowed']


def test_gate_closes_even_when_persistence_fails(admission,monkeypatch):
    def failed():raise sqlite3.OperationalError('disk full')
    monkeypatch.setattr(admission,'connect',failed)
    with pytest.raises(sqlite3.OperationalError):admission.set_gate(False,'停止')
    assert not admission.gate


def test_broker_restart_cannot_resurrect_old_generation(admission):
    with pytest.raises(ValueError,match='resurrected'):
        module.Admission(admission.directory,'a'*32,{'rules':[]},'b'*64,owner=os.getuid())


def test_untrusted_storage_is_rejected(tmp_path):
    directory=tmp_path/'untrusted';directory.mkdir(mode=0o755)
    with pytest.raises(ValueError,match='Unsafe'):
        module.Admission(directory,'a'*32,{'rules':[]},'b'*64,owner=os.getuid())
