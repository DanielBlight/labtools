# Release-candidate validation

## Purpose

Use this procedure to validate a clean LabTools candidate from the locked environment,
then prove that the built wheel can be installed and imported outside the source tree.

## Standard command

From the repository root:

```powershell
& ".\scripts\development\validate_release_candidate.ps1"
```

The script performs six bounded stages:

1. `uv sync --frozen --group dev`
2. `ruff check src tests`
3. `compileall` over `src`
4. the full non-hardware pytest suite
5. `uv build`
6. isolated wheel installation and metadata/import smoke

Validation refuses to start from a dirty working tree. This prevents generated build
artefacts or uncommitted source from being mistaken for the reviewed candidate.

## Faster packaging-only rehearsal

After the complete suite has already passed for the same clean commit:

```powershell
& ".\scripts\development\validate_release_candidate.ps1" -SkipTests
```

Record the earlier test output with the candidate evidence. `-SkipTests` is not a
substitute for the full release gate.

## Wheel-only smoke

```powershell
uv build
& ".\scripts\development\smoke_test_wheel.ps1"
```

The smoke test creates a temporary virtual environment, installs the newest LabTools
wheel with `--no-deps`, checks package metadata version `0.2.0rc1`, imports `labtools`
from the installed wheel, and deletes the temporary environment.

The no-dependency smoke is intentional: it verifies wheel contents and metadata without
reusing the development checkout. Functional operator and hardware tests still require
the locked runtime environment and the acceptance process in `release-plan.md`.

## Evidence to retain

- candidate commit and tag
- `uv.lock` hash
- CI run URL or exported log
- pytest summary
- wheel and source-distribution SHA-256 hashes
- isolated smoke output
- lab-PC installation and rollback record
