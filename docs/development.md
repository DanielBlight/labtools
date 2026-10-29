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

## Alignment lifecycle checkpoint

See [acceptance guide](alignment-lifecycle-acceptance.md). Run the new blocked-backend
cases and window cases with the existing Qt lifecycle suite. The implementation
environment ran QtCore but could not load QtWidgets (libGL.so.1 missing). Local
Windows execution must report actual passes, not skipped modules. Temporary validation
tools were installed outside the repository; pyproject.toml and uv.lock are unchanged.

## Lab-PC release and operator installation

See [lab-PC deployment](lab-pc-deployment.md) for the proposed non-editable wheel,
locked runtime bundle, protected accounts/paths and side-by-side update procedure.
Keep development sync/editable installs separate from production operator use.
The [current Qt gate](qt-gate-status.md) is not accepted: four QtWidgets modules skip.
No collision-allocation code or automated deployment system is added by this checkpoint.

## Wrapper-audit continuation

[Device audit](device-wrapper-audit.md) and [repair plan](device-wrapper-repair-plan.md)
separate style, extracted-method probes, whole-wrapper fake tests and physical acceptance.
Current gate is still 15 passed / 4 skipped; full suite 318 passed / 4 skipped. Next
independent wrapper task is ITC transport lifecycle, not a repository-wide rewrite.
The [checkpoint guide](wrapper-audit-checkpoint.md) records exact evidence and commands.

## ITC W1 lifecycle contract

See [current checkpoint](itc4000-lifecycle-checkpoint.md). Ordinary transport cleanup
failures now raise ExceptionGroup; callers catching Exception still receive them.
Interrupt/cancellation remains primary. Startup/body errors retain cleanup notes and
structured _itc4000_cleanup_failures. Teardown blocks commands permanently; explicit
close retries only failed handles, with no guarantee a manager-invalidated handle can
recover. No physical output commands are added. Do not auto-reconnect or silently retry
commands. Whole-module fake-PyVISA tests supplement historical AST/adapter probes.

## HORIBA W2 lifecycle contract

See [W2 checkpoint](horiba-lifecycle-checkpoint.md). Real wrapper startup/teardown now
retains primary/cancellation and independently attempts CCD, mono and manager cleanup.
Failed handles are uncertain and only explicit disconnect retries them; reconnect and
commands after teardown are refused by cleared public handles/teardown state. Do not
add timeout/exposure/persistent-connection changes to this checkpoint. Whole-module
fake SDK tests supplement adapter fakes; neither establishes physical SDK/shutter safety.
## W5 scanning-mirror preflight status

W5 is implemented/offline-tested at input HEAD `d2e29eb929567cdcc10bdf3fff907044c6815369`.
Both finite requests and representable calibrated codes are checked before either write;
A/B protocol and calibration maths remain unchanged. Channel-B ordinary failure now
reports uncertain partial movement with no rollback/home. Validation: 11 dedicated,
89 focused, full 404 passed / 5 skipped. PyQt6 is absent, so Qt remains gated. See
[W5 checkpoint](scanning-mirror-preflight-checkpoint.md). IDQ P0 remains open.
## UC480 lifecycle status

UC480 partial setup/start cleanup is implemented/offline-tested at HEAD `b4be98c4f619526a421af54f795365f14d95ac54`. Validation: 16 dedicated; 27 camera+regression; full 420 passed / 5 skipped. PyQt6 absent, so Qt remains gated. See [UC480 checkpoint](uc480-lifecycle-checkpoint.md). IDQ P0 remains open.

## SC10 checkpoint status

SC10 serial startup/teardown and fake transcript coverage are implemented at HEAD `f054ad5`. Full-suite validation must be rerun locally because the execution wrapper interrupted the combined run. See [SC10 checkpoint](sc10-lifecycle-checkpoint.md). IDQ P0 and Qt remain open.

## Scriptable measurement API requirement

The final product must provide a stable Qt-free `labtools.measurements` facade over shared services/acquisition logic, with validated immutable requests/results, explicit backend/profile provenance, session reservations, deterministic cleanup, progress/cancellation and GUI/script parity. Spectrum and intensity map delegate to existing services; hyperspectral must be rebuilt from the legacy runner before export. See [scriptable measurements](scripted-measurements.md).

Kinesis finite native-unit validation and close ownership are implemented at HEAD `bea41a66`; 15 dedicated fake-SDK tests passed. Full-suite rerun remains local because the execution wrapper interrupted it. See [Kinesis checkpoint](kinesis-lifecycle-checkpoint.md).

## Scripted spectrum facade

The Qt-free spectrum facade is implemented; see [checkpoint](measurements-spectrum-checkpoint.md) and [usage](scripted-measurements.md). Map, hyperspectral and anneal facades remain planned.

## Scripted dark records

Qt-free dark capture, immutable reuse and NPZ helpers are implemented; see [checkpoint](measurements-dark-checkpoint.md).
