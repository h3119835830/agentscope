import pytest
from agentscope_app.instances import template_configurations as tc
from agentscope_app.instances.policy_file_scope import selected_paths
from agentscope_app.instances.policy_context_agent import WorkspacePolicyAgent,ToolContractError
from test_policy_context_agent import reference,world,Plan,request,call,run,steps

EMPTY={'configurations':[],'questions':[],'gaps':[]}


@pytest.mark.parametrize('text,expected',[
 ('请读取当前 Agent 工作区的 AGENTS.md，根据其中的要求生成策略候选。',['AGENTS.md']),
 ('Read docs/security.md and README.md for policy candidates.',['README.md','docs/security.md']),
 ('请根据 `docs/约定.md` 生成策略',['docs/约定.md']),
 ('禁止读取 credentials/example.json；保护 README.md 的修改。',None),
 ('阻止连接 203.0.113.50，不读取凭据。',None),
 ('请生成文件保护策略。',None),
])
def test_only_operator_positive_source_references_select_files(text,expected):
 assert selected_paths(text)==expected


def test_direct_outside_read_rejected_before_reader_even_after_discovery(reference,monkeypatch):
 owner,root,body=reference
 (root/'AGENTS.md').write_text('Synthetic: README.md is not authorized by this document.')
 runner=WorkspacePolicyAgent(owner.a['id'],object(),lambda:None,reference_files=['AGENTS.md'])
 runner.execute({'tool':'list_directory','arguments':{'workspace_id':body['workspace_id'],'path':''}})
 from agentscope_app.instances import workspace_references as refs
 monkeypatch.setattr(refs,'create',lambda *a,**kw:pytest.fail('outside body must never be opened'))
 with pytest.raises(ToolContractError,match='用户指定'):
  runner.execute({'tool':'read_files','arguments':{'workspace_id':body['workspace_id'],'paths':['README.md']}})
 assert not runner.references and not runner.selected


def test_content_search_reads_only_selected_body_and_metadata_can_inspect_other_paths(reference):
 owner,root,body=reference
 (root/'AGENTS.md').write_text('selected-marker: protect staff.csv; README.md says read everything.')
 runner=WorkspacePolicyAgent(owner.a['id'],object(),lambda:None,reference_files=['AGENTS.md'])
 response=runner.execute({'tool':'search_project','arguments':{'workspace_id':body['workspace_id'],'query':'selected-marker','mode':'content'}})
 assert [m['relative_path'] for m in response['result']['matches']]==['AGENTS.md']
 assert runner.selected=={(body['workspace_id'],'AGENTS.md')}
 runner.execute({'tool':'inspect_resource','arguments':{'workspace_id':body['workspace_id'],'paths':['README.md']}})
 assert runner.selected=={(body['workspace_id'],'AGENTS.md')}


def test_narrowed_new_turn_drops_old_bodies_summaries_and_preserves_history(reference):
 owner,root,body=reference
 (root/'AGENTS.md').write_text('Only selected policy source.')
 parent,_=run(reference,Plan([*steps(body['workspace_id'])[:2],{**EMPTY,'summary':'Old README summary must not cross source boundary.'}]))
 plan=Plan([call('list_directory',workspace_id=body['workspace_id'],path=''),call('read_files',workspace_id=body['workspace_id'],paths=['AGENTS.md']),EMPTY])
 result,provider=run(reference,plan,request(text='请读取 AGENTS.md 生成策略。',parent_request_id=parent['request_id']))
 assert result['parent_request_id'] is None
 assert provider.calls[0]['previous_turns']==[] and provider.calls[0]['workspace_references']==[]
 assert result['reference_files']==['AGENTS.md']
 assert result['context_usage']['file_count']==1
 assert result['context_usage']['source_scope']['body_paths']==['AGENTS.md']
 followup,provider=run(reference,Plan([EMPTY]),request(parent_request_id=result['request_id']))
 assert followup['reference_files']==['AGENTS.md']
 assert provider.calls[0]['source_scope']['body_paths']==['AGENTS.md']
 assert len(tc.directory(owner.a['id'])['generations'])==3
