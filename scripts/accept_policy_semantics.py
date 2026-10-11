"""Opt-in actual-provider/static-compiler acceptance on nonsensitive fixtures.

No Broker, service restart, application approval or production Agent is involved.
Run with configured AGENTSCOPE_HISTORY_LLM_* environment. Never exports credentials.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

root = Path(__file__).resolve().parents[1]
state = Path(tempfile.mkdtemp(prefix='as-sem-'))
for name in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_POLICY_DIR','AGENTSCOPE_LOG_DIR',
             'AGENTSCOPE_CORPUS_ROOT','AGENTSCOPE_SERVICE_HOME','AGENTSCOPE_RUNTIME_DIR','DSH_HOME'):
    os.environ.pop(name,None)
os.environ.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),
    AGENTSCOPE_SCOPE_WORKER='0',AGENTSCOPE_INSTANCE_WORKER='0',AGENTSCOPE_HISTORY_WORKER='0',
    ACTPLANE_BIN=str(root/'actplane/target/release/actplane'))
sys.path.insert(0,str(root/'backend'))
from agentscope_app import db
from agentscope_app.history import inputs, registry, generations, agent_context as context
from agentscope_app.history.pipeline import digest
from agentscope_app.instances import controller,sessions,policy_sources,dsl_policy,system_policy
db.init_db()
with db.connect() as con:dsl_policy.init(con)
workspace=state/'project';workspace.mkdir()
binary=state/'semprobe'
shutil.copyfile('/usr/bin/python3',binary);binary.chmod(0o755)
identity=dict(generation='semantic-fixture',pid=55090,start_ticks='100',domain_id=99090,host_id='fixture',boot_id='fixture')
row=dict(id='semantic-agent',agent_type='dsh',resources=[str(workspace)],mode='controlled',connected=True,
    runtime={**identity,'verified':True,'executable':str(binary)},**identity)
controller.detail=lambda ident:copy.deepcopy(row) if ident==row['id'] else (_ for _ in ()).throw(ValueError('Unknown fixture'))
policy_sources.process_executable=lambda *args:str(binary)
sessions.native_sessions=lambda _:dict(mapping_available=True,sessions=[dict(id='semantic-session',name='Fixture',mapping='native_registry',
    resource=str(workspace),execution_resource=str(workspace),process_ids=[55090],historical=False)])
system_policy.current=lambda:dict(phase='ready',revision=1)
dsl_policy.current=lambda *args,**kwargs:dict(phase='ready',revision=0,document_hash='a'*64)

cases=[
    ('readonly_zh','只读取 sales.csv 以获取报告数据，不写入、追加或覆盖该文件。',['sales.csv'],{'sales.csv':{'file_mutate'}},{'sales.csv':{'file_read'}}),
    ('readonly_en','Read input.json without changing it.',['input.json'],{'input.json':{'file_mutate'}},{'input.json':{'file_read'}}),
    ('readonly_paraphrase','可以查看 notes.txt，保持原始文件不变。',['notes.txt'],{'notes.txt':{'file_mutate'}},{'notes.txt':{'file_read'}}),
    ('deny_read','Do not read private.txt.',['private.txt'],{'private.txt':{'file_read'}},{}),
    ('deny_access','不允许访问 archive.txt。',['archive.txt'],{'archive.txt':{'file_read','file_mutate'}},{}),
    ('two_files','a.txt 可读不可改；不要读取 b.txt。',['a.txt','b.txt'],{'a.txt':{'file_mutate'},'b.txt':{'file_read'}},{'a.txt':{'file_read'}}),
]
tables=('tasks','policy_versions','history_deployments','instance_dsl_proposals','instance_policy_receipts','instance_dsl_scopes')
def authority():
    with db.connect() as con:
        return {t:digest([list(r) for r in con.execute('SELECT * FROM '+t+' ORDER BY rowid')]) for t in tables}
before=authority()
summary={'scope':'Actual provider + static ActPlane compiler; synthetic registered identity; no approval/application.',
         'state':str(state),'workspace':str(workspace),'probe_binary':str(binary),'cases':[]}
from agentscope_app.history.intent import ACCESS
from agentscope_app.history.llm import DeepSeekProvider
class Recorder:
    def __init__(self):self.provider=DeepSeekProvider();self.outputs=[]
    def generate(self,system,payload,version):
        result,meta=self.provider.generate(system,payload,version)
        self.outputs.append({'version':version,'output':result,'metadata':meta})
        (state/'provider-outputs.json').write_text(json.dumps(self.outputs,ensure_ascii=False,indent=2))
        return result,meta
provider=Recorder()
for name,text,files,blocked,preserved in cases:
    for path in files:(workspace/path).write_text('fixture-data\n')
    selection=context.snapshot(row['id'])
    v=inputs.create_input(dict(text=text,enforcement_level='per_event',context_requirement='project',
        agent_context=dict(instance_id=row['id'],session_id='semantic-session',context_hash=selection['context_hash'])),'semantic-acceptance')
    batch=generations.create(dict(statement_version_id=v['id'],request_key=uuid.uuid4().hex))
    print(json.dumps({'case':name,'stage':'generation_started'},ensure_ascii=False),flush=True)
    result=generations.execute(batch['id'],provider)
    found=generations.results(batch['id'])['items']
    assert len(found)==1,(name,result)
    item=found[0];artifact=item['artifact']
    actual={}
    if artifact:
        for rule in artifact['policy_ir']['rules']:
            for clause in rule['clauses']:
                assert clause['effect']=='block' and clause['when']['kind']=='label' and clause['when']['label']=='AGENT' and not clause['unless']
                path=Path(clause['pattern']);assert path.parent==workspace
                actual.setdefault(path.name,set()).add(ACCESS[clause['operation']])
    ok=item['compile_state']=='compiled' and actual==blocked and all(not actual.get(p,set()) & rights for p,rights in preserved.items())
    selected=context.selected_candidate(row['id'],item['artifact_id']) if ok else None
    stages=[dict(stage=s['stage'],result=s.get('result')) for s in result.get('steps',[])]
    record={'name':name,'request':text,'passed':ok,'compile_state':item['compile_state'],'actual':{p:sorted(v) for p,v in actual.items()},
        'statement':item['record']['statement'],'verified_targets':item['record']['resolved_context'].get('verified_targets'),
        'artifact':artifact,'run_id':batch['id'],'artifact_id':item['artifact_id'],
        'document':selected['document'] if selected else None,
        'review_status':item['review_status'],'artifact_review_status':item['artifact_review_status'],'eligible':item['eligible'],
        'error':item.get('error') or result.get('error'),'stages':stages}
    summary['cases'].append(record)
    summary['authority_unchanged']=authority()==before
    summary['authority_before']=before;summary['authority_after']=authority()
    output=state/'model-results.json';output.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'case':name,'passed':ok,'compile_state':item['compile_state'],'error':record['error']},ensure_ascii=False),flush=True)
    assert ok,name
assert summary['authority_unchanged']
assert all(c['review_status']==c['artifact_review_status']=='pending_review' and not c['eligible'] for c in summary['cases'])
print(json.dumps({'passed':len(summary['cases']),'authority_unchanged':True,'output':str(output)},ensure_ascii=False),flush=True)
