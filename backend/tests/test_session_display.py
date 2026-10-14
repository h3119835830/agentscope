import json
import pytest
from agentscope_app import db
from agentscope_app.instances import session_display as display, sessions, store, dsl_policy
from test_dsl_configuration import world, ADMIN


def cache(row,sid='same-session',name='Read README and summarize'):
    with db.connect() as con:
        con.execute('INSERT OR REPLACE INTO instance_session_cache VALUES(?,?,?,?,?)',
            (row['id'],sid,json.dumps({'id':sid,'name':name,'status':'stored','resource':row['resources'][0],'mapping':'native_session_database'}),row.get('generation'),db.now()))


def test_name_change_is_metadata_only_and_same_session_id_never_crosses_instances(world):
    cache(world.a);cache(world.b,name='Other Agent task')
    before=store.get(world.a['id']);policy=dsl_policy.current(world.a['id'])
    result=display.rename(world.a['id'],'same-session','读取项目说明并总结','Read README and summarize')
    assert result['metadata_only'] and result['revision']==1
    a=sessions.native_sessions({**before,'connected':False})['sessions'][0]
    b=sessions.native_sessions({**world.b,'connected':False})['sessions'][0]
    assert a['name']=='读取项目说明并总结' and a['native_name']=='Read README and summarize'
    assert b['name']=='Other Agent task'
    assert store.get(world.a['id'])==before and dsl_policy.current(world.a['id'])==policy and not world.calls


def test_name_update_requires_existing_session_and_compare_and_swap(world):
    cache(world.a)
    with pytest.raises(ValueError,match='不属于'):display.rename(world.a['id'],'foreign','中文标题',None)
    display.rename(world.a['id'],'same-session','第一次修改','Read README and summarize')
    with pytest.raises(ValueError,match='已经变化'):display.rename(world.a['id'],'same-session','过期修改','Read README and summarize')
    assert display.rename(world.a['id'],'same-session','第二次修改','第一次修改')['revision']==2
    with db.connect() as con:assert con.execute('SELECT COUNT(*) FROM instance_session_display_names WHERE instance_id=?',(world.a['id'],)).fetchone()[0]==1
    assert not world.calls


@pytest.mark.parametrize('value',[' ','第一行\n第二行','\x00名称','x'*121])
def test_invalid_names_are_rejected_without_mutating_authority(world,value):
    cache(world.a)
    with pytest.raises(ValueError):display.rename(world.a['id'],'same-session',value,'Read README and summarize')
    assert not world.calls


def test_name_api_is_administrator_only_and_works_for_stopped_historical_session(world):
    cache(world.a)
    path='/api/agent-instances/'+world.a['id']+'/sessions/same-session/name'
    body={'name':'历史中文会话','expected_name':'Read README and summarize'}
    assert world.client.post(path,json=body).status_code==401
    response=world.client.post(path,headers=ADMIN,json=body)
    assert response.status_code==200 and response.json()['metadata_only']
    assert store.get(world.a['id'])['gate']=='closed' and not world.calls
    assert world.client.post(path,headers=ADMIN,json=body).status_code==409


def test_name_change_does_not_replace_native_cache_or_forge_runtime_mapping(world):
    cache(world.a,name=None)
    display.rename(world.a['id'],'same-session','未命名会话',None)
    with db.connect() as con:
        raw=json.loads(con.execute('SELECT metadata_json FROM instance_session_cache WHERE instance_id=?',(world.a['id'],)).fetchone()[0])
    assert raw['name'] is None
    page=sessions.native_sessions({**world.a,'connected':False})
    assert page['mapping_available'] is False and page['sessions'][0]['historical']
    assert page['sessions'][0]['process_ids']==[] and page['sessions'][0]['name']=='未命名会话'
