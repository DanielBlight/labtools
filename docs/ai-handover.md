# AI handover

Start here. `labtools` controls physical laboratory instruments. Reliability,
resource ownership, deterministic cleanup, explicit backend selection and truthful
failure reporting take priority over architectural uniformity.

## Repository state

This handover describes the repository at commit `5225d07` on
`feature/shared-instrument-session` after the spectrum-service and shared
mirror/map checkpoints. Inspect the actual code and Git status before changing it;
this document never overrides a newer implementation.

Canonical sources:

- [Architecture](architecture.md): current and target dependency/lifecycle model.
- [Development conventions](development-conventions.md): mandatory implementation rules.
- [Roadmap](refactor-roadmap.md): completed and remaining bounded phases.
- [Commands](commands.md): supported entry points and operator commands.

Historical refactor notes retain technical context but are not current task lists.

## Currently implemented and offline validated

- Lazy CLI/standalone launchers for annealing, intensity maps, spectra and manual
  mirror control.
- Strict annealing recipes and maintainer-controlled instrument profiles.
- Resumable intensity-map acquisition with cooperative point-boundary cancellation,
  checkpointing and independently attempted checkpoint/home/gate cleanup.
- Explicit map simulation with deterministic model/version, coordinate/channel seeds
  and resume-signature validation.
- Process-local `InstrumentSession` reservations, physical-resource aliasing, lazy
  connection, worker-thread ownership, fault latching and reviewed cleanup allowlists.
- Shared `LabJackService` and `SharedMapProvider` adapters.
- `SpectrumService`, validated immutable settings/results, explicit real/synthetic
  backends, provenance-bearing NPZ dark records and result exports.
- The ordinary HORIBA spectrum GUI uses the spectrum service. It snapshots settings
  on the UI thread, rejects legacy CSV as validated dark provenance, reports stale
  darks, keeps dark enablement separate from stored data, exports immutable result
  metadata, handles cancellation separately and retains worker ownership until
  `QThread.finished`.
- `SharedMirrorMapApplication` composes manual mirror control and intensity mapping
  around one application-owned session. `ManualMirrorService` exposes only lease,
  movement and status operations. Shared mode disables uncoordinated laser controls.
- Detached status records report session/resource state without exposing handles or
  bypassing reservations.
- Shared simulation composition now owns one synthetic mirror/gate state behind the
  same session aliases as real mode. Manual and map tools share it without exposing
  mutable state; deterministic counter behaviour remains per-map and config-bound.
- Real shared-map composition owns a lazy IDQ count service keyed as
  `time-controller:<canonical-ip>`. IDQ construction/use/close stays on the session
  worker, and maps reserve LabJack plus IDQ atomically through cleanup. Standalone
  maps and shared simulation keep their established counter composition.

These statements describe software behaviour exercised by fake/offline tests. They
are not claims about physical hardware, calibration, optical safety or vendor SDKs.

## Implemented but requiring physical hardware validation

- Real HORIBA connection/configure/acquire/disconnect through the service adapter.
- LabJack partial-startup cleanup and application-owned manual/map connection reuse.
- Mirror voltage movement, installed DAC calibration, DIO wiring and gate polarity.
- SC10, ITC4000, rotation-stage, camera and IDQ wrapper lifecycle behaviour.

Do not run `--run-hardware`, vendor diagnostics or legacy hyperspectral acquisition
without an operator-reviewed setup. Software does not replace interlocks or laboratory
procedures. Zero-voltage mirror home is not universally a safe optical state.

## Non-negotiable design rules

- Use the existing `InstrumentSession`; do not introduce a global singleton or a
  second resource manager.
- Reserve physical resources for the whole operation and its cleanup. Mirror and
  SPAD gate alias the same LabJack resource.
- GUI code receives services/controllers. It must not construct competing device
  connections in shared mode or contain the canonical experiment implementation.
- Do not return raw vendor handles to GUI code.
- HORIBA connect/use/disconnect remains on one asyncio loop. Persistent reuse needs
  the planned dedicated asyncio worker; do not cache objects across `AsyncTaskRunner`
  jobs.
- Select real or simulated backends explicitly. Never fall back to simulation after
  a real connection failure, and never describe simulation as hardware validation.
- Preserve vendor commands, units, limits, pin defaults, timing, QSettings keys,
  output formats and checkpoint signatures unless an intentional change is separately
  reviewed, documented and tested.
- Preserve primary failures and report cleanup failures. Broad catches are permitted
  only at reviewed GUI/worker/cleanup boundaries and must be documented locally.
- Do not manufacture dark provenance, calibration identity, raw frames after nonlinear
  reduction, or a known safe state after failed cleanup.
- Treat `vendor/` as reference material. Do not reformat or silently correct it;
  copy understood behaviour into first-party wrappers with tests and source notes.

## Validation baseline

The 28 October 2026 source snapshot was clean at `5225d07`. In the reconstruction
environment the full offline suite reported `267 passed, 3 skipped` with inherited
Matplotlib/pyparsing warnings. Python compilation and CLI help passed. PyQt6 and Ruff
were unavailable in that environment, so use the checked-in `uv.lock` and the actual
Windows development environment for final Qt and Ruff acceptance.

Run before every checkpoint:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = "offscreen"
$env:MPLBACKEND = "Agg"
uv run --no-sync python -m pytest -q
uv run --no-sync ruff format --check src tests
uv run --no-sync ruff check src tests
uv run --no-sync python -m labtools --help
git diff --check
git status --short
```

Repository-wide Ruff excludes `vendor/`. Do not auto-fix the whole tree inside a
functional migration; review changed-file fixes first and keep broad cleanup separate.

## Planned, not implemented

- IDQ DLT/timestamp streaming, histogram and coincidence ownership.
- Persistent HORIBA asyncio worker and alignment integration.
- Complete shared launcher with truthful availability/busy/fault presentation.
- General instrument-profile/recipe coverage and additional device simulations.
- Remaining wrapper reliability work and eventual compatibility retirement after
  internal and external consumers are checked.

## Next bounded task

Implement Phase 4's persistent HORIBA asyncio worker foundation only, without yet
integrating alignment. One dedicated asyncio loop must own connect/use/disconnect and
serialize complete jobs. Do not combine it with GUI redesign, IDQ streaming,
cryostat/piezo wrappers or hardware diagnostics.

## Git/checkpoint workflow

Work on a feature branch. Inspect and preserve unrelated changes. Do not have an
assistant commit, merge, push, reset or switch branches. After validation, inspect
`git diff --check`, `git diff --stat` and `git status --short`; commit one bounded
checkpoint yourself. Record unavailable checks and physical validation separately.
