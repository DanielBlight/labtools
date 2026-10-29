# Scripted spectrum dark capture/reuse checkpoint

Input `labtools_source_20261029_111859.txt`, HEAD `4d324946`, branch `feature/shared-instrument-session`. This checkpoint adds only script-facing dark capture, exact-match reuse and NPZ helpers over existing service/IO contracts.

API: `capture_dark`, `capture_dark_async`, `save_dark`, `load_dark`, `request_with_dark`. Runtime ownership, progress and cancellation mirror spectrum acquisition. No exposure scaling or backend fallback is introduced. Settings/configuration/backend must match exactly.

Validation: 11 facade tests passed; focused dark/spectrum/service/worker/records validation is recorded in the local run. Full suite remains required locally. Qt, hardware and IDQ parser P0 are separate.

```powershell
python .\apply_labtools_measurements_dark.py --check
python .\apply_labtools_measurements_dark.py --list
python .\apply_labtools_measurements_dark.py --apply
$changedPaths = @(python .\apply_labtools_measurements_dark.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m pytest tests/test_measurements_dark.py tests/test_measurements_spectrum.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Recommended commit: `Add script-facing spectrum dark capture and reuse`.
