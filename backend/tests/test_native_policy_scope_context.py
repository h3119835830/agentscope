"""Native scope receives fresh kernel facts, not only broad typed grants."""
import json
from agentscope_app.instances import controller,store
from test_dsl_configuration import world
from test_session_loaded_policies import loaded

def test_native_scope_includes_loaded_document_without_application_authority(loaded):
    row=store.get(loaded.a['id'])
    before=store.get(row['id'])
    result=controller.native_loaded_context(row)
    assert result['state']=='verified'
    assert any(r['name']=='保护配置文件 v1' for r in result['records'])
    assert 'block read file' in json.dumps(result,ensure_ascii=False)
    assert store.get(row['id'])==before
    loaded.live[row['id']]['verified']=False
    assert not controller.native_loaded_context(row)['records']
