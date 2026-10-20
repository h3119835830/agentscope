"""Print a manifest only for successful exact new-label template contracts."""
import hashlib,json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
report_path=Path(sys.argv[1]).resolve(strict=True)
report=json.loads(report_path.read_text())
assert report['passed'] and len(report['cases'])==6
os.environ['AGENTSCOPE_STATE_DIR']=tempfile.mkdtemp(prefix='as-label-manifest-')
for key in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_POLICY_DIR','AGENTSCOPE_LOG_DIR'):
    os.environ.pop(key,None)
sys.path.insert(0,str(ROOT/'backend'))
from agentscope_app import db
from agentscope_app.instances import template_catalog,template_versions,template_support
db.init_db()
with db.connect() as con:template_versions.init(con)
manifest={k:report[k] for k in ('binary_sha256','kernel_release')}
manifest.update(schema='agentscope.template-runtime-evidence.v1',date='2026-10-20',
                evidence_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),templates={})
for name in ('SECRET-EGRESS','SYS-secret-egress'):
    selected=[c for c in report['cases'] if c['template_id']==name]
    assert len(selected)==3 and all(c['passed'] for c in selected)
    assert {c['effect'] for c in selected}=={'block','notify','kill'}
    version={c['version'] for c in selected};assert len(version)==1
    definition=template_catalog.get(name,version.pop())
    assert definition.get('label_contract')=='explicit-secret-sources.v1'
    assert all('source SECRET = file' in c['dsl'] and 'if AGENT and SECRET' in c['dsl'] for c in selected)
    manifest['templates'][name]={'contract_hash':template_support.contract(definition),'cases':3,
        'effects':['block','kill','notify'],'case_ids':[c['id'] for c in selected],'kind':'runtime'}
print(json.dumps(manifest,indent=2))
