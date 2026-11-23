# Unified alignment implementation and validation, 2026-11-23

Status: engineering evidence, not Windows or connected unified-GUI acceptance.

## Baseline and input review

Implemented against the complete supplied source at
`90ae556a2efd6319b0820012b92995346807e5d8`, clean branch
`feature/unified-gui-alignment`, exported from `C:/Dev/labtools`.
All 393 full-bundle entries were decoded and their declared sizes/SHA-256 hashes
verified. The screenshots establish the requested visual style, not the current
source state: their review.json names the earlier 70317566 source and 2026-11-20
capture session. No screenshot preferences or synthetic output paths were imported
into the working-lab configuration.

The committed standalone record passes its bounded Start/multiple-frames/Stop/restart
check at 714405a. It explicitly marks dark-subtracted alignment and active-close
Not tested. Historical records are unchanged; unified acceptance is still required.

## Delivered behaviour

- Alignment tab beside Spectrum in explicit simulation and real-HORIBA modes.
- Existing light/teal studio cards, scrolling controls, plot toolbar, autoscale,
  immutable frame metrics and parameter-wheel protection. No broad GUI redesign.
- One lazy application-owned SpectrumWorker for both range and alignment.
- The existing range panel keeps its QThread-facing async API through a worker
  facade; all native construction and calls stay on the shared worker's loop/thread.
- The Alignment panel reuses the accepted standalone stream and bounded mailbox,
  injected with that worker. It does not construct a private native connection.
- Existing workspace Spectrum reservations serialize both workflows and overlapping
  map/Annealing resources. Ownership is retained through Stop/failure/disconnect.
- Stop all includes alignment. Parent close requests Stop and automatically retries
  close after all workers/camera finish; no second click is required. Pending parent
  close suppresses late alignment failure modals.
- A real operation/cleanup failure faults the shared worker. Both workflows refuse
  reuse until application teardown. Clean Stop permits restart.
- New explicit `--hardware-spectrum` route enables real Spectrum and Alignment only.
  The default disabled native route remains unchanged. Map, Annealing and laser
  execution remain gated. Camera retains its independent existing source selector.
- Real wrapper import/construction remains lazy. Source identity, backend, detector
  options and existing source hashes are validated. Deployed wrapper CCD identity,
  ROI, grating and mirror expectations must match the source before construction.
  First-discovered monochromator selection remains an explicit existing limitation.
- No detector-minimum, real acquisition timing, dark-order, one-shot API, profile
  schema, dependency lock, hardware command, package version or SDK change.

Alignment settings are currently per-window, initialized from the source-backed
spectrum draft; this change does not invent profile persistence or a profile migration.
The range panel's output preferences continue using the existing mechanism.

## Scope of real hardware enablement

This is the next bounded native-workspace step, not blanket enablement of all tabs.
The source deliberately gates native map/Annealing/laser, so silently bypassing all
those gates while integrating alignment would be an unrelated hardware rollout.
The header and overview identify Real HORIBA; other native actions remain disabled.
Opening the window does not connect. A source change causes refusal, not fallback.

## Actual validation

Final targeted regression command ran the 25 modules listed below:
**360 passed, 273 warnings in 64.55 seconds**, no failed or skipped tests in that run.
Warnings were Matplotlib/Pyparsing deprecations. This includes 18 new cases across
the runtime and actual Qt-window modules, plus existing standalone, source-validation,
read-only-native, simulation, ownership and spectrum tests.

Environment: Linux, Python 3.12.16, PyQt6/Qt 6.7.1, Matplotlib 3.8.4,
NumPy 1.26.4, pytest 9.2.0, Ruff 0.16.3. Not the locked Windows runtime.
The standard project conftest/QApplication fixture WAS used in this final run.

Actual Qt widgets, event processing, QThreads and Matplotlib raster canvases were
exercised, not mocked GUI methods. The base container lacks libGL/libEGL. To load
Qt for raster-only offscreen testing, temporary loader libraries linked the existing
Chromium ANGLE GLES/EGL libraries and provided abort-on-use GLX entry points. No GLX
entry point was used (it would abort). This loader setup is not shipped and does
not replace Qt widgets or emulate instrument calls. No OpenGL, desktop-window-manager,
Windows rendering or vendor-driver acceptance is claimed from this environment.

