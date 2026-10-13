"""Permission preservation, compiler aliases and approval guards, not keyword rules."""
import copy
import json
import uuid
import pytest
from test_agent_policy_context import world, create, Provider
from agentscope_app import db, main
from agentscope_app.history import generations, registry, agent_context, intent
from agentscope_app.policy_ir import PolicyIR


class SemanticProvider(Provider):
    def __init__(self, targets, permissions, operations, bad_first=False):
        super().__init__()
        self.targets, self.permissions, self.operations = targets, permissions, operations
        self.bad_first = bad_first
        self.ir_calls = 0
        self.intent_calls = 0
        self.payloads = []

    def generate(self, system, payload, version):
        self.payloads.append((version, copy.deepcopy(payload)))
        if version == intent.REVIEW_VERSION:
            return payload['first_pass'], {}
        if version == 'agent-environment-targets-v1':
            return {'targets':[{'path':p,'evidence':p} for p in self.targets], 'questions':[]}, {}
        if version == intent.VERSION:
            self.intent_calls += 1
            return {'permissions':[dict(action={'file_read':'read','file_mutate':'modify'}.get(access,access), pattern='/w/0/'+path, decision='forbid' if decision=='restrict' else 'permit',
                evidence=payload['SOURCE']['selected_quote']) for path, access, decision in self.permissions]}, {}
        if version == 'history-policy-ir-v1':
            self.ir_calls += 1
            operations = self.operations + ([(self.targets[0], 'open')] if self.bad_first and self.ir_calls == 1 else [])
            return {'rules':[{'name':'policy','reason':payload['statement']['statement']['text_original'],
                'clauses':[dict(operation=op,pattern='/w/0/'+p) for p,op in operations]}]}, {}
        return super().generate(system, payload, version)


def run(world, text, provider):
    for name in provider.targets:
        (world.root/name).write_text('fixture data\n')
    version = create(world, text)
    batch = generations.create(dict(statement_version_id=version.id,request_key=uuid.uuid4().hex))
    compiled = []
    world.monkeypatch.setattr(main,'compile_policy',lambda yaml,*args:(compiled.append(yaml) or 'compiled',{},None))
    generations.execute(batch['id'],provider)
    return batch, generations.results(batch['id'])['items'][0], compiled


@pytest.mark.parametrize('text,path',[
    ('只读取 sales.csv 以获取报告数据，不写入、追加或覆盖该文件。','sales.csv'),
    ('Read input.json without changing it.','input.json'),
    ('可以查看 notes.txt，保持原始文件不变。','notes.txt'),
])
def test_preserved_read_and_restricted_mutation_survive_full_chain(world,text,path):
    p=SemanticProvider([path],[(path,'file_read','preserve'),(path,'file_mutate','restrict')],[(path,'write'),(path,'unlink')])
    _, row, compiled=run(world,text,p)
    assert row['compile_state']=='compiled' and len(compiled)==1
    assert row['review_status']==row['artifact_review_status']=='pending_review'
    assert 'block open' not in compiled[0] and 'block read' not in compiled[0]
    assert row['artifact']['policy_record']['metadata']['semantic_check']['state']=='verified'
    assert not row['eligible']
    agent_context.selected_candidate('agent-a',row['artifact_id'])
    with db.connect() as con:
        for table in ('instance_dsl_proposals','instance_policy_receipts','tasks'):
            assert con.execute('SELECT count(*) FROM '+table).fetchone()[0]==0


def test_legacy_model_hook_generation_is_bypassed_and_wrong_ir_fails_validation(world):
    p=SemanticProvider(['table.csv'],[('table.csv','file_read','preserve'),('table.csv','file_mutate','restrict')],
                       [('table.csv','write')],bad_first=True)
    _,row,compiled=run(world,'table.csv 仅用于查看，不能改动。',p)
    assert row['compile_state']=='compiled' and len(compiled)==1
    assert p.intent_calls==1 and p.ir_calls==0
    checked=row['artifact']['policy_record']['metadata']['semantic_check']
    bad=copy.deepcopy(row['artifact']['policy_ir'])
    bad['rules'][0]['clauses'].append(dict(operation='open',pattern='/w/0/table.csv'))
    with pytest.raises(ValueError,match='不一致'):
        intent.validate(PolicyIR.model_validate(bad),checked,registry.load_statement(row['statement_version_id']))
    # The source stage never receives the generated IR or its error diagnostics.
    source_payload=next(value for v,value in p.payloads if v==intent.VERSION)
    assert 'compiler_diagnostic' not in source_payload and 'policy_ir' not in source_payload


