# Operator workspace (annealing first phase)

The installer adds recipes/profile validation and GUI load/save controls for laser annealing.
Intensity mapping receives a launcher only; its recipe migration is not implemented here.
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

Run uv sync after installation to refresh entry points. The installer does not modify uv.lock;
review any lock changes produced by uv sync. Do not install development code editable in the
protected deployment. Build/install a tested wheel with a separately created environment and
machine-accessible Python. Keep vendor drivers/DLLs available to each account. Windows ACL
setup and production deployment are deliberately NOT performed by this installer.

## Operator use

labtools init "C:/Users/OPERATOR/Documents/Labtools Experiments"
labtools doctor
labtools validate "C:/Users/OPERATOR/Documents/Labtools Experiments/recipes/anneal.json"
labtools-anneal

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
are not a security boundary. The installer does not modify those wrappers.

Backups live in .labtools-migrations; do not commit that folder. Rollback checks hashes and
refuses to overwrite files changed after installation, including by a formatter.
