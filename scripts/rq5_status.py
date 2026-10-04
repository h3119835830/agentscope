import json
from rq5_service import STATE
data=json.loads((STATE/'report/acceptance.json').read_text())
for case,pair in data['cases'].items():
    for group in ('A','B'):
        run=pair.get(group,{})
        evaluation=run.get('evaluation',{})
        print(json.dumps({'case':case,'group':group,'task':run.get('id'),'status':run.get('task_result'),
                          'unsafe':evaluation.get('raw_evaluator',{}).get('unsafe'),'integrity':evaluation.get('independent_integrity',{}).get('protected_unchanged'),
                          'modified':evaluation.get('independent_integrity',{}).get('modified'),'probes':run.get('probes',{}).get('checks'),
                          'chain':run.get('chain_passed'),'events':len(run.get('dsh_events',[]))}))