def test_persistent_conflict_never_compiles_selects_or_approves(world):
    p=SemanticProvider(['a.txt'],[('a.txt','file_read','preserve'),('a.txt','file_mutate','restrict'),('a.txt','file_read','restrict')],[])
    batch,row,compiled=run(world,'允许读取 a.txt，不得修改。',p)
    assert row['compile_state']=='invalid_candidate' and compiled==[]
    assert row['artifact']['actplane_dsl'] is None and p.ir_calls==0 and p.intent_calls==1
    with pytest.raises(ValueError):agent_context.selected_candidate('agent-a',row['artifact_id'])
    item=dict(statement_version_id=row['statement_version_id'],expected_statement_hash=row['statement_hash'],artifact_id=row['artifact_id'],expected_artifact_hash=row['artifact_hash'])
    with pytest.raises(ValueError):generations.final_review(batch['id'],[item],'approve','tester')


def test_multiple_objects_cannot_exchange_permissions_or_expand_scope(world):
    permissions=[('a.txt','file_read','preserve'),('a.txt','file_mutate','restrict'),('b.txt','file_read','restrict'),('a.txt','file_read','restrict')]
    p=SemanticProvider(['a.txt','b.txt'],permissions,[('a.txt','write'),('b.txt','open'),('a.txt','read')])
    _,row,compiled=run(world,'a.txt 可读不可改；不要读取 b.txt。',p)
    assert not compiled and row['artifact']['actplane_dsl'] is None


def test_explicit_truncation_is_a_source_action_in_the_existing_mutation_group(world):
    context=agent_context.snapshot('agent-a')['resolved_context']
    source=intent.SourceDescription(permissions=[intent.SourcePermission(
        action='truncate',decision='forbid',pattern='/w/0/sales.csv',evidence='禁止截断 sales.csv')])
    normalized=intent.normalize(source,context)
    assert normalized.permissions[0].access=='file_mutate'
    assert normalized.permissions[0].decision=='restrict' and not normalized.unresolved


@pytest.mark.parametrize('op',['read','open'])
def test_deny_read_uses_read_access_group_without_inventing_mutation_restriction(world,op):
    p=SemanticProvider(['secret.txt'],[('secret.txt','file_read','restrict')],[('secret.txt',op)])
    _,row,compiled=run(world,'不要读取 secret.txt。',p)
    assert row['compile_state']=='compiled' and len(compiled)==1


@pytest.mark.parametrize('change',[
    lambda c:c.update(effect='notify'),lambda c:c.update(unless={'kind':'target','pattern':'/w/0/a.txt'}),
    lambda c:c.update(when={'kind':'true'}),lambda c:c.update(pattern='/w/0/b.txt')])
def test_restriction_effect_condition_exception_and_target_must_match(world,change):
    v=create(world,'不得修改 a.txt。')
    frozen=intent.extract(v,SemanticProvider(['a.txt'],[('a.txt','file_mutate','restrict')],[]))
    clause={'operation':'write','pattern':'/w/0/a.txt'};change(clause)
    ir=PolicyIR.model_validate({'rules':[{'name':'one','reason':'source','clauses':[clause]}]})
    with pytest.raises(ValueError,match='不一致'):intent.validate(ir,frozen,v)


def test_old_compiled_candidate_without_semantic_check_is_not_reusable(world):
    p=SemanticProvider(['a.txt'],[('a.txt','file_mutate','restrict')],[('a.txt','write')])
    batch,row,_=run(world,'不得修改 a.txt。',p)
    data=copy.deepcopy(row['artifact']);data['policy_record']['metadata'].pop('semantic_check')
    from agentscope_app.history.pipeline import digest
    with db.connect() as con:
        con.execute('UPDATE history_artifacts SET artifact_json=?,content_sha256=? WHERE id=?',(json.dumps(data),digest(data),row['artifact_id']))
    with pytest.raises(ValueError,match='重新生成'):agent_context.selected_candidate('agent-a',row['artifact_id'])
    updated=generations.results(batch['id'])['items'][0]
    assert '原文权限校验未通过，请重新生成' in updated['submission_blockers']


