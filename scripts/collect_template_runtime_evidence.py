"""Collect successful per-template runtime probes without losing failed attempts."""
import argparse,hashlib,json,os,re,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--runs',nargs='+',required=True);p.add_argument('--rejections',required=True);p.add_argument('--output',required=True);p.add_argument('--publish-manifest',action='store_true');args=p.parse_args()
 os.environ['AGENTSCOPE_STATE_DIR']=tempfile.mkdtemp(prefix='asrt-collect-',dir='/var/tmp')
 for k in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_RUNTIME_DIR'):os.environ.pop(k,None)
 sys.path.insert(0,str(ROOT/'backend'))
 from agentscope_app import db
 from agentscope_app.instances import template_versions,template_catalog,template_support
 db.init_db()
 with db.connect() as con:template_versions.init(con)
 sources=[Path(p) for p in args.runs];report=json.loads((sources[0]/'runtime-results.json').read_text());preliminary=json.loads(json.dumps(report));cases={};origin={}
 for source in sources:
  for c in json.loads((source/'runtime-results.json').read_text())['cases']:cases[c['id']]=c;origin[c['id']]=source
 assert all(c['passed'] for c in cases.values()),[c['id'] for c in cases.values() if not c['passed']]
 reject=json.loads(Path(args.rejections).read_text());assert reject['passed']
 report.update(cases=list(cases.values()),passed=True,source_runs=[str(p) for p in sources],pin_removed=True)
 report['limits']=['Synthetic parameter sets, not exhaustive values or hostile evidence tampering.','CLI-exported event files have UID 1000. Parent separately records process returns, file state and localhost receiver.','Retired workflow accepts a failed checker execution; this limitation is reproduced and its control-plane entry points are retired.']
 evidence=Path(args.output);evidence.mkdir(parents=True,exist_ok=True)
 for name,data in [('runtime-results',report),('rejection-results',reject),('preliminary-results',preliminary)]:(evidence/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2))
 cli_output={}
 for ident,source in origin.items():
  assert re.fullmatch('[a-z0-9-]+',ident)
  cli_output[ident]={suffix:(source/(ident+'-'+suffix+'.txt')).read_text() for suffix in ('stdout','stderr')}
 (evidence/'cli-output.json').write_text(json.dumps(cli_output,ensure_ascii=False,indent=2))
 manifest={'schema':'agentscope.template-runtime-evidence.v1','date':'2026-10-20','kernel_release':report['kernel_release'],'binary_sha256':report['binary_sha256'],
  'evidence_sha256':hashlib.sha256((evidence/'runtime-results.json').read_bytes()).hexdigest(),'templates':{}}
 for public in template_catalog.public_catalog():
  t=template_catalog.get(public['id'],public['version']);selected=[c for c in cases.values() if c['template_id']==t['id']]
  rejected=next((c for c in reject['cases'] if c['template_id']==t['id']),None)
  assert selected or rejected,t['id']
  manifest['templates'][t['id']]={'contract_hash':template_support.contract(t),'cases':len(selected) if selected else len(rejected['checks']),
   'effects':sorted({c['effect'] for c in selected}),'case_ids':[c['id'] for c in selected],'kind':'unsupported' if t['renderer']=='unsupported' else 'legacy' if public.get('retired') else 'runtime'}
 assert len(manifest['templates'])==37 and len(cases)==164
 (evidence/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 if args.publish_manifest:
  target=ROOT/'backend/agentscope_app/instances/template_runtime_acceptance.json';shutil.copyfile(evidence/'manifest.json',target);os.chown(target,1000,1000)
 for item in evidence.iterdir():
  if item.is_file():os.chown(item,1000,1000)
 print(json.dumps({'templates':len(manifest['templates']),'runtime_templates':len({c['template_id'] for c in cases.values()}),'runtime_cases':len(cases),'rejection_templates':len(reject['cases']),'passed':True}))
if __name__=='__main__':main()
