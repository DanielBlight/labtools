# Scripted alignment-frame facade checkpoint

Input `labtools_source_20261029_113421.txt`. This checkpoint adds only the Qt-free alignment facade and tests over existing service/worker contracts. Public API: `AlignmentRequest`, `AlignmentMeasurement`, `acquire_alignment_frame`, `acquire_alignment_frame_async`.

Validation: 5 dedicated tests and the focused alignment/service/worker selection passed. Full suite must be rerun locally. Qt, physical hardware and IDQ parser P0 remain separate.

```powershell
python .\apply_labtools_measurements_alignment.py --check
python .\apply_labtools_measurements_alignment.py --list
python .\apply_labtools_measurements_alignment.py --apply
$changedPaths = @(python .\apply_labtools_measurements_alignment.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m pytest tests/test_measurements_alignment.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Recommended commit: `Add Qt-free scripted alignment-frame facade`.
