from agentscope_app.instances import approval_views,template_configurations as tc,dsl_policy as dsl
from test_dsl_configuration import world
from test_template_configurations import clean_templates,config,proposal


def test_approval_displays_each_exact_selected_revision_after_later_edits(world):
 first=tc.save(world.a['id'],config(name='员工文件保护'))
 second=tc.save(world.a['id'],config(name='预算文件保护',parameters={'target':'/w/0/budget.csv'}))
 base=dsl.current(world.a['id'])
 result=tc.propose_batch({'scope_id':world.a['id'],'selections':[{'id':r['id'],'revision':r['revision']} for r in (first,second)],
  'operation':'apply','acknowledge_coverage':True,'base_hash':base['document_hash'],'base_revision':base['revision'],'request_key':'record-batch-test'})
 details=[approval_views.detail(p['id']) for p in result['items']]
 assert all(len(detail['configuration_records'])==1 for detail in details)
 assert [detail['configuration_records'][0]['name'] for detail in details]==['员工文件保护','预算文件保护']
 tc.save(world.a['id'],config(name='之后修改的名字',base_revision=1,parameters={'target':'/w/0/other.csv'}),first['id'])
 frozen=[approval_views.detail(p['id'])['configuration_records'] for p in result['items']]
 assert frozen==[detail['configuration_records'] for detail in details]
 assert not world.calls
