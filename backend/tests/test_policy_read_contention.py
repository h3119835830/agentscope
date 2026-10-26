from concurrent.futures import ThreadPoolExecutor,TimeoutError
from types import SimpleNamespace
import threading
import pytest
from agentscope_app.instances import workspace_references as refs,approval_views as approvals,template_configurations as tc
from agentscope_app.instances.configuration_approvals import read_snapshot
from test_policy_workspace_references import reference,world,generated
from test_template_configurations import config,Provider
from test_unified_policy_catalog import batch


def test_reader_waits_for_capacity_instead_of_reporting_a_policy_failure(monkeypatch):
    slots=threading.BoundedSemaphore(1);slots.acquire()
    monkeypatch.setattr(refs,'SLOTS',slots)
    monkeypatch.setattr(refs.os,'geteuid',lambda:0)
    monkeypatch.setattr(refs.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='{"files":[]}'))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(refs.run_reader,{},0,0)
        try:
            with pytest.raises(TimeoutError):future.result(timeout=.05)
        finally:slots.release()
        assert future.result(timeout=2)=={'files':[]}


def test_exhausted_queue_is_reader_unavailability_not_file_staleness(monkeypatch):
    class Full:
        def acquire(self,*,timeout):assert 0<timeout<=5;return False
        def release(self):pytest.fail('unacquired slot must not be released')
    monkeypatch.setattr(refs,'SLOTS',Full())
    with pytest.raises(refs.ReaderUnavailable):refs.run_reader({},0,0)


def proposals(reference):
    world,_,_=reference
    first={k:v for k,v in config().items() if k in ('template_id','template_version','name','parameters')}
    second={**first,'name':'预算保护','parameters':{'target':'/w/0/budget.csv'}}
    result,_=generated(reference,provider=Provider({'configurations':[first,second],'questions':[],'gaps':[]}))
    return tc.propose_batch(batch(world.a['id'],result['items']))['items']


def approval_rows(items):
    # Other modules leave independent runtime/history approvals in the shared
    # test database. Assert this test's exact approvals without borrowing them.
    rows={row['id']:row for row in approvals.directory()['records']}
    assert all(item['id'] in rows for item in items)
    return [rows[item['id']] for item in items]


def test_shared_receipts_are_checked_once_per_response_and_again_on_next_read(reference,monkeypatch):
    items=proposals(reference);_,root,_=reference;original=refs.verify_metadata;seen=[]
    def metadata(*args):seen.append(args);return original(*args)
    monkeypatch.setattr(refs,'verify_metadata',metadata)
    assert all(row['status']=='pending' for row in approval_rows(items))
    assert len(seen)==1
    approvals.detail(items[0]['id']);assert len(seen)==2
    full_original=refs.verify;full_reads=[]
    def verify(*args):full_reads.append(args);return full_original(*args)
    monkeypatch.setattr(refs,'verify',verify)
    @read_snapshot
    def write_boundary_checks():
        for item in items:tc.verify_proposal(item['id'],read_sources=True)
    write_boundary_checks();assert len(full_reads)==2
    (root/'README.md').write_text('changed after the previous response')
    assert all(row['status']=='stale' for row in approval_rows(items))
    assert len(seen)==4


def test_unavailable_reader_never_becomes_stale_file_or_approvable_policy(reference,monkeypatch):
    items=proposals(reference)
    def unavailable(*args):raise refs.ReaderUnavailable()
    monkeypatch.setattr(refs,'verify_metadata',unavailable)
    rows=approval_rows(items)
    assert all(row['status']=='blocked' and row['validation_unavailable'] and not row['can_approve'] for row in rows)
    assert all(row['revalidation'] is None for row in rows)
