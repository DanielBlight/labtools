# Working-lab configuration migration

This migrates settings from labtools_working_lab_20261119_113535.txt, captured from
C:\Users\mbcx4db7\Downloads\labtools, into the development project's existing recipe
and disabled native-candidate mechanisms. It does not modify that working lab copy,
load device modules, contact hardware, import its code, or replace saved preferences.

## Use the populated candidate, not the blank template

```powershell
uv run --no-sync labtools workspace preflight examples/workspace/working-lab/candidate.json
```

Expected: exit 0, inputs_complete=true, execution_enabled=false, hardware_opened=false,
environment_probed=false, input_errors=[], and explicit runtime_inputs. Complete means
source configuration is internally consistent, NOT that native operation is accepted.
No native controls, default factories or execution switches are enabled by this batch.

The five JSON files in examples/workspace/working-lab are source-backed configuration,
not simulated data or invented physical identities:
- candidate.json: schema 2 references, software identity and logical resource labels;
- profile.json: map wiring/software envelope, selection policies and both detector presets;
- map.json: existing strict native map recipe using working GUI startup defaults;
- spectrum.json: existing strict Syncerity recipe using working GUI startup defaults;
- source-record.json: original capture SHA-256, source-section hashes, claim values,
  file/line references and distinctions between defaults and external runtime state.

The source record is a migration record, not a new approval document. It does not
assert physical serials for the LabJack or monochromator. No source text is executed.
Logical labels such as working-lab-u6 identify reservations, not discovered devices.
Schema 1 manifests remain supported unchanged; schema 2 removes the irrelevant
anneal-profile/SC10/stage fields and the requirement for five separate review references.
It reuses the existing recipe loader, reservation authority and transport boundaries.
The binding plan retains the profile as hardware_settings and hashes all five inputs;
source changes after preflight are refused by the existing disabled service binder.
The current wrapper remains authoritative for device setup; this batch does not add
profile-driven hardware execution or silently change its grating/ROI/serial checks.

## Migrated values

Counter: 169.254.99.159, SCPI port 5555. Mirror SCL DIO 2, SDA DIO 3, DAC A/B X/Y,
zero home. Gate DIO 0, active high. Map software envelope -10 to +10 V. Startup grid
-2 to +2 V, 40x40, 0.100 s integration, 0.010 s settling, channel 1, 0.1 V threshold,
rising edge, serpentine, existing source output directory. These are startup defaults,
not last-used lab-PC QSettings values. Simulation/checkpoint compatibility fields
and recipe owner labels use the existing development schema, not physical settings.

Syncerity: index 1, expected serial Camera SN: 926, 1024x256, full-height binning,
SECOND grating, AXIAL exit. Symphony: index 0, Camera SN: 26070, 512x1, THIRD grating,
LATERAL exit. Both preserve source gain/speed option tokens and exposure floors.
Spectrum startup recipe: Syncerity, 600-900 nm, 0.5 s, gain 2, speed 0, slit 0.5 mm,
one frame, single combine, 20-pixel overlap, no pre-taken dark. The source README's
shared SDrive-500 TTL/shutter caveat is retained in the source record. Its older
statement about presets not forcing grating is not used to override actual code.

## Authorized anneal limit alignment

Only the default software envelope changes from -5/+5 to -10/+10 V in
InstrumentProfile, LaserAnnealConfig and instrument.example.json. The example stays
unapproved. No scan endpoints, timing, shutter, rotation-stage, cleanup or interlock
logic changes. Existing explicit local profile limits are NOT overwritten; an existing
-5/+5 profile remains -5/+5. A profile omitting those fields inherits the new defaults.
This is the user's authorized software-envelope change, not a hardware-rating claim.
No migration writes %PROGRAMDATA%, QSettings or the Downloads working project.

## Validation

```powershell
uv run --no-sync ruff check --fix src/labtools/config/native_candidate.py src/labtools/config/source_candidate.py src/labtools/config/anneal_workspace.py src/labtools/acquisition/laser_anneal.py tests/test_source_candidate.py tests/test_native_candidate.py tests/test_anneal_workspace.py
uv run --no-sync pytest -q -ra tests/test_source_candidate.py tests/test_native_candidate.py tests/test_anneal_workspace.py tests/test_anneal_startup_policy.py tests/test_anneal_cleanup_review.py tests/test_laser_anneal_lifecycle.py tests/test_workspace_map_transport.py tests/test_workspace_spectrum_transport.py
```

The delivered validation record gives actual sandbox results and limitations. Ruff
could not be installed in this sandbox and is not claimed passed. New tests forbid
native/GUI imports. Existing offline anneal tests require import-only u6/serial
sentinels here because those packages are absent; sentinels refuse construction and
are not delivered as project code. This is not SDK compatibility or hardware acceptance.
No Qt tests or full suite are rerun for this configuration/default-only change.

## Remaining runtime inputs and release direction

LabJack selection is still u6.U6(), monochromator first discovered. Physical identities,
installed ICL/calibration/runtime state, saved GUI preferences and actual shared-shutter
state are not recoverable from the source capture. They are runtime checks, not a
reason to manufacture more approval files. Source-backed input completeness is not
connected-device acceptance. Next compose the actual native workspace route with
explicit operator selection and the migrated settings in one coherent batch, preserving
worker affinity and existing session ownership. Keep execution disabled unless the
user authorizes native enablement; no more fake-only/profile-search milestones.

Base development source: 598b214907551ebc32d87642d9774fa1dfa4bf95. The working lab source
is separately linked by capture/section hashes; do not confuse it with development HEAD.
Historical 801-test evidence remains at 235f70ca..., wheel/staging at 6074fdad...,
startup-policy validation at 607c7db.... No packaging or ID900 changes.
