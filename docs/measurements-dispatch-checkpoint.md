# Qt-free measurement recipe dispatcher checkpoint

Input <File>labtools_source_20261029_130319.txt</File>, HEAD `26fcd0f65510761c9d954db0c1ca362b897316a0`, branch `feature/shared-instrument-session`; tracked state was recorded clean and existing installers preserved.

This checkpoint adds `execute_recipe` and `RealConfirmation` for schema-v1 `spectrum`, `dark`, `alignment`, and `intensity_map` only. It validates/loads data-only recipes, requires explicit confirmation before any real runtime is created, delegates to existing facade functions, borrows injected `MeasurementRuntime`, owns a temporary runtime otherwise, forwards progress/cancellation and returns existing immutable result records. No arbitrary pipeline, code execution, GUI, device, algorithm, hyperspectral or anneal change.

Validation: 7 dedicated dispatch tests passed. Full suite must be rerun locally. Qt, physical acceptance and IDQ P0 remain separate.

```powershell
python .\apply_labtools_measurements_dispatch.py --check
python .\apply_labtools_measurements_dispatch.py --list
python .\apply_labtools_measurements_dispatch.py --apply
$changedPaths = @(python .\apply_labtools_measurements_dispatch.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m pytest tests/test_measurements_dispatch.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Recommended commit: `Add guarded Qt-free measurement recipe dispatch`.
