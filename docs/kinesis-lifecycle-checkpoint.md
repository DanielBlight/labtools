# Kinesis lifecycle checkpoint

Input `labtools_source_20261029_104018.txt`, HEAD `bea41a66`, branch `feature/shared-instrument-session`, upstream +6/-0; tracked state recorded clean and nine installers preserved.

The wrapper now rejects non-finite/non-positive timeout and non-finite native positions before SDK calls. It preserves exactly-one discovery, lazy import, native units, no homing, move/wait/readback and stop ordering. Failed close retains `_stage`, starts permanent teardown, and blocks commands/reconnect. Context cleanup preserves body failures. No travel/degree limits were invented.

Validation: 15 whole-module fake-pyLabLib tests passed. The complete suite was started but the execution wrapper interrupted it, so local full-suite validation is required. No physical stage or Qt acceptance is claimed.

The companion [scriptable measurements architecture](scripted-measurements.md) makes a stable `labtools.measurements` facade a final-version requirement. It is documentation only in this checkpoint; no new measurement API or hyperspectral implementation is claimed.

```powershell
python .\apply_labtools_kinesis.py --check
python .\apply_labtools_kinesis.py --list
python .\apply_labtools_kinesis.py --apply
$changedPaths = @(python .\apply_labtools_kinesis.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m pytest tests/test_kinesis_lifecycle.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Recommended commit: `Harden Kinesis native-unit validation and close ownership` with body noting fake-SDK coverage and the documented scriptable-measurements target.
