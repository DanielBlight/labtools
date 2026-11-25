"""Simplified focus controls: fixed settling and one +Z 60 V step."""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from labtools.runtime.focus_stack import FocusPlan, run_focus_stack


class Stage:
    simulated = True
    def __init__(self):
        self.stop_event = SimpleNamespace(is_set=lambda: False)
        self.calls = []
    def check_stop(self, cancel=None):
        return None
    def wait(self, seconds, cancel=None):
        self.calls.append(("wait", seconds))
    def call(self, token, command, **kwargs):
        self.calls.append((command, kwargs))
        if command == "read":
            return {"connected": True}
        return {"connected": True}


@dataclass(frozen=True)
class Config:
    save_results: bool = False
    output_root: Path = Path(".")

    def validate(self):
        return self


def test_automatic_extension_uses_one_positive_60_v_step():
    stage = Stage()
    plan = FocusPlan((20,), sweeps=2, steps_per_extension=1, direction=1, settle_s=.2)
    results = iter([SimpleNamespace(complete=True), SimpleNamespace(complete=True)])
    last, run = run_focus_stack(stage, object(), plan, Config(), lambda *a, **k: next(results))
    extensions = [call for call in stage.calls if call[0] in {"amplitude", "step"}]
    assert extensions == [
        ("amplitude", {"axis": 1, "value": 60, "cancel": extensions[0][1]["cancel"]}),
        ("step", {"axis": 1, "value": 1, "cancel": extensions[1][1]["cancel"]}),
    ]
    assert [call for call in stage.calls if call == ("wait", .2)] == [("wait", .2), ("wait", .2)]
    assert last.complete and run["status"] == "completed"
