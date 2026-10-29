# Scripted intensity-map facade checkpoint

Input <File>labtools_source_20261029_114828.txt</File>, HEAD `117b445f72742bf966927d789379210ab1e28a9a`, branch `feature/shared-instrument-session`, upstream +10/-0. The tracked tree/index were recorded clean and 13 unrelated installers are preserved.

This checkpoint adds only a Qt-free facade over the existing resumable map acquisition. Public contracts: `IntensityMapRequest`, `IntensityMapProvenance`, `IntensityMapMeasurement`, `IntensityMapRuntime`, sync/async `acquire_intensity_map`, and `request_from_resume`. Schema version 1, signatures, dataset allocation, checkpoint/final outputs, deterministic simulation, cleanup and shared provider/session composition are unchanged.

Validation: 5 dedicated facade tests and focused simulation/shared-map tests passed. Full suite is required locally. Qt, physical acceptance, IDQ P0, hyperspectral and anneal remain separate.

```powershell
python .\apply_labtools_measurements_intensity_map.py --check
python .\apply_labtools_measurements_intensity_map.py --list
python .\apply_labtools_measurements_intensity_map.py --apply
$changedPaths = @(python .\apply_labtools_measurements_intensity_map.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m pytest tests/test_measurements_intensity_map.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Recommended commit: `Add Qt-free scripted intensity-map facade`.
