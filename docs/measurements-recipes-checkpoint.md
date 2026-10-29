# Versioned data-only measurement recipes checkpoint

Input <File>labtools_source_20261029_121652.txt</File>, HEAD `820fc7f6f3617aa13afcc79b58b61b4786bcf60`, branch `feature/shared-instrument-session`, upstream +12/-0. The tracked worktree/index were recorded clean and existing installers remain untracked/preserved.

This checkpoint adds schema-version-1 strict JSON recipes only for implemented spectrum, dark, alignment and intensity-map facades. Public API: `MeasurementRecipe`, `RECIPE_SCHEMA_VERSION`, `load_recipe`, `save_recipe`, and `recipe_to_data`. Files contain JSON data only. Unknown root/kind fields, unsupported schemas/kinds, implicit backends and invalid settings are rejected. Dark NPZ reuse still requires exact settings/configuration/backend equality. Map configuration and optional resume directory are preserved without changing checkpoint schema or signatures.

Validation: 8 dedicated recipe tests passed. Full suite must be rerun locally. Qt, hardware, IDQ P0, hyperspectral and anneal remain separate.

```powershell
python .\apply_labtools_measurements_recipes.py --check
python .\apply_labtools_measurements_recipes.py --list
python .\apply_labtools_measurements_recipes.py --apply
$changedPaths = @(python .\apply_labtools_measurements_recipes.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m pytest tests/test_measurements_recipes.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git status --short
```

Recommended commit: `Add strict versioned measurement recipe schemas`.
