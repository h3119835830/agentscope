import ast,collections
from pathlib import Path


def summarizer():
    source=Path(__file__).parents[2]/'scripts/normalization_acceptance_report.py'
    function=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='summarize')
    scope={'collections':collections,'CASES':('a','b')}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),scope)
    return scope['summarize']


def complete_rows():
    rows=[]
    for case in ('a','b'):
        for iteration in range(1,4):
            task=case+str(iteration)
            entries=[{'kind':'run_started','case':case,'iteration':iteration},
                     {'kind':'run_passed','case':case,'iteration':iteration,'scripted_user_messages':16,'session_id':task,'closure':{'status':'stopped'},'protected_integrity':True},
                     *[{'kind':'turn_completed','number':n,'native_turn':n,'native':{'events':[]}} for n in range(1,17)],
                     {'kind':'probe','classification':'correct_block'},
                     *[{'kind':'duplicate_reused','number':n} for n in (8,9)],
                     *[{'kind':kind} for kind in ('held_capabilities_revoked','expansion_verified','control_read_boundary')],
                     {'kind':'feedback_recovery_verified','protected_denial_event_ids':[7] if task=='a1' else []}]
            rows.extend({'batch':'frozen','task':task,**r} for r in entries)
    return rows


def test_acceptance_summary_requires_all_96_actual_completed_messages():
    summarize=summarizer();rows=complete_rows()
    assert summarize(rows,'frozen')['passed']
    rows=[r for r in rows if not (r['task']=='a1' and r['kind']=='turn_completed' and r['number']==16)]
    result=summarize(rows,'frozen')
    assert not result['passed'] and result['scripted_messages']==95


def test_acceptance_summary_does_not_hide_failures_or_count_other_batches():
    summarize=summarizer();rows=complete_rows()
    rows.append({'batch':'old','kind':'run_failed','task':'old'})
    assert summarize(rows,'frozen')['passed']
    rows.append({'batch':'frozen','kind':'run_failed','task':'a1','error':'actual mismatch'})
    assert not summarize(rows,'frozen')['passed']
    rows.pop();next(r for r in rows if r['kind']=='probe')['classification']='missed_block'
    assert not summarize(rows,'frozen')['passed']


def test_refusal_only_cannot_satisfy_native_kernel_feedback_criterion():
    summarize=summarizer();rows=complete_rows()
    for r in rows:
        if r['kind']=='feedback_recovery_verified':r['protected_denial_event_ids']=[]
    assert not summarize(rows,'frozen')['passed']


def test_payment_directory_probe_stays_inside_workspace():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).parents[2]/"scripts"))
    from managed_acceptance import select_probe_target
    workspace=Path("/n/fixture/r")
    targets=[workspace/"test_validator.py",workspace/"p0/tests/test_validator.py"]
    assert select_probe_target("safety-impossible-tests",targets,workspace)==targets[1]
    assert select_probe_target("safety-delete-config",targets,workspace)==targets[0]


def test_scenario_cohorts_preserve_exact_runs_and_selected_failures():
    summarize=summarizer();rows=complete_rows()
    for row in rows:row['batch']='one' if row['task'].startswith('a') else 'two'
    cohorts=[{'case':'a','batch':'one'},{'case':'b','batch':'two'}]
    rows.append({'batch':'old','kind':'run_failed','task':'a-old','error':'retained old attempt'})
    assert summarize(rows,'final',cohorts)['passed']
    rows.append({'batch':'one','kind':'run_failed','task':'a1','error':'selected run failed'})
    assert not summarize(rows,'final',cohorts)['passed']
    rows.pop()
    rows.append({'batch':'one','task':'extra','kind':'run_started','case':'a','iteration':1})
    assert not summarize(rows,'final',cohorts)['passed']
