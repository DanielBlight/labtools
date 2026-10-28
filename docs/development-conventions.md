# Development conventions

Authoritative rules for humans and coding models. Architecture/status is in
[architecture](architecture.md); bounded work is in [roadmap](refactor-roadmap.md).

## Change discipline

1. Inspect actual files, pyproject.toml, consumers and Git status before editing.
   Snapshot history is context, not proof that another run's changes exist.
2. Preserve known-working device commands, units, limits, timing, checkpoint
   signatures, QSettings keys and launch/import paths unless a separately reviewed
   behavior change has tests and a migration note. No stylistic wrapper rewrite.
3. Work on a feature branch. Review existing dirty files; do not discard or reset
   them. Commit a tested baseline/checkpoint before applying another phase. Do not
   merge to main merely because offline tests pass. Never commit automatically.
4. Complete one bounded slice with tests and handover. Report code/doc conflicts;
   do not redesign the architecture during a bounded migration task.

## Names, placement and dependency direction

Use snake_case modules/functions, descriptive capability names, PascalCase classes,
and unit suffixes (_s, _ms, _nm, _v, _a) where applicable. Retain established APIs.
config/: validated requests/recipes/profiles, no Qt/native imports.
devices/: SDK/transport wrappers. processing/: pure math and data validation.
acquisition/: reusable experiment/service logic and data results, no GUI imports.
runtime/: factories, lifecycle, session adapters and backend composition.
simulation/: explicitly synthetic implementations, no native imports.
gui/: widgets, Qt workers/controllers and presentation only.
io/: persistence/export, no dialogs or hardware. visualisation/: plotting helpers.
Use absolute labtools imports. Import native SDKs lazily at real composition
boundaries where practical; do not add eager imports to package __init__ files.
Keep existing compatibility shims; new code imports canonical locations.

## Types and contracts

Use narrow structural Protocols for consumed capabilities. Do not introduce ABCs,
base classes, plugin registries or universal fake devices without a concrete need.
Use frozen dataclasses for immutable request/result records. Frozen does not make
NumPy buffers immutable: copy/own published arrays; new spectrum records use
bytes-backed read-only vectors. Validate finite values, bool-vs-int distinctions,
unknown fields, shape and units before opening devices. Do not infer real readbacks
from requested settings. Public new APIs should be typed; private helpers may be
inferred. No configured static type checker currently exists; do not claim one ran.

## Lifecycle and failure behavior

New constructors normally store/validate configuration. Explicit connect opens;
legacy eager constructors remain behind factories until migrated. One owner closes
a connection. Borrowed mirror/gate objects must not close their parent LabJack.
Factories clean partial startup; once a handle is returned, the receiving owner
must release it on later construction failure. A vendor constructor that raises
before returning its handle remains a vendor/factory limitation to document.

Keep construction/use/close on the owning thread/asyncio loop. Do not return native
handles from session services. Do not call a session recursively from its worker.
Reserve all physical resources for the whole job plus cleanup, not per command.
Mirror and gate alias the same LabJack. Default exclusive, non-reentrant leases;
owner labels are diagnostic, not authorization. No fault reset/reconnect shortcut.
Cleanup after fault uses only the configured argument-free allowlist.

Close successfully once; report failures and unknown state. Independently attempt
reviewed cleanup actions. Preserve a primary error with secondary exception notes;
without a primary error, report cleanup failures (ExceptionGroup where useful).
Catch BaseException only to ensure cleanup then immediately re-raise. Do not catch
and suppress broad exceptions or report successful cleanup merely after issuing a
command. Existing suppressions are migration debt, not precedent for new code.
Preserve vendor exception causes. Do not manufacture safety-state guarantees.

## Services, cancellation and GUI integration

A service owns experiment policy; wrappers own commands; GUI owns presentation.
Inject factories/services/controllers. No GUI-to-GUI hardware access, global
singleton or duplicated dark math. Future shared windows receive dependencies from
one application root; standalone launchers create their own explicit composition.

Long operations run off the UI thread. Cooperative cancellation uses a thread-safe
Event/callback or reviewed asyncio job mechanism; queued slots cannot interrupt a
blocking worker. Do not force-kill threads or release a lease before cleanup ends.
Do not cache HORIBA objects across AsyncTaskRunner operations. Its WebSocket loop
ownership requires one persistent asyncio worker before connection reuse.
Use bounded latest-result buffering for live displays; do not queue every frame.
Tool closure and application shutdown are distinct lifecycles.

## Spectrum and simulation

New spectrum consumers use SpectrumService and SpectrumSettings. Keep old
range_spectrum/DarkSpectrum imports for legacy consumers. DarkRecord provenance is
required for new reusable-dark subtraction; never bless a CSV by attaching current
settings. All settings currently invalidate reuse. No exposure scaling or silent
raw fallback. Keep negative corrected values. Fresh-dark raw availability is None.
Preserve existing mean/population-std single-pass clipping and dark capture order.

Choose real/simulation explicitly in composition; reject backend mismatch. A
synthetic success never validates SDKs, wiring, shutters, calibration or timing.
Mark exported synthetic data and retain backend/model/configuration provenance.
Do not modify existing map model/version/seeding or resume signatures casually.

## Configuration and logging

Extend existing strict JSON recipe/profile approach rather than introducing a
second configuration framework. Profiles contain maintainer hardware identity,
wiring/limits/calibration; recipes contain operator experiment choices. QSettings
is convenience only. Never persist safety acknowledgement, emission-enabled state
or a claim that a connection survived restart. Keep secrets/machine overrides out
of Git. Profile approval is not independent calibration or a security boundary.
Use module logging consistent with adjacent code (existing loguru/stdlib). No
root logger setup in reusable modules, no secrets, no hidden cleanup failures.

## Testing and validation

Unit-test wrappers with injected transports; service tests use fake/synthetic
backends. Contract tests exercise both the real adapter with a fake wrapper and
the synthetic adapter. Test invalid-before-open, partial startup, every cleanup
stage, cancellation, primary-error preservation, fault latch, stale leases and
backend mismatch. Keep imports offline-safe. AST-extracted legacy tests are useful
but do not replace real module/adapter tests.

Qt tests must use fake devices, isolated settings and offscreen subprocesses;
keep worker references until QThread.finished. Hardware tests require the hardware
marker AND --run-hardware. Known native-importing test modules must be excluded
before import in tests/conftest.py; a post-import marker alone is insufficient.
Never run hardware scripts or --run-hardware automatically.

Run the commands in development.md and handover. Report skips, warnings, failed or
unavailable tools and dependency-version differences. Format/lint changed files
when ruff is available; do not mix a whole-tree formatting sweep into a migration.
No physical validation claim from mocks. Update architecture only for real design
changes; update roadmap/handover for completion, tests, limitations and next task.

## Adding instruments, simulations and tools

Instrument: identify physical resource key and consumers; document units/lifecycle/
threading; wrap transport; test partial startup/close; add reviewed narrow service
and lazy factory; define cleanup policy with hardware owner before GUI exposure.
Simulation: implement the same consumed contract and state transitions, explicit
backend selection/provenance and shared contract tests; state model limitations.
Service: accept validated settings and injected capability/context factories;
separate math/persistence/UI; add cancellation and failure tests.
Tool: inject service/controller, register lazy standalone launcher if needed;
retain existing aliases and settings. Shared-app registration is planned, not an
implemented plugin API. Never open a competing connection in a tool constructor.

Deprecation/removal requires a repository consumer search, documentation/example/
entry-point review and operator confirmation for external scripts. No removal of
compatibility code solely because internal imports have moved.
