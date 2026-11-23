"""Exercise actual GUI completion methods without importing Qt or native drivers."""

import ast
import asyncio
import traceback
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "state,error,closing,failed,dialogs",
    [
        ("available", asyncio.CancelledError, False, False, 0),
        ("faulted", asyncio.CancelledError, False, True, 1),
        ("faulted", asyncio.CancelledError, True, True, 0),
        ("faulted", OSError, False, True, 1),
        ("faulted", OSError, True, True, 0),
        ("available", None, False, False, 0),
    ],
)
def test_gui_completion_reports_worker_fault(state, error, closing, failed, dialogs):
    source = Path(__file__).resolve().parents[1] / "src/labtools/gui/alignment_gui_horiba.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HoribaAlignmentWindow")
    methods = [n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in {"_poll_job", "_report_job_failure"}]
    assert len(methods) == 2
    for method in methods:
        method.decorator_list = []
    harness = ast.Module(body=[ast.ClassDef(name="Harness", bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[])
    ast.fix_missing_locations(harness)
    shown = []

    class Box:
        Icon = SimpleNamespace(Critical=1)

        def __init__(self, parent):
            pass

        def setWindowTitle(self, value):
            pass

        def setIcon(self, value):
            pass

        def setText(self, value):
            pass

        def setDetailedText(self, value):
            self.details = value

        def exec(self):
            shown.append(self.details)

    class Job:
        def take_latest(self):
            return None

        def done(self):
            return True

        def result(self):
            if error is not None:
                raise error("injected completion")

    scope = {"asyncio": asyncio, "traceback": traceback, "QMessageBox": Box, "SpectrumWorkerFaultedError": type("SpectrumWorkerFaultedError", (RuntimeError,), {})}
    exec(compile(harness, str(source), "exec"), scope)  # noqa: S102 - test harness executes methods from trusted local project source
    widget = scope["Harness"]()
    widget._job = Job()
    widget._running = False
    widget._close_pending = closing
    widget._worker = SimpleNamespace(status=lambda: SimpleNamespace(state=state))
    messages = []
    widget._finish = messages.append
    widget._poll_job()
    assert widget._job is None
    assert len(messages) == 1
    assert ("teardown" in messages[0]) is failed
    if not failed:
        assert messages[0] == "Stopped"
    assert len(shown) == dialogs
    if shown:
        assert "injected completion" in shown[0]
