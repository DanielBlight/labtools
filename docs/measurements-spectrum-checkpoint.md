# Scriptable spectrum measurement facade checkpoint

Input snapshot `labtools_source_20261029_105903.txt`, HEAD `951cb543ab82e62718f8a04442ec93abf4edc96b`, branch `feature/shared-instrument-session`, upstream +7/-0. This checkpoint adds only the Qt-free spectrum facade, tests, one simulation example and documentation.

New public API: `SpectrumRequest`, `MeasurementProvenance`, `SpectrumMeasurement`, `SpectrumRuntime`, `acquire_spectrum`, and `acquire_spectrum_async`. Requests/results/provenance are frozen; backend and configuration identity are explicit. Existing `SpectrumService`/`SpectrumWorker` remain authoritative. No GUI, SDK, device-wrapper, map, hyperspectral or anneal facade change.

Validation: 6 facade contract tests and 68 focused spectrum tests passed. Ruff passed. The complete suite was started but the execution wrapper interrupted it, so local full-suite validation remains required. Qt, hardware and IDQ parser P0 remain separate.

```powershell
python .\apply_labtools_measurements_spectrum.py --check
python .\apply_labtools_measurements_spectrum.py --list
python .\apply_labtools_measurements_spectrum.py --apply
$changedPaths = @(python .\apply_labtools_measurements_spectrum.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m pytest tests/test_measurements_spectrum.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Recommended commit: `Add Qt-free scripted spectrum measurement facade`.