Changed-file Ruff check --fix passed on all 11 changed/new Python files using the
repository configuration. compileall passed. Local documentation file-target checks
passed. No full non-hardware suite, hosted CI, build/wheel, physical hardware or
new rollback rehearsal on a lab PC was performed.

An actual 1400x736 offscreen capture of the running simulated Alignment tab was
reviewed against the supplied style. It is an application screenshot, not a mockup
or generated concept image. Windows fonts/platform rendering may differ.

The updater was tested against a fresh copy of the exact baseline: read-only
preflight, all-target conflict refusal before writes, apply, exact installed bytes,
repeat application, CRLF-normalized matching, rollback and refusal to roll back over
later edits. Its validation command/log/exit-code paths were tested separately.
No claim is made that the updater ran on the user's PC before delivery.

### Regression selection

```text
tests/test_operator_spectrum_runtime.py
tests/test_unified_alignment_window.py
tests/test_alignment_cancel_reporting.py
tests/test_alignment_gui.py
tests/test_alignment_lifecycle_acceptance.py
tests/test_alignment_persistent_session.py
tests/test_alignment_spectrum.py
tests/test_alignment_stream_pacing.py
tests/test_alignment_window_acceptance.py
tests/test_spectrum_service.py
tests/test_spectrum_worker_phase4a.py
tests/test_horiba_wrapper_lifecycle.py
tests/test_native_workspace_launch.py
tests/test_native_workspace_window.py
tests/test_native_workflow_binding.py
tests/test_native_workflow_window.py
tests/test_simulated_operator_session.py
tests/test_simulated_operator_window.py
tests/test_workspace_studio.py
tests/test_operator_ui.py
tests/test_workspace_spectrum_transport.py
tests/test_workspace_ownership.py
tests/test_workspace_config.py
tests/test_source_candidate.py
tests/test_native_candidate.py
```

The simulated-window expected tab list was updated to include Alignment. Existing
fault assertions/deadlines were not weakened and no security rule was globally disabled.

## Application and evidence boundaries

Use the single guarded installer against the reviewed branch. It applies complete
files from this inspected baseline rather than rewriting functions from earlier
assistant patches. It accepts newline normalization, refuses other conflicting
edits, keeps backups and supports rollback. `--validate` applies then runs changed-file
Ruff check --fix and the full targeted selection, logging under the ignored backup
folder. Validation failure does not roll back the source or claim acceptance.
`--validate-only` reruns validation without applying payloads. `--print-paths` emits
only the exact delivery paths for staging. No dependency installation, Git staging,
commit, hardware launch or simulation-to-real fallback occurs automatically.

See [unified alignment operation](unified-alignment.md) for exact launch modes,
lab-PC branch update and the connected acceptance checklist.

## Next bounded continuation prompt

Continue from the applied unified Alignment implementation on
feature/unified-gui-alignment. Read the actual current files, Git status/HEAD,
current-state, release-plan, unified-alignment.md and this implementation record.
Inspect the Windows validation output and simulation rehearsal before changing code.
Do not repeat the standalone lifecycle repair or replay old installers. If a new
failure exists, fix its demonstrated cause in one bounded change without weakening
fault assertions, extending deadlines or adding delays to real acquisition. Once
Windows tests and visual rehearsal pass, commit/push this branch and test the explicit
--hardware-spectrum unified GUI on the lab PC. Record the exact commit/configuration,
multiple frames, spectrum/alignment exclusion in both directions, Stop all, restart,
range-to-alignment handoff, fresh dark on/off and close while active. Mark untested
items honestly; the earlier standalone record did not cover dark or active close.
Do not enable native map/Annealing/laser or migrate the strict flat profile in this
checkpoint. After connected unified acceptance, choose the next bounded native
workflow rollout using the existing transport seams and actual evidence, rather
than a broad rewrite or another audit loop. Deliver only evidence-required changes,
actual test results, exact staging/commit commands and the next continuation prompt.
