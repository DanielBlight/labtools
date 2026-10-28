# Development and validation

Current implementation rules are in [development conventions](development-conventions.md);
current status, validation limitations and next task are in [handover](ai-handover.md).

## Environment

```powershell
uv sync --dev
uv run python -m labtools --help
```

The cleanup does not change dependency constraints, Python requirements or
vendor driver setup. Entry-point changes require refreshing the installed
package. Review `uv.lock` if uv updates project metadata.

## Offline checks

```powershell
uv run python -m compileall -q src tests
uv run python -m pytest -q
uv run labtools simulate intensity-map --points 3 --seed 7
```

The last command creates synthetic output. Known hardware test modules are
excluded by `pytest_ignore_collect` before import unless explicitly opted in.
The existing collection marker hook remains as a second guard. New hardware
test modules must be added to both known-module lists, or use a collection-safe
layout with lazy imports and explicit hardware fixtures. A marker applied after
import cannot prevent a module-level native import or connection.

Hardware tests require `--run-hardware`, the correct Windows drivers and a
reviewed setup. Do not add that option to ordinary regression checks. Hardware
diagnostic scripts in `scripts/` are not offline tests and may change device
state. Do not run them automatically.

## Linting

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
```

These are inspection commands, not a claim that the inherited project is
lint-clean. A repository-wide automatic formatting sweep was deliberately not
mixed into the structural refactor. Review style-only changes separately.

## Conventions

Use snake_case for modules/functions and descriptive workflow names for CLI
commands. Preserve vendor names in device wrappers. Separate Qt controls from
configuration/data processing. Import native libraries at the point a real
operation is requested where practical; do not silently simulate failures.

Retain old import/launch paths as small compatibility shims when moving code.
Do not rename persisted QSettings keys, checkpoint fields or output columns as
part of a cosmetic cleanup. Document intentional compatibility breaks.

## Local acceptance

Offline tests do not establish Qt rendering, Windows DLL loading, instrument
connectivity, physical shutter/gate timing, calibration or safety. With the
optical path made safe and only one tool owning each instrument, verify the
existing GUIs and real-device operations on the laboratory system before
merging. Test simulation and real operation separately.
