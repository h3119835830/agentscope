"""Validate documentation/source evidence; never executes agents or policy writes.

The only optional write is --write-report to this directory's validation.json.
No credentials, conversation content or application database are inspected.
"""
import argparse,ast,hashlib,json,re,subprocess,sys
from pathlib import Path
from urllib.parse import unquote,urlparse
from render_catalog import render

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
NEW_DOCS=['docs/AgentScope-四层策略架构与ActPlane调研-20261012.md','docs/RFC/RFC-20261012-AgentScope-four-layer-policy.md','docs/ADR/ADR-20261012-AgentScope-four-layer-policy.md','docs/REVIEW/REVIEW-20261012-AgentScope-four-layer-audit.md','docs/BUG/BUG-20261012-AgentScope-policy-scope-and-evidence.md']
OLD_DOCS=['docs/REVIEW/REVIEW-20261011-AgentScope-policy-source-semantics.md','docs/BUG/BUG-20261011-AgentScope-policy-source-semantics.md','docs/acceptance/20261011-policy-source-semantics-dsh/README.md']
SCOPES={'system','agent','workspace','session','delegation'}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(name):return json.loads((HERE/name).read_text())
def require(condition,message):
    if not condition:raise AssertionError(message)
def check_cases(cases):
    require({c['id'] for c in cases}=={'E'+str(i) for i in range(1,14)} and len(cases)==13,'case IDs')
    for c in cases:
        require(set(c['scope'])<=SCOPES and c['scope'],'case scope '+c['id'])
        require(c['classification'] in ('可参数化复用','需要适配','仅参考'),'classification')
        for k in ('tool_blind_spot','expected_allow','expected_deny','adaptation','risk'):require(bool(c.get(k)),c['id']+' missing '+k)
def local_target(path,link):
    target=(path.parent/unquote(link.split('#')[0])).resolve()
    require(target.is_relative_to(REPO),'link escapes repo '+link)
    return target
def self_tests():
    import copy
    good=load('case-catalog.json')['cases'];n=0
    for mutate in (lambda x:x[0].pop('expected_allow'),lambda x:x[0].update(scope=['invented']),lambda x:x.pop(),lambda x:x[0].update(classification='passed')):
        bad=copy.deepcopy(good);mutate(bad)
        try:check_cases(bad)
        except AssertionError:n+=1
        else:raise AssertionError('negative fixture accepted')
    try:local_target(HERE/'README.md','../../../../../../outside.md')
    except AssertionError:n+=1
    else:raise AssertionError('escaping link accepted')
    return n