def test_same_abi_group_cannot_simultaneously_preserve_and_deny(world):
    v=create(world,'a.txt 不得写入，但必须允许删除。')
    p=SemanticProvider(['a.txt'],[('a.txt','file_mutate','preserve'),('a.txt','file_mutate','restrict')],[])
    frozen=intent.extract(v,p)
    ir=PolicyIR.model_validate({'rules':[{'name':'one','reason':'source','clauses':[{'operation':'write','pattern':'/w/0/a.txt'}]}]})
    with pytest.raises(ValueError,match='保留'):intent.validate(ir,frozen,v)


def test_fabricated_source_evidence_is_rejected(world):
    class Forged(SemanticProvider):
        def generate(self,*args):
            value,meta=super().generate(*args)
            if args[2]==intent.VERSION:value['permissions'][0]['evidence']='not present in the source'
            return value,meta
    p=Forged(['a.txt'],[('a.txt','file_mutate','restrict')],[('a.txt','write')])
    batch,row,compiled=run(world,'不得修改 a.txt。',p)
    assert not compiled and row['artifact'] is None


def test_wrongly_rendered_dsl_cannot_pass_stored_contract(world):
    p=SemanticProvider(['a.txt'],[('a.txt','file_mutate','restrict')],[('a.txt','write')])
    _,row,_=run(world,'不得修改 a.txt。',p)
    data=copy.deepcopy(row['artifact']);data['actplane_dsl']+='\n  block read file "/w/0/a.txt" if AGENT'
    with pytest.raises(ValueError,match='DSL'):intent.check_artifact(data,registry.load_statement(row['statement_version_id']))


def test_single_review_contract_does_not_inherit_document_atomic_splitting():
    from agentscope_app.history.pipeline import SINGLE_COMPLETENESS_PROMPT, COMPLETENESS_PROMPT
    assert 'Split composite policies' not in SINGLE_COMPLETENESS_PROMPT
    assert 'exactly one reviewed candidate' in SINGLE_COMPLETENESS_PROMPT
    assert 'Split composite policies' in COMPLETENESS_PROMPT


def test_source_review_corrects_missing_negation_before_deterministic_lowering(world):
    class MissingAction(SemanticProvider):
        def generate(self,system,payload,version):
            if version==intent.VERSION:
                value,meta=super().generate(system,payload,version)
                return {'permissions':value['permissions'][:1]},meta
            if version==intent.REVIEW_VERSION:
                assert len(payload['first_pass']['permissions'])==1
                return {'permissions':[dict(action='read',pattern='a.txt',decision='permit',evidence=payload['SOURCE']['selected_quote']),
                    dict(action='modify',pattern='a.txt',decision='forbid',evidence=payload['SOURCE']['selected_quote'])]},{}
            return super().generate(system,payload,version)
    p=MissingAction(['a.txt'],[('a.txt','file_read','preserve'),('a.txt','file_mutate','restrict')],[])
    _,row,compiled=run(world,'读取 a.txt，不能改动。',p)
    assert row['compile_state']=='compiled' and len(compiled)==1 and 'block write' in compiled[0]
    assert 'block read' not in compiled[0] and p.ir_calls==0


def test_equivalent_source_actions_are_coalesced_without_losing_source_evidence(world):
    class Actions(SemanticProvider):
        def generate(self,system,payload,version):
            if version==intent.VERSION:
                return {'permissions':[dict(action=a,pattern='a.txt',decision='forbid',evidence=payload['SOURCE']['selected_quote'])
                    for a in ('write','append','overwrite')]},{}
            return super().generate(system,payload,version)
    p=Actions(['a.txt'],[],[])
    _,row,compiled=run(world,'不要写入、追加或覆盖 a.txt。',p)
    assert row['compile_state']=='compiled' and compiled[0].count('block write')==1
    checked=row['artifact']['policy_record']['metadata']['semantic_check']
    assert len(checked['source_permissions']['permissions'])==3
