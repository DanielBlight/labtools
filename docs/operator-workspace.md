# Operator workspace (annealing first phase)

The annealing workflow includes recipe/profile validation and GUI load/save controls.
Intensity mapping has a standalone launcher and explicit simulation; named recipe migration is not implemented.
Camera preferences and existing QSettings persistence are retained. Recipes exclude hardware
connections, maintainer limits, camera preferences and safety acknowledgements.

## Maintainer setup

Review examples/profiles/instrument.example.json. All example limits and coordinates are
unverified starting values, NOT a power calibration. Set real instrument limits and a unique
profile_id, then set approved to true only after review. Install the profile at
C:/ProgramData/Labtools/instrument.json and use Windows permissions to allow operators read
access but no modification. Do not use a user-writable profile for a protected deployment.
LABTOOLS_INSTRUMENT_PROFILE overrides the path for development/testing; it is NOT a security
boundary. An operator able to execute arbitrary Python can bypass these software guardrails.
Do not treat the approved flag as independent evidence of calibration or safety.

For the DEVELOPMENT checkout only, run uv sync after source changes to refresh entry points. The cleanup does not edit uv.lock;
review any lock changes produced by uv sync. Do not install development code editable in the
protected deployment. Build/install a tested wheel with a separately created environment and
machine-accessible Python. Keep vendor drivers/DLLs available to each account. Windows ACL
setup and production deployment are deliberately NOT performed by the cleanup.

## Operator use

labtools init "C:/Users/OPERATOR/Documents/Labtools Experiments"
labtools doctor
labtools validate "C:/Users/OPERATOR/Documents/Labtools Experiments/recipes/anneal.json"
labtools gui anneal

Use Load recipe / Save recipe / Save recipe as / Restore recipe defaults in the GUI.
Profile hardware fields override GUI hardware preferences. Requested maximum open time may
be reduced but cannot exceed the profile. Recipe load clears the optical-path acknowledgement.
Load/save/reset is refused during an anneal. Recipe loading does not connect or move hardware.
Manual stage moves are checked against profile coordinates before confirmation.

The CLI anneal command operates hardware only with --confirm-optical-path. Physical checks
and interlocks remain essential. Editable runner examples default to validation only.

## Metadata and limitations

Existing metadata.json includes resolved dataclass settings plus instrument_profile_id,
instrument_profile_sha256 and software_version. The profile digest identifies the resolved
profile, not a digital signature. The existing maximum-open-time check is an estimate based on dwell and settle, not an
independent hard shutter deadline. Native driver calls can block. Hardware interlocks remain
required. This update does not change acquisition timing or device shutdown.

This update preserves existing camera and serial shutdown code; it does not fix driver hangs.
The existing QSettings values are per-user convenience settings, not named recipes.
Only maintainers should change the installed core; operators edit their workspace.

## Existing scripts

Direct calls to run_laser_anneal(LaserAnnealConfig(...)) now require resolved profile metadata.
Migrate them to build_config(recipe, profile); the GUI is patched to resolve the profile.
Existing hardware integration tests may need corresponding fixtures. The profile check runs
before the public anneal function opens devices. Internal helpers and direct device wrappers
are not a security boundary. The cleanup does not modify those wrappers.


## Migration history

Historical migration backups may exist in `.labtools-migrations`; keep them out
of Git. Do not rerun older migration installers against the refactored source.
The current cleanup uses `.labtools-refactor-backups` and its own guarded rollback.

## Protected lab-PC deployment

Use the [deployment runbook](lab-pc-deployment.md) for reviewed wheels, separate
operator workspaces, standard accounts, protected profiles/code and side-by-side
updates/rollback. Do not run uv sync against the production environment or install
editable source for operators. The guide is proposed and requires local IT/Windows
acceptance; it does not change permissions or deploy software by itself.


## Hyperspectral simulation GUI plotting checkpoint

The public scripted hyperspectral measurement remains frozen and Qt-free. The operator GUI remains simulation-only and presents a synthetic NaN-safe raw spectral sum, completion mask, click-selected completed pixel, and an immutable selected spectrum in wavelength nanometres against mirror voltages. Typed progress intentionally contains no partial arrays, so live spectral/map plotting is not implemented. GUI resume, multi-recipe pipelines, anneal dispatch, and real-hardware execution remain unsupported. The legacy runner is not the GUI backend. `--confirm-real` applies only to guarded scripted execution and is not a GUI safety control. HORIBA exclusion remains process-local. Offline Qt tests and synthetic plots are not physical, calibration, timing, optical, Windows-native SDK, or Qt-production acceptance.
