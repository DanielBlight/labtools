# Unified native candidate: mapping, spectroscopy and annealing

## Starting evidence and scope

Base: 6f547acffd34935bf1953115d2a440bdd261d9a2, nine-path operator-binding commit,
clean tree/index in labtools_evidence_20261119T125704Z.txt. Captured local lint passed;
the captured pytest command ran the OLDER launch selection (101 passes, no skips),
not the full new operator-binding selection. The user reports the operator window
opened/worked but did not retain settings. Do not relabel those 101 tests as complete
operator-binding acceptance. Earlier integrated acquisition rehearsal is unconfirmed.

This is the coherent three-workflow candidate/persistence integration portion of
release step one. Native execution remains gated because separate explicit enablement
was not supplied. It is not a claim of a hardware-enabled or release-accepted build.
No hardware operations, discovery, SDK probes, new registry, packaging or ID900 changes.

## Launch and persistence

```powershell
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json
```

The window contains Configuration/preview, Intensity map, Spectrum and Annealing.
Save operator settings explicitly, or close cleanly to save automatically. Reopen to
restore valid acquisition, output and display preferences for all three workflows.
Preferences live under %LOCALAPPDATA%\Labtools\native-workspace\<configuration-hash>.json
(or ~/.local/share/Labtools/native-workspace on non-Windows). The exact path and restore
messages appear in the source-status report. No standalone/simulation QSettings,
source recipes, working-lab copy or local instrument profile is overwritten.

Preferences use an atomic replace and a whitelist. They never include connected state,
laser output, shutter state, active runs, reservations, dark archives, physical-device
identities, addresses, pins, software limits or approval fields. Camera exposure/gain/
display interval can be remembered but camera start is never restored. Confirmation
checkboxes always reset. Source/local-profile hash changes invalidate stale preferences;
invalid saved workflows fall back independently with diagnostics. Failed writes leave
the previous file intact. Closing after a save failure offers an explicit discard
choice rather than silently losing settings. Preview remains non-executing.

Map grid/integration/channels/thresholds/output, spectrum preset/range/exposure/options,
anneal grid/passes/dwell/return policy/output and selected display/output preferences
are remembered. A source profile change can intentionally reset them; preferences
cannot expand a source envelope or replace physical connection settings.

## Annealing integration and limits

The existing LaserAnnealWindow and AnnealWorker are embedded, not rewritten. The
anneal data contracts moved unchanged into config/anneal_types.py, and the acquisition
module re-exports them for existing imports. GUI acquisition injection is optional;
standalone defaults still call the original run_laser_anneal. Native wrapper imports
are lazy so merely displaying the panel does not import hardware packages.

The unified panel uses existing anneal defaults and shared source mirror wiring and
software envelope (-10/+10 V), NOT invented physical approval. SC10/stage/camera
settings are labelled unprobed. The spectroscopy TTL shutter and anneal SC10 are not
assumed interchangeable. Shutter/stage startup, cancellation, cleanup and return-stage
acquisition algorithms are unchanged. Manual shutter/stage/camera operations and
anneal Start are disabled/refused just like map/spectrum native actions.

If an existing local anneal instrument profile is present at the existing configured
path, its explicit narrower voltage/time/stage policies are respected and its hash is
retained. It is never created or marked approved by this batch. An explicit file can
be selected without editing source:

```powershell
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json --anneal-profile 'C:\path\to\existing\instrument.json'
```

That path is an example, not an actual installed profile. A missing/invalid explicit
profile is reported and anneal preview refuses; map/spectrum inspection still opens.
A local wiring mismatch also refuses. No profile means source-default anneal draft
inspection only, not permission to run or a replacement for connected acceptance.

## Ownership, cancellation and execution wiring

The same WorkspaceOwnership/InstrumentSession instance now reserves Annealing as a
third workflow. It shares the actual existing map LabJack logical resource and shared
optical-path resource, and adds logical anneal shutter/stage/camera labels. Those labels
are not serials or evidence that the physical devices have been selected. Mapping and
spectroscopy do not unnecessarily reserve anneal-only devices. Shared optical exclusion
prevents all three conflicting workflows from overlapping. No persistent native handles
or new device manager is introduced. Existing two-workflow simulation configuration
remains compatible; optional anneal_resources is validated by the same config class.

The existing anneal worker receives workspace.acquire_anneal. The native runtime
validates the draft and hits the same unconditional execution refusal before native
imports, just as map/spectrum. Public UI actions also refuse before workers start.
A trusted direct worker invocation still refuses and retains/releases its reservation
through thread cleanup. The existing map and spectrum thread/async-loop boundaries
are unchanged. Stop all attempts each active workflow; close waits for worker/camera
teardown before saving settings and closing the shared authority.

This batch does not remove any native gate, auto-connect, operate a shutter/stage,
start a camera or laser, or claim connected-device readbacks. The unified candidate
is ready for local offline/UI acceptance, not yet lab hardware execution. Native
activation remains a separately authorized part of step one before connected testing.
Do not add another simulated-only or profile-search milestone.

## Validation and source linkage

The guarded updater's --validate mode runs ruff check --fix on all changed Python
paths, one focused pytest selection (including three-workflow persistence/ownership,
actual Qt roundtrip/worker cleanup, existing map/spectrum boundaries and anneal
startup/cleanup/lifecycle), and a headless launch. It writes one evidence snapshot
outside the project in Downloads, including command output, JUnit, Git state and
selected project text. Failures/skips are retained; no hardware operations are run.
Review that text for sensitive source content before uploading. It does not commit.

Actual sandbox focused selection: 215 passed, 3 Qt skips in 266.77s, exit 0.
The skips are missing libGL.so.1, not acceptance. A targeted widget-float preference
roundtrip passed separately after correcting integer-JSON versus float-widget restore;
final profile-envelope/schema edge tests also passed separately. These are not added
together as a fabricated full-run count. Ruff check --fix passed on all changed Python.
The delivered record/log retains the exact outcomes. Qt tests must actually pass locally. Import-only u6/serial
sentinels were needed for existing sandbox anneal tests and refuse construction;
they are not delivered or used by local validation. No SDK compatibility or hardware
acceptance follows from those tests. Existing acquisition function ASTs are unchanged.

Working-source profile/recipes/source-record remain untouched. New preference hashes
reference those same source stamps plus an existing local anneal profile if loaded.
Historical full-suite evidence remains at its original revisions: 235f70ca... for the
801-test checkpoint, 6074fdad... for wheel/staging and 607c7db... for startup policy.
No historical count is promoted to current acceptance.

## Remaining release route

1. Accept this unified UI/persistence batch locally, including save/close/reopen and
   the actual Qt tests. Confirm exact scope and clean commit using the evidence file.
2. With explicit authorization, complete native activation/device-selection integration
   for all three workflows together. Keep operation-scoped handles and existing policies.
3. Connected-device acceptance on the lab PC: actual identities, ICL/runtime, shutter/
   stage/camera configuration, data correctness, cancellation/error cleanup and transitions.
4. Only after acceptance: freeze, release regression, deployment/update and rollback.

No further approval-document exercise, registry or fake-only milestone is required.
