from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest
from agentscope_app.instances.product_status import current_load, runtime, configuration, display_identities


def evidence():
    identity = dict(generation='run-1',pid=101,start_ticks='birth-1',boot_id='boot-1',host_id='host-1',domain_id=900)
    artifact = dict(loaded=True,bundle_hash='actual-v2',dsl_hash='dsl-v2',binding=identity)
    row = dict(id='instance-a',mode='controlled',gate='open',connected=True,verified=True,status='running',
               **identity,last_checked_at=datetime.now(timezone.utc).isoformat(),evidence_age_seconds=0,
               runtime={**identity,'policy_artifact':artifact,'dsl_hash':'dsl-v2'},dsl_hash='dsl-v2')
    return row,dict(instance_id=row['id'],generation='run-1',artifact=artifact,bundle_hash='actual-v2',dsl_hash='dsl-v2')


@pytest.mark.parametrize('gate', ['open','paused'])
def test_gate_is_not_loading_evidence(gate):
    row, receipt = evidence()
    row['gate'] = gate
    assert current_load(row,receipt)['state']=='loaded'
    assert current_load(row,None)['state']=='unverified'
    row['evidence_age_seconds']=8
    assert current_load(row,receipt)['state']=='unverified'
    assert runtime(row)['state']=='unknown'


@pytest.mark.parametrize('key', ['generation','domain_id','pid','start_ticks','boot_id','host_id'])
def test_missing_or_reused_identity_is_never_current(key):
    row, receipt = evidence()
    del receipt['artifact']['binding'][key]
    assert current_load(row,receipt)['state']=='unverified'
    row, receipt = evidence()
    row[key]='replacement'
    assert current_load(row,receipt)['state']=='unverified'


def test_hash_restart_failure_and_stop():
    row, receipt = evidence()
    other=deepcopy(receipt)
    other['bundle_hash']='desired-v3'
    assert current_load(row,other)['state']=='unverified'
    row['status']='unknown'
    assert runtime(row)['state']=='unknown'
    assert current_load(row,receipt)['state']=='unverified'
    row.update(gate='closed',connected=False,runtime={})
    assert runtime(row)['state']=='stopped'
    assert current_load(row,receipt)['state']=='stopped'


def test_expiry_and_missing_age_are_fail_closed():
    row, receipt = evidence()
    row.pop('evidence_age_seconds')
    assert current_load(row,receipt)['state']=='unverified'
    row['evidence_age_seconds']=0
    row['last_checked_at']=(datetime.now(timezone.utc)-timedelta(seconds=9)).isoformat()
    assert current_load(row,receipt)['state']=='unverified'


def test_explicit_empty_dsl_still_verifies_the_actual_startup_bundle():
    row,receipt=evidence()
    for value in (row,row['runtime'],receipt,receipt['artifact']):
        value['dsl_hash']=None
    assert current_load(row,receipt)['state']=='loaded'
    del row['dsl_hash']
    assert current_load(row,receipt)['state']=='unverified'


def test_progress_and_applied_version_are_distinct():
    value=configuration(dict(status='pending',revision=3,applied_revision=2,archived=True))
    assert value['label']=='待审批' and value['applied_revision']==2
    assert value['lifecycle']['archived'] and not value['lifecycle']['disabled']
    assert configuration(dict(status='approved'))['label']=='待应用'
    assert configuration(dict(status='draft',applied=True))['label']=='已应用'


def test_duplicate_names_and_unnamed_instances_are_stable_not_pid():
    rows=[dict(id='instance-aaaaaaaa1',name='工作助手',agent_type='dsh',pid=None),
          dict(id='instance-aaaaaaaa2',name='工作助手',agent_type='dsh',pid=None),
          dict(id='instance-cccccccc',name='',agent_type='dsh')]
    display_identities(rows)
    labels=[r['display_name'] for r in rows]
    assert len(set(labels))==3 and all('DeepSeek Harness' in n for n in labels)
    for r in rows:r['pid']=123
    display_identities(rows)
    assert [r['display_name'] for r in rows]==labels
