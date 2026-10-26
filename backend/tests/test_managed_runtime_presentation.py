import json
from agentscope_app import db
from agentscope_app.managed import controller as c
from agentscope_app.managed.records import runtime_templates
from test_managed_runtime_additive import bound

def test_template_retrieval_does_not_claim_the_candidate_referenced_it(bound):
    task=bound[0]
    with db.connect() as con:
        c.event(con,task,'pi_history','job-one',{'approved_only':True,'versions':[{'id':'template-one','hash':'frozen-hash'}]})
        assert runtime_templates(con,task,'job-one',[])=={'searched':True,'items':[]}
        assert runtime_templates(con,task,'another-job',[])=={'searched':False,'items':[]}

def test_template_name_requires_exact_retrieved_version_and_candidate_reference(bound):
    task=bound[0];record={'name':'禁止修改重要文件'}
    with db.connect() as con:
        con.execute('INSERT INTO bootstrap_history VALUES(?,?,?,?,?,?,?)',('template-one','text',json.dumps(record),'frozen-hash','approved','frozen-hash','test_sample'))
        c.event(con,task,'pi_history','job-one',{'approved_only':True,'versions':[{'id':'template-one','hash':'frozen-hash'}]})
        assert runtime_templates(con,task,'job-one',['history:template-one'])['items']==[{'id':'template-one','name':'禁止修改重要文件'}]
        con.execute('UPDATE bootstrap_history SET record_json=?,content_hash=? WHERE id=?',(json.dumps({'name':'其他版本名称'}),'new-hash','template-one'))
        result=runtime_templates(con,task,'job-one',['template-one'])
        assert result['items']==[{'id':'template-one','name':'已引用模板（名称未保存）'}]
        assert '其他版本名称' not in json.dumps(result,ensure_ascii=False)

def test_template_receipts_do_not_cross_task_boundaries(bound):
    with db.connect() as con:
        c.event(con,bound[0],'pi_history','same-job',{'approved_only':True,'versions':[]})
        assert runtime_templates(con,'foreign-task','same-job',[])=={'searched':False,'items':[]}

def test_generated_policy_pagination_skips_guidance_without_hiding_older_policies(bound,monkeypatch):
    from agentscope_app.managed import records as views
    task=bound[0]
    with db.connect() as con:
        for index in range(45):
            ident='policy-'+str(index) if index%3==0 else 'guidance-'+str(index)
            con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (ident,task,ident,index,'hash','{}',json.dumps({'decision':'restrict' if index%3==0 else 'guidance_only'}),'completed',db.now()))
    def children(con,task,state,row,*args):
        restrict=row['id'].startswith('policy-')
        return [{'id':row['id'],'stage':'runtime','effect':'restrict' if restrict else 'guidance','policy_type':'per_event' if restrict else 'semantic_only','targets':['/work/record.txt'] if restrict else [],'compilation':{'status':'compiled'},'loading':{}}]
    monkeypatch.setattr(views,'runtime_statement_records',children)
    first=views.records(task,'runtime',generated_only=True)
    second=views.records(task,'runtime',before=first['next_cursor'],generated_only=True)
    ids=[row['id'] for row in first['records']+second['records']]
    assert len(first['records'])==12 and len(second['records'])==3
    assert len(set(ids))==15 and all(ident.startswith('policy-') for ident in ids)
    assert second['next_cursor'] is None
