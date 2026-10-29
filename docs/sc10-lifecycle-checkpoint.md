# SC10 serial lifecycle checkpoint

Input snapshot `labtools_source_20261029_102922.txt`, HEAD `f054ad5`, branch `feature/shared-instrument-session`, upstream +5/-0. Tracked state was recorded clean; eight unrelated installers are preserved.

SC10 now validates positive baud/timeout before opening, preserves connect/identity exceptions when close also fails, retains a failed-close handle, blocks reconnect/commands after teardown starts, and never sends shutter commands from transport close. Framing, enums, 9600/8-N-1 defaults, timeouts, command+CR, prompt/echo/whitespace parsing, toggle/readback and command ordering are unchanged. Toggle commands are never retried.

Whole-module fake serial tests cover open/reset/identify, wrong device, whitespace, timeout, query/command, cancellation, parameter validation and close failure. No serial port was opened. Focused SC10 plus inherited regression tests passed; the complete suite was started but the execution wrapper limit interrupted it, so local full-suite validation remains required. IDQ eval P0 and Qt acceptance remain open.

## Install and validate

```powershell
python .\apply_labtools_sc10.py --check
python .\apply_labtools_sc10.py --list
python .\apply_labtools_sc10.py --apply
$changedPaths = @(python .\apply_labtools_sc10.py --list)
$changedPython = @($changedPaths | Where-Object { $_ -like '*.py' })
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync ruff format --check @changedPython
uv run --no-sync ruff check @changedPython
uv run --no-sync python -m pytest tests/test_sc10_lifecycle.py tests/test_reliability_regressions.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Rollback with the exact printed backup path before later edits. Recommended commit:

```powershell
git commit -m "Harden SC10 serial startup and teardown ownership" -m "Preserve primary failures, retain failed-close ownership, and add whole-module fake serial transcript coverage without changing shutter state."
```

Next bounded task: Kinesis finite native-unit validation and close ownership only, unless approved IDQ histogram fixtures arrive first.