def run(source,central):
    counts={};lock=load('source-lock.json');evidence=load('source-evidence.json');repos={r['id']:r for r in lock['repositories']}
    require(len(repos)==5 and len(lock['papers'])==5,'source versions')
    for r in repos.values():
        base=source/r['id'];actual=subprocess.check_output(['git','-C',str(base),'rev-parse','HEAD'],text=True).strip();require(actual==r['commit'],'source commit drift '+r['id'])
    counts['repository_pins']=5
    for e in evidence:
        base=REPO if e['repo']=='agentscope' else source/e['repo'];p=base/e['path'];raw=p.read_bytes();text=raw.decode('utf-8')
        require(sha(raw)==e['sha256'],'source digest drift '+str(p));require(len(text.splitlines())==e['lines'],'source lines')
        if e['repo']=='agentscope':require(e['url'] is None and e['availability'].startswith('local_git_only'),'unpublished source link')
        else:require('/blob/'+e['commit']+'/' in e['url'],'unpinned source URL')
        for s in e['symbols']:
            require(1<=s['line']<=e['lines'],'symbol line bounds')
            if not e['path'].endswith('.py'):require(text.splitlines()[s['line']-1].strip()[:130]==s['name'],'symbol text drift')
        if e['path'].endswith('.py'):
            symbols=[dict(name=n.name,line=n.lineno,end=n.end_lineno) for n in ast.walk(ast.parse(text)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
            require(symbols==e['symbols'],'python symbol drift '+e['path'])
    counts['source_file_hashes']=len(evidence)
    # Source URLs/line anchors point into the pinned, locally fetched blob.
    by_url={e['url']:e for e in evidence if e['url']};paper_urls={p['url'] for p in lock['papers']}
    for p in lock['papers']:require(sha((source/(p['name']+'.html')).read_bytes())==p['sha256'],'paper fetch digest '+p['name'])
    counts['paper_fetch_hashes']=5
    cases=load('case-catalog.json');check_cases(cases['cases']);index=load('example-source-index.json');require(len(index['test_cases'])==12,'test count')
    require(cases['common']['runtime_verified_in_this_audit'] is False,'case false runtime claim')
    names={c['name'] for c in index['test_cases']}
    for c in cases['cases']:
        require(set(c['upstream_tests'])<=names,'unverified test name '+c['id'])
        url,anchor=c['source_url'].split('#');require(url in by_url,'case source URL');require(1<=int(anchor[1:])<=by_url[url]['lines'],'case source anchor')
    require(not next(c for c in cases['cases'] if c['id']=='E13')['upstream_tests'],'E13 falsely tested')
    rendered,data=render();require(rendered==(HERE/'case-catalog.md').read_text() and data==cases,'generated catalog drift')
    counts.update(document_examples=13,upstream_case_correspondences=12,case_contracts=13)
    artifact=source/'actplane-artifact';bench=load('benchmark-catalog.json');require({f['id'] for f in bench['families']}=={'RQ1','RQ2','RQ4','RQ5'},'benchmark families')
    rq4=json.loads((artifact/'docs/artifact/rq4_octobench_ledger.json').read_text());rq5=json.loads((artifact/'docs/artifact/rq5_openagentsafety_ledger.json').read_text());task4={r['case_id'] for r in rq4['rows']};task5={r['task_id'] for r in rq5['rows']}
    for f in bench['families']:
        for path in f['sources']:require((artifact/path).is_file(),'benchmark source missing '+path)
        for item in f['representatives']:require(item in task4 if f['id']=='RQ4' else item in task5 if f['id']=='RQ5' else (artifact/item).is_file(),'benchmark representative missing '+item)
        for k in ('license','dependencies','tool_blind_spot','expected_effect','risk'):require(bool(f[k]),'benchmark metadata '+k)
    counts['benchmark_families']=4
    prov=load('generation-provenance.json');require(prov['rq4']['task_count']==21 and prov['rq5']['task_count']==361,'provenance counts');require(prov['rq5']['description_manifest_rows']==311 and prov['rq5']['noops']==58,'RQ5 inventory')
    require(prov['rq4']['per_task_reward_available']==0 and prov['rq5']['per_task_outcome_available']==0,'provenance availability')
    require(prov['rq5']['llm_generation_reproduced'] is False and prov['rq4']['delta_trace_reproduced'] is False,'false reproduction claim')
    counts['generation_ledger_rows']=382
    artifact_check=load('artifact-check.json');require(artifact_check['returncode']==0 and not any(artifact_check[k] for k in ('agents_run','bpf_loaded','models_called')),'artifact check boundary')
    require(sha((HERE/'upstream-artifact-check.txt').read_bytes())==artifact_check['stdout_sha256'],'artifact check output drift')
    docs=[REPO/p for p in NEW_DOCS+OLD_DOCS]+list(HERE.glob('*.md'));links=0;source_links=0
    for p in docs:
        text=p.read_bytes().decode('utf-8');require('\ufffd' not in text and '\x00' not in text,'encoding '+str(p));require(text.count('```')%2==0,'code fences '+str(p))
        for label,link in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',text):
            if link.startswith(('http://','https://')):
                base,_,anchor=link.partition('#')
                if base in by_url:
                    require(not anchor or re.fullmatch('L[0-9]+',anchor),'source anchor shape');source_links+=1
                elif base in paper_urls and anchor:
                    name=next(x['name'] for x in lock['papers'] if x['url']==base);require('id="'+anchor+'"' in (source/(name+'.html')).read_text(),'paper anchor missing '+link)
                continue
            if link.startswith('#'):continue
            target=local_target(p,link);require(target.is_file() or target==HERE/'validation.json','missing doc link '+str(p)+': '+link);links+=1
    counts.update(markdown_documents=len(docs),relative_links=links,pinned_case_links=source_links)
    rfc=(REPO/NEW_DOCS[1]).read_text()
    for i in range(1,13):require('A'+str(i).zfill(2) in rfc,'missing acceptance A'+str(i))
    contract_terms=('scope/target','origin/context_ref','authority','binding','worker','workspace_id','session_id','人工确认','待实现','cgroup','idle','default','locked')
    for term in contract_terms:require(term in rfc,'missing contract '+term)
    counts['architecture_contract_checks']=12+len(contract_terms)
    changed=subprocess.check_output(['git','-C',str(REPO),'diff','--name-only','-z']).decode().split('\0')+subprocess.check_output(['git','-C',str(REPO),'diff','--cached','--name-only','-z']).decode().split('\0')+subprocess.check_output(['git','-C',str(REPO),'ls-files','--others','--exclude-standard','-z']).decode().split('\0')
    files=sorted({x for x in changed if x});allowed=set(NEW_DOCS+OLD_DOCS)
    for x in files:require(x in allowed or x.startswith('docs/research/20261012-four-layer-policy/'),'out of scope diff '+x)
    require(subprocess.run(['git','-C',str(REPO),'diff','--check'],capture_output=True).returncode==0,'git diff check')
    require(subprocess.run(['git','-C',str(REPO),'diff','--cached','--check'],capture_output=True).returncode==0,'staged git diff check')
    counts['changed_files_checked']=len(files)
    if central:
        synced=0
        for p in sorted(set(docs+list(HERE.glob('*.json'))+list(HERE.glob('*.py'))+[HERE/'upstream-artifact-check.txt'])):
            if p.name=='validation.json':continue
            dest=central/p.relative_to(REPO/'docs');require(dest.is_file() and dest.read_bytes()==p.read_bytes(),'central mismatch '+str(dest))
            synced+=1
        counts['central_sync_files']=synced
        central_updates=load('central-index-updates.json')['files']
        for e in central_updates:
            p=central/e['path'];require(sha(p.read_bytes())==e['sha256'],'central historical index drift '+e['path'])
            require('2026-10-12' in p.read_text(encoding='utf-8'),'central latest note missing')
            for label,link in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',p.read_text(encoding='utf-8').split('\n\n')[1]):
                require((p.parent/link).is_file(),'central latest link missing '+link)
        counts['central_historical_index_updates']=len(central_updates)
    counts['negative_guard_checks']=self_tests()
    return dict(date='2026-10-12',passed=True,kind='documentation_and_static_source_audit',checks=counts,runtime_acceptance_performed=False,models_called=False,policy_changed_by_this_task=False,remote_push=False,files={str(p.relative_to(REPO)):sha(p.read_bytes()) for p in docs+list(HERE.glob('*.json'))+list(HERE.glob('*.py'))+[HERE/'upstream-artifact-check.txt'] if p.name!='validation.json'})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True,type=Path);p.add_argument('--central-root',type=Path);p.add_argument('--write-report',action='store_true');a=p.parse_args();result=run(a.source_root,a.central_root)
    if a.write_report:(HERE/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':result['checks']},ensure_ascii=False))
