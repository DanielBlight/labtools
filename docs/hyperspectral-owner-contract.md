# Hyperspectral owner-label contract decision

## Status and scope

Decision recorded on 2026-11-05: preserve provider-owned reservation labels.
This is a compatibility-preserving design decision supported by characterization,
not an implementation of request-label propagation. No production source changes.

Authority: labtools_source_20261105_111524.txt, created UTC
2026-11-05T11:15:24.3826927Z. Branch feature/shared-instrument-session, HEAD
1bdef873daaa94e84e0455eb1e80b73d9a330a77, upstream +1/-0. Tracked worktree/index
recorded clean. All untracked measurement data, validation artifacts, installers
and v2/v3/v4 backups are preserved. The assistant works on an isolated reconstruction,
not the live Windows worktree. No Git mutation or hardware access was performed.

## Observed behavior, before this decision

- measurements/hyperspectral.py:29-38: HyperspectralRequest.owner defaults to
  scripted-hyperspectral. validate() rejects a string with an empty strip().
  It does not trim stored nonblank labels. This is not a new promise about all
  non-string inputs; no validation policy is broadened here.
- measurements/recipes.py:83-105 and 170-188: recipe serialization/loading retains
  the request owner. It is request/recipe data, not currently an archive provenance
  field or a reservation credential.
- measurements/dispatch.py:177-183 and 241-247: sync/async dispatch forwards the
  recipe request and runtime.hyperspectral; it does not map the label to a provider.
  measurements/runtime.py lazily composes that runtime by backend, not by owner.
- measurements/hyperspectral.py:73-106: real session-backed runtime composition
  constructs HyperspectralMirrorProvider(session) without an owner override.
  An explicit mirror_factory is retained; session plus mirror_factory is rejected.
- measurements/hyperspectral.py:165-203: acquisition validates the request and
  uses runtime.mirror_factory without consuming request.owner. An injected runtime
  is borrowed; a facade-created runtime is closed. The characterization uses a
  fake service seam for facade lifecycle, not a physical acquisition.
- runtime/hyperspectral.py:26-36: the default provider label is hyperspectral-service.
  Explicit provider labels are used as supplied. The provider reserves mirror
  in an async context and releases the lease on exit.
- runtime/hyperspectral.py:40-65: the factory is called without arguments. Mirror
  context entry precedes spectrum operation entry; exit unwinds in reverse order.
  Custom providers remain responsible for their own reservation/cleanup contract.
  Retaining a custom factory is not a guarantee that arbitrary custom code reserves
  resources, releases them, or avoids native SDKs.
- runtime/session.py:38-69 and 125-173: aliases resolve to physical resources;
  conflicts use physical-resource intersection. Each reservation receives a fresh
  token. Owner labels are diagnostics stored with leases, not authorization or
  reentrancy keys. Equal labels still conflict on the same physical resource.
  This is process-local coordination, not cross-process exclusion or an interlock.

The different defaults are therefore not evidence of reservation bypass.

## Decision

Reservation-label authority stays with the runtime/provider that actually reserves
resources. Keep both existing defaults and keep the current request-label validation
and recipe representation. Do not silently propagate request.owner, mutate a reused
provider, infer permission from a label, or change custom-provider call signatures.

This decision makes the existing separation explicit: a request label describes
request data; the provider label identifies the actual session reservation. It does
not claim request.owner currently affects acquisition, archive provenance, spectrum
ownership or safety. Existing explicit provider construction remains the way to
choose a session reservation label. The provider is an internal composition boundary,
not a new public export.

## Alternatives considered

1. Automatically propagate request.owner into the default provider. Rejected for
   this checkpoint: changes visible reservation diagnostics and requires decisions
   about borrowed/reused runtimes, per-request concurrency and custom factories.
   It would not improve token-based exclusivity by itself.
2. Remove or rename request.owner. Rejected: breaks request/recipe compatibility
   and requires an explicitly versioned migration.
3. Add a new runtime owner parameter. Deferred: no demonstrated need for another
   API, and explicit providers already support labels. No feature is added here.

## Characterization and limitations

New tests: tests/test_hyperspectral_owner_contract.py, 26 parameterized cases.
They cover request defaults/nonblank whitespace preservation and recipe round trips;
blank-label rejection; default/explicit provider labels; same/different-label
contention through mirror/gate/labjack aliases; exception identity and lease release;
actual task cancellation; owned/borrowed facade lifecycle with default/explicit
providers; and no-argument custom factories with reverse-order context cleanup.

Device factories deliberately raise if opened. No device movement, native SDK,
network connection or real acquisition is required, despite the real-backend config
used to select session-backed composition. Existing session and cleanup regressions
are included in the targeted run.

Final targeted command (PYTHONPATH=src in the sandbox):

```text
python -m pytest -q tests/test_hyperspectral_owner_contract.py tests/test_session_core.py tests/test_hyperspectral_service.py::test_session_provider_reserves_before_open_and_releases_after_operation tests/test_measurements_hyperspectral_contract.py::test_runtime_borrowed_resources_are_not_closed tests/test_audit_hyperspectral_regressions.py
```

Result: 60 passed, zero failures/errors/skips, 29.00 seconds. The 26 new cases are
included in 60, not additional. No full suite or Qt gate was rerun. An earlier draft
had a collection error from incorrect recipe helper names; that test-only error was
corrected to the actual save_recipe/load_recipe API before the final run.

Lint attempt: python -m ruff check tests/test_hyperspectral_owner_contract.py.
Result: exit 1, No module named ruff. This is an environment prerequisite failure,
not a lint pass or a reported lint finding. No dependencies were installed.

The original Windows run remains recorded as Ruff passed, core 68, widgets 12,
full offline 608, zero recorded failures/errors/skips/timeouts. The actual v4 evidence
output and raw logs/XML contents remain absent. No local raw-artifact verification,
original historical comparison, visible operator acceptance, native-SDK acceptance
or hardware acceptance is newly claimed.

## Bounded future implementation plan

No production implementation is required to adopt this compatibility decision.
If a later requirement needs per-request reservation diagnostics, first specify an
explicit opt-in contract and ownership rules for borrowed/reused runtimes. Then
propose a separate implementation with tests for custom providers and concurrency;
never mutate an existing provider implicitly. Schema changes, archive provenance
and label removal require separate decisions, not incidental cleanup.

## Next independent bounded task

Read-only IDQ histogram fixture-readiness audit: inventory existing representative
response fixtures and the get_histogram eval(raw) path, then document the accepted
input grammar only where supported by real supplied fixtures. If fixtures are
missing, report the exact missing examples and stop before parser implementation.
Do not collect hardware responses automatically, execute untrusted responses, invent
fixtures or combine this with IDQ/DLT ownership redesign.
