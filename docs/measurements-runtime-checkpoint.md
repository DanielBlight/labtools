# Unified Qt-free measurement runtime checkpoint

Input <File>labtools_source_20261029_120541.txt</File>, HEAD `48eae2bd966462a52b4bfcee044ca4ee31749cfe`, branch `feature/shared-instrument-session`, upstream +11/-0. The tracked index/worktree were recorded clean and 14 unrelated installers are preserved.

This checkpoint adds `MeasurementRuntime` and frozen `MeasurementRuntimeStatus` only. It lazily exposes `.spectrum` and `.intensity_map`, enforces one explicit backend, borrows injected child runtimes, owns lazily-created child runtimes, and closes all owned children independently. Ordinary cleanup failures aggregate; cancellation/interrupt remains primary; context-body failures retain cleanup notes. Existing spectrum worker ownership and map session reservations remain unchanged.

Validation: 7 dedicated tests plus focused facade composition tests passed. Full suite must be rerun locally. Qt, hardware, IDQ P0, hyperspectral and anneal remain separate.

```powershell
python .\apply_labtools_measurements_runtime.py --check
python .\apply_labtools_measurements_runtime.py --list
python .\apply_labtools_measurements_runtime.py --apply
$changedPaths = @(python .\apply_labtools_measurements_runtime.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m pytest tests/test_measurements_runtime.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Recommended commit: `Add unified Qt-free measurement runtime composition`.
