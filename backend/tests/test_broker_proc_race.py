import ast,json,subprocess
from pathlib import Path
from types import SimpleNamespace


def test_domain_member_exit_race_keeps_live_executor(monkeypatch):
    # Load the real function without executing the broker process setup.
    source=Path(__file__).parents[1]/'broker/main.py'
    function=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='domain_members')
    scope={'Path':Path,'subprocess':subprocess,'json':json}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),scope)
    rows=[{'key':pid,'value':5} for pid in [11,12,13,14]]
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(rows)))
    def read(path,*a,**k):
        pid=int(path.parent.name)
        if pid==12:raise ProcessLookupError(3,'No such process')
        if pid==13:raise FileNotFoundError(2,'No such file')
        return 'State:\t'+('Z' if pid==14 else 'S')+' (process)\n'
    monkeypatch.setattr(Path,'read_text',read)
    assert scope['domain_members']({'pin_root':'/pins/task','domain_id':5})==[11]
