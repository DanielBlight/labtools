# Native workspace candidate: read-only preflight and disabled composition

This is the native input/composition boundary, not another fake-only workspace mode.
It reuses the existing strict measurement recipes, instrument-profile loader, map and
spectrum transport boundaries, and InstrumentSession-backed workspace ownership.
It adds no native execution command, device registry, connection discovery or GUI.

## Current repository evidence

The supplied snapshot confirms 1732f1dc965bd02f6825fe9cf917ff3d2bd042d5 and the eight-path
transport-composition commit. The tree is NOT clean: acquisition/intensity_map.py and
visualisation/intensity_map.py are modified and tests/test_map_export_worker.py is
untracked. These are the prior worker-export correction and must be committed, not
lost or overwritten. The snapshot omits untracked file content; the delivered export
regression test was used in sandbox validation, not represented as inspected local bytes.
No successful local test summary or integrated rehearsal confirmation accompanied the
snapshot. A commit alone does not close that acceptance milestone; skipped Qt is not
acceptance. No historical counts are reconstructed.

## Inspect missing native inputs without opening hardware

```powershell
uv run --no-sync labtools workspace preflight examples/workspace/native-candidate.template.json
```

The blank template deliberately returns exit code 2 with a JSON report listing all
13 missing input fields. This is expected, not an installer/test failure. A complete,
consistent manifest returns 0 but ALWAYS reports execution_enabled=false. There is no
--execute, --enable or native GUI route. Existing standalone commands are unchanged;
this new guard does not disable unrelated historical standalone hardware commands.

Copy the template outside versioned examples and reference existing local reviewed
files; do not manufacture new approval paperwork when an existing source suffices.
Relative references resolve against the manifest directory. The same existing review
file can satisfy several review-reference fields if it actually covers those topics.
The code checks file presence/content hashes, not the meaning or authority of prose.

Exact inputs:
- configuration_id: reviewed identity shared with SpectrumSettings.configuration_id.
- resources.labjack, resources.counter, resources.spectrometer, resources.optical_path:
  explicit resource identities. Mirror/gate use the LabJack lease; both workflows use
  the same optical-path lease. Resource labels are not connection addresses.
- instrument_profile: existing strict InstrumentProfile JSON, reviewed/approved via
  its existing loader. Only shared mirror limits/pins/home/grid are cross-checked;
  no anneal code or policy is changed. The checked-in example is unapproved.
- map_recipe: existing strict intensity_map recipe, backend=real, no resume directory.
  It explicitly includes address, mirror/gate pins, thresholds/edges, integration,
  scan grid, output path and voltage envelope. No defaults are filled by preflight.
- spectrum_recipe: existing strict spectrum recipe, backend=real, matching identity,
  dark_mode=none and no pre-taken archive. It explicitly specifies preset, exposure,
  gain/speed, slit, wavelength range, overlap and frame combination.
- device_selection_review: existing source mapping identities to actual selected
  LabJack/counter/detector/monochromator and explaining any selection limitations.
- wiring_review: existing source for mirror I2C pair, gate pin/polarity and routing.
- operating_limits_review: existing source for channel thresholds, exposure/slit,
  wavelength/detector settings and electrical/optical operating envelope.
- native_environment_review: intended SDK/driver/runtime source, not auto-probed here.
- optical_path_procedure: existing optical-path/beam/shutter procedure reference.

No real values are invented in the template. The existing native LabJack factory has
no serial-selection argument; resource identity in a manifest is not proof of physical
selection. That remains an explicit connected-device integration/acceptance issue.

## Consistency and provenance

Preflight rejects missing/unknown/duplicate manifest fields, missing references,
unapproved profile, wrong recipe kinds/backends, identity mismatch, mirror-pin mismatch,
voltage envelope exceeding the profile, unsupported nonzero home, grid over profile
limit, and gate overlap with the mirror I2C pins. The existing map wrapper homes to
zero; preflight reports unsupported reviewed settings rather than changing hardware.
The base spectrum recipe is rejected before any pre-taken dark archive is opened.

A successful plan retains the actual recipe settings, source paths and SHA-256 hashes.
Binding rechecks hashes and the exact resource layout. This is source linkage, not
cryptographic approval or a security boundary against arbitrary Python code.

## Disabled service composition

DisabledNativeCandidate accepts a successful plan, the existing ownership object and
explicit trusted factory objects. It constructs the existing map/spectrum boundary
objects, but no device or second session. Public map, spectrum and dark operations
raise NativeExecutionDisabled even if every input is complete and a lease is held.
There is intentionally no production factory import or switch to turn that off.

Native handles remain operation-scoped in the existing boundaries. No handle is moved
to the reservation executor or retained across event loops. Fake transport regressions
cover cancellation, cleanup and recovery; the disabled candidate itself cannot execute
those operations, which is the intended invariant.

## Validate

```powershell
uv run --no-sync ruff check --fix src/labtools/cli.py src/labtools/config/native_candidate.py src/labtools/runtime/native_candidate.py tests/test_native_candidate.py
uv run --no-sync pytest -q -ra tests/test_native_candidate.py tests/test_workspace_transport_composition.py tests/test_workspace_map_transport.py tests/test_workspace_spectrum_transport.py tests/test_spectrum_service.py tests/test_intensity_map_simulation.py tests/test_map_export_worker.py tests/test_intensity_map_visualisation.py
```

Ruff 0.17.4 check --fix passed on all four changed Python paths. The completed
candidate regression passed 143 tests with one Qt-runtime skip and 236 plotting-library
deprecation warnings in 170.30s. It includes 26 new input/disabled-composition tests,
existing fake transport cancellation/cleanup/recovery tests, and worker-export checks.
An initial foreground attempt hit the tool time limit; the completed retry is the
reported result. The missing Linux libGL runtime still prevents actual Qt acceptance.
The validation record delivered with this batch retains these results.
No skipped Qt test is GUI acceptance. No hardware, packaging, ID900 parsing or anneal
changes. Historical 801-test evidence remains at 235f70ca..., wheel/staging at
6074fdad..., startup-policy validation at 607c7db.... New results do not relabel them.

## Remaining release gates

1. Commit/validate the worker-export correction and confirm actual integrated Qt
   rehearsal on the development PC; do not infer it from a snapshot.
2. Supply authoritative existing native inputs and review the preflight diagnostics.
3. Resolve actual device selection and native environment compatibility. A syntactically
   complete manifest is not approval and cannot enable this candidate.
4. Only after explicit authorization, implement native operator execution and perform
   connected-device acceptance. Persistent shared connections are not required.
5. Release build/deployment remains a later authorized task; none is performed here.

Next task should bind the actual supplied inputs and resolve concrete selection gaps,
not add another simulated layer, approval checkbox or speculative audit. If inputs
remain unavailable, report the exact missing fields and stop short of hardware enablement.
