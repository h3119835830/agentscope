"""Concurrent dashboard reads share work without retaining stale approvals."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
import pytest
from agentscope_app.instances import approval_views as approvals


def test_concurrent_readers_share_one_snapshot_and_next_read_is_fresh(monkeypatch):
    entered=threading.Event();release=threading.Event();calls=[]
    def read():
        calls.append(len(calls)+1);entered.set();assert release.wait(3)
        return {'records':[{'revision':len(calls)}]}
    monkeypatch.setattr(approvals,'_read_directory',read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(approvals.directory);assert entered.wait(3)
        second=pool.submit(approvals.directory)
        with pytest.raises(TimeoutError):second.result(timeout=.03)
        release.set()
        assert first.result(timeout=3)==second.result(timeout=3)=={'records':[{'revision':1}]}
    assert calls==[1]
    assert approvals.directory()=={'records':[{'revision':2}]}


def test_failed_read_does_not_poison_the_next_snapshot(monkeypatch):
    def fail():raise ValueError('snapshot unavailable')
    monkeypatch.setattr(approvals,'_read_directory',fail)
    with pytest.raises(ValueError,match='unavailable'):approvals.directory()
    monkeypatch.setattr(approvals,'_read_directory',lambda:{'records':[]})
    assert approvals.directory()=={'records':[]}
