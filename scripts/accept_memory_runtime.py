#!/usr/bin/env python3
"""Real DSH/Pi acceptance driver. All emitted evidence is synthetic and public."""
import argparse,json,time,urllib.request,urllib.error,uuid
from pathlib import Path
ROOT=Path('/var/lib/agentscope-memory-20261026')
REPORT=ROOT/'evidence'
URL='http://127.0.0.1:18005'
def api(path,body=None):
    request=urllib.request.Request(URL+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=85) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(str(json.load(error).get('detail','HTTP '+str(error.code)))) from error
def evidence(name,value):
    REPORT.mkdir(exist_ok=True)
    (REPORT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2))
    return value
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['create','state','prompt','probe','close','capture']);p.add_argument('value',nargs='?',default='');p.add_argument('--task');p.add_argument('--operation',default='write');p.add_argument('--expected',default='deny');args=p.parse_args()
    if args.action=='create':
        created=api('/api/managed/scenarios/safety-delete-config/tasks',{});task=created['id']
        evidence(args.value or task,created);print(json.dumps({'task':task,'start':api('/api/managed/tasks/'+task+'/start',{})}));return
    task=args.task;base='/api/managed/tasks/'+task
    if not task:raise SystemExit('--task is required')
    if args.action=='prompt':result=api(base+'/prompt',{'text':args.value,'request_key':uuid.uuid4().hex})
    elif args.action=='probe':result=api(base+'/verify-operation',{'target':args.value,'operation':args.operation,'expected':args.expected})
    elif args.action=='close':result=api(base+'/close',{})
    elif args.action=='capture':
        result={name:api(base+path) for name,path in [('state',''),('native','/native'),('records','/strategy-records?stage=runtime&include_assessments=true'),('audit','/audit'),('tools','/execution-audit?category=tools'),('os','/execution-audit?category=os')]}
        result['details']=[api(base+'/strategy-records/'+item['id']) for item in result['records']['records']]
        evidence(args.value or task,result)
        print(json.dumps({'task':task,'saved':str(REPORT/((args.value or task)+'.json')),'policy_records':len(result['details'])}));return
    else:
        result=api(base);s=result['state']
        view={k:s.get(k) for k in ('phase','gate','turn','revision','version','session_id','runtime_protected','error')}
        view['jobs']=[{'id':row['id'],'status':row['status'],'error':row.get('error')} for row in result['jobs']]
        if s['phase']=='running':
            native=api(base+'/native');view['native']={'status':native.get('status'),'turn':native.get('turn'),'messages':[item.get('text') for item in native.get('events',[]) if item.get('type')=='assistant/message'][-1:]}
        print(json.dumps(view,ensure_ascii=False));return
    evidence(task+'-'+args.action+'-'+str(time.time_ns()),result);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
