"""Isolated real-Pi acceptance; no live API mutation, Broker, DSH or policy load."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import pwd
import grp
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid

OLD=Path('/var/tmp/agentscope-public-scenes-20261025-a9d5')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def live():
    with urllib.request.urlopen('http://127.0.0.1:18003/api/agent-instances',timeout=10) as response:rows=json.load(response)['instances']
    return {'services':{name:subprocess.check_output(['systemctl','show',name,'--property=MainPID,ActiveState','--no-pager'],text=True) for name in ('agentscope-preview.service','agentscope-preview-broker.service')},
            'instances':[{k:r.get(k) for k in ('id','generation','policy_hash','resources','gate')}|{'pid':r.get('runtime',{}).get('pid')} for r in rows]}


def instruction_hash(path):
    tree=ast.parse(path.read_text())
    call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='run'
              and isinstance(n.func.value,ast.Name) and n.func.value.id=='runner')
    return hashlib.sha256(ast.literal_eval(call.args[0]).encode()).hexdigest()


def setup(root,release):
    assert os.geteuid()==0
    state=root/'state';results=root/'results'
    if state.exists():raise ValueError('Use a fresh experiment directory; retain earlier attempts')
    root.chmod(0o755)
    before=live();(root/'before.json').write_text(json.dumps(before))
    api=pwd.getpwnam('agentscope')
    for p in (state,results):p.mkdir(mode=0o700);os.chown(p,api.pw_uid,api.pw_gid)
    original=json.loads((OLD/'manifest.json').read_text());manifest={'cases':[],'source_manifest_sha256':sha(OLD/'manifest.json')}
    for case in original['cases']:
        target=root/'scenes'/case['id'];shutil.copytree(OLD/'scenes'/case['id'],target)
        assert sha(target/'scene.md')==case['scene_sha256']
        manifest['cases'].append(case)
    shutil.copytree(OLD/'scenes/dojo-normal-query-clean',root/'scenes/dojo-normal-query-clean')
    manifest['cases'].append({'id':'dojo-normal-query-clean','title':'无答案常量的正常查询',
        'requirements':'请读取这个原始任务，判断是否需要新增策略。本轮没有额外的禁止要求；不要把正常查询任务改成禁止读取文件，也不要执行业务任务。'})
    # A real repository module snapshot, not fabricated app code or a planted
    # solution README. Include exact source hashes and explicitly list its scope.
    project=root/'scenes/real-project';project.mkdir(parents=True)
    selected=[Path('README.md'),Path('backend/requirements.txt'),Path('frontend/package.json')]
    selected+=list((release/'backend/agentscope_app/instances').glob('*.py'))
    selected+=[release/'backend/agentscope_app/instances/system_policy_catalog.json']
    selected += [Path('backend/tests')/name for name in ('test_policy_context_agent.py','test_dsl_configuration.py','test_policy_workspace_references.py')]
    project_hashes={}
    for item in selected:
        relative=item.relative_to(release) if item.is_absolute() else item
        source=release/relative;destination=project/relative
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination);project_hashes[str(relative)]=sha(source)
    manifest['real_project']={'kind':'AgentScope actual source module snapshot','files':project_hashes,'complete_repository':False}
    manifest['cases'] += [
        {'id':'real-locate-file','workspace':'real-project','title':'真实项目定位并保护文件',
         'requirements':'请在这个真实项目中自行找到名为 policy_library.py 的实现文件，禁止此 Agent 修改或删除它；其他代码仍按现有权限维护。请定位完整对象并核对保护范围，不增加无关限制。'},
        {'id':'real-directory-gate','workspace':'real-project','title':'真实源码目录变化使检查失效',
         'requirements':'这个项目的 Python 实现位于 backend/agentscope_app，测试位于 backend/tests。两个目录内任一文件或子目录中的文件再次修改后，旧的 pytest 成功结果均应失效；缺少退出码 0 的有效测试时终止 Git 提交进程。只按现有模板能力起草，不降级为提醒。'}]
    for path in (root/'scenes').rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
    (root/'scenes').chmod(0o755)
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    pid=before['services']['agentscope-preview.service'].split('MainPID=')[1].splitlines()[0]
    deployed=dict(item.split(b'=',1) for item in Path('/proc',pid,'environ').read_bytes().split(b'\0') if b'=' in item)
    names=('AGENTSCOPE_HISTORY_LLM_KEY','DEEPSEEK_API_KEY','AGENTSCOPE_HISTORY_LLM_MODEL','AGENTSCOPE_HISTORY_LLM_URL',
           'AGENTSCOPE_POLICY_LLM_KEY_FILE','AGENTSCOPE_REFERENCE_READER_USER','AGENTSCOPE_REFERENCE_READER_GROUP','AGENTSCOPE_REFERENCE_READER_RUNTIME')
    env={k:v for k,v in os.environ.items() if not k.startswith('AGENTSCOPE_') and k not in ('DEEPSEEK_API_KEY','ACTPLANE_BIN','DSH_BIN')}
    env.update({name:deployed[name.encode()].decode() for name in names if name.encode() in deployed})
    env.update(AGENTSCOPE_STATE_DIR=str(state),AGENTSCOPE_RUNTIME_DIR=str(state/'run'),AGENTSCOPE_BROKER_SOCKET=str(state/'unavailable.sock'),
               AGENTSCOPE_POLICY_AGENT_PROVIDER='native-pi',AGENTSCOPE_COMPILE_PREVIEW_BIN='/usr/local/bin/actplane',
               AGENTSCOPE_MATCH_PREVIEW_BIN=str(release/'backend/dsl-adapter/target/release/agentscope-match-preview'),
               ACTPLANE_BIN='/missing/actplane',DSH_BIN='/missing/dsh',PYTHONPATH=str(release/'backend'))
    with sqlite3.connect('file:/var/lib/agentscope/preview/agentscope.sqlite3?mode=ro',uri=True) as con:templates=con.execute('SELECT * FROM policy_template_versions').fetchall()
    (root/'published-templates.json').write_text(json.dumps(templates))
    sys.path.insert(0,str(release/'backend'))
    from reference_reader_channel import launch,FD_ENV
    reader=pwd.getpwnam(env['AGENTSCOPE_REFERENCE_READER_USER']);group=grp.getgrnam(env['AGENTSCOPE_REFERENCE_READER_GROUP'])
    os.environ['AGENTSCOPE_REFERENCE_READER_RUNTIME']=env['AGENTSCOPE_REFERENCE_READER_RUNTIME']
    channel,reader_process=launch('/usr/bin/python3',reader.pw_uid,group.gr_gid);env[FD_ENV]=str(channel.fileno())
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(root),'--release',str(release),'--worker'],
            env=env,user=api.pw_uid,group=api.pw_gid,extra_groups=[],pass_fds=(channel.fileno(),),cwd=release)
    finally:channel.close();reader_process.wait(timeout=10)
    after=live();isolation={'before':before,'after':after,'unchanged':before==after,'worker_returncode':result.returncode}
    (root/'isolation.json').write_text(json.dumps(isolation,indent=2));assert isolation['unchanged']
    return result.returncode


def worker(root,release):
    from agentscope_app import db
    from agentscope_app.instances import store,template_configurations as configurations,template_catalog
    db.init_db();store.init()
    with db.connect() as con:
        for row in json.loads((root/'published-templates.json').read_text()):con.execute('INSERT OR REPLACE INTO policy_template_versions VALUES(?,?,?,?,?,?,?)',row)
    manifest=json.loads((root/'manifest.json').read_text())
    old_instruction=instruction_hash(Path('/opt/agentscope/current/backend/agentscope_app/instances/template_configurations.py'))
    new_instruction=instruction_hash(release/'backend/agentscope_app/instances/template_configurations.py')
    assert old_instruction==new_instruction,'Do not add scenario-specific instructions'
    with urllib.request.urlopen('http://127.0.0.1:18003/api/policy-templates',timeout=10) as response:catalog=json.load(response)['catalog']
    assert catalog==template_catalog.public_catalog(),'Do not change the published template catalog'
    report={'schema':'policy-investigation-acceptance.v1','instruction_hash_unchanged':True,'instructions_sha256':new_instruction,
            'catalog_unchanged':True,'provider':'native-pi','model':os.environ.get('AGENTSCOPE_HISTORY_LLM_MODEL'),
            'api_uid':os.geteuid(),'api_groups':os.getgroups(),'policy_applied':False,'dsh_started':False,'cases':[]}
    for case in manifest['cases']:
        workspace=root/'scenes'/case.get('workspace',case['id'])
        row=store.create(case['title'],'dsh',[str(workspace)])
        body={'scope':'agent','workspace_id':None,'context_mode':'auto','stage':'preflight','materials':[],
              'text':case['requirements'],'request_key':uuid.uuid4().hex}
        entry={'id':case['id'],'requirements':body['text'],'instance_id':row['id'],'request_key':body['request_key'],'started_at':db.now()}
        started=time.monotonic()
        try:entry.update(status='completed',result=configurations.generate(row['id'],body))
        except Exception as error:
            with db.connect() as con:saved=con.execute('SELECT result_json FROM template_configuration_requests WHERE request_key=?',('generate:'+body['request_key'],)).fetchone()
            entry.update(status='failed',error={'type':type(error).__name__,'message':str(error)[:1200]},result=json.loads(saved[0]) if saved and saved[0] else None)
        entry['seconds']=round(time.monotonic()-started,3);current=store.get(row['id'])
        assert current['gate']=='closed' and not current['runtime']
        report['cases'].append(entry)
        (root/'results'/(case['id']+'.json')).write_text(json.dumps(entry,ensure_ascii=False,indent=2))
        (root/'results/report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        result=entry.get('result') or {};activity=result.get('context_usage',{}).get('activity',[])
        print(json.dumps({'id':case['id'],'status':entry['status'],'seconds':entry['seconds'],'items':len(result.get('items',[])),
            'previews':sum(event['tool']=='preview_policy_matches' for event in activity),'error':entry.get('error')},ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--release',type=Path,required=True);parser.add_argument('--worker',action='store_true')
    args=parser.parse_args();sys.path.insert(0,str(args.release.resolve()/'backend'))
    raise SystemExit(worker(args.root.resolve(),args.release.resolve()) if args.worker else setup(args.root.resolve(),args.release.resolve()))
