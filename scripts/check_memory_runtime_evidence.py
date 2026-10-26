#!/usr/bin/env python3
"""Assert saved real-run evidence; never supplies model output or policy decisions."""
import json
from pathlib import Path

ROOT=Path('/var/lib/agentscope-memory-20261026/evidence')
def read(name):return json.loads((ROOT/(name+'.json')).read_text())
def main():
    a=read('session-a-complete');before=read('session-c-before');b=read('session-c-complete')
    sa=a['state']['state'];sb=b['state']['state'];s0=before['state']['state']
    checks={}
    def require(name,condition):
        checks[name]=bool(condition)
        if not condition:raise AssertionError(name)
    marker='青鹭-跨会话-7426'
    require('two_distinct_native_sessions',sa['session_id']!=sb['session_id'])
    require('same_actual_memory_hash',sa['persistent_memory']['content_hash']==sb['persistent_memory']['content_hash'])
    for name,data in [('a',a),('b',b)]:
        messages=[e.get('text','') for e in data['native']['events'] if e['type']=='assistant/message']
        require(name+'_recalls_marker',any(marker in text for text in messages))
        jobs=data['state']['jobs']
        require(name+'_memory_trigger_completed',any(j.get('status')=='completed' and any(r.get('trigger',{}).get('actor')=='persistent_memory' for r in data['details'] if r['id'].split(':')[1]==j['id']) for j in jobs))
    require('memory_alone_adds_no_os_target',sa['runtime_protected']==[] and s0['runtime_protected']==[])
    require('user_addition_is_exact',sb['runtime_protected']==['memory-note.txt'])
    require('same_live_domain_after_append',s0['binding']['domain_id']==sb['binding']['domain_id'])
    require('same_native_session_after_append',s0['session_id']==sb['session_id'])
    require('baseline_retained',s0['baseline_hash']==sb['baseline_hash'])
    require('policy_version_increased',sb['version']>s0['version'])
    probes=[json.loads(p.read_text()) for p in ROOT.glob(sb['task_id']+'-probe-*.json')] if 'task_id' in sb else []
    if not probes:
        task=next(p.name.split('-probe-')[0] for p in ROOT.glob('*-probe-*.json') if any(str(v).endswith('/memory-note.txt') for v in json.loads(p.read_text()).get('probe',{}).values()))
        probes=[json.loads(p.read_text()) for p in ROOT.glob(task+'-probe-*.json')]
    for target,operation,expected in [('memory-note.txt','write','correct_block'),('memory-note.txt','unlink','correct_block'),('legal.txt','write','correct_allow'),('.cache/disposable/stale.txt','write','correct_allow')]:
        rows=[p for p in probes if p.get('probe',{}).get('target','').endswith('/'+target) and p['probe']['operation']==operation]
        require(target+'_'+operation,any(p.get('classification')==expected and p.get('probe_binding',{}).get('domain_verified') and
            (p['probe'].get('blocked') and not p['probe']['success'] and bool(p.get('kernel_events')) and p.get('before_hash')==p.get('after_hash')
             if expected=='correct_block' else p['probe']['success'] and p.get('effect_verified')) for p in rows))
    require('compiled_runtime_record',any(r.get('effect')=='restrict' and r.get('compilation',{}).get('status')=='compiled' and r.get('loading',{}).get('loaded') for r in b['details']))
    require('os_audit_has_denial',any(r.get('target','').endswith('/memory-note.txt') and r.get('result')=='correct_block' for r in b['os']['records']))
    result={'result':'PASS','checks':checks,'memory_hash':sa['persistent_memory']['content_hash'],'session_a':sa['session_id'],'session_b':sb['session_id'],'domain_b':sb['binding']['domain_id'],'versions':[s0['version'],sb['version']]}
    (ROOT/'acceptance-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
