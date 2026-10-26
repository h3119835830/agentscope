"""Optional regression probe: load the pre-fix decision code in isolated tests.

Run only with the backend test conftest, which creates a temporary database and
disconnects all live runtime endpoints. A failing candidate-check budget is the
expected result for this historical baseline, not an acceptance pass.
"""
from pathlib import Path
import types
import pytest


@pytest.fixture(autouse=True)
def use_historical_decision_code(monkeypatch):
    from agentscope_app.instances import approval_decisions
    module=types.ModuleType('agentscope_app.instances._historical_approval_decisions')
    module.__package__='agentscope_app.instances'
    path=Path(__file__).resolve().parents[2]/'approval_decisions-baseline.py'
    exec(compile(path.read_text(),str(path),'exec'),module.__dict__)
    monkeypatch.setattr(approval_decisions,'approve',module.approve)
