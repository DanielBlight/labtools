# ITC4000 W1b finite-input contract decision

## Current-setpoint readback contract review (2026-11-05)

**Decision recorded, NOT implemented:** after get_current returns in set_current,
reject a nonfinite readback with RuntimeError before tolerance arithmetic. Include
requested amperes and the observed nonfinite value in the diagnostic. Preserve
finite tolerance, existing mismatch text, query/conversion exceptions and W1 cleanup.
See [readback contract](itc4000-readback-contract.md) for evidence and compatibility.

Authority: labtools_source_20261105_131803.txt, HEAD
013afc9fa6d7b6181de571ffe911383071eaf9ec, branch feature/shared-instrument-session,
upstream +6/-0, clean tracked worktree/index. W1b is committed and all eight W1b
payloads match the implementation backup. Its Windows lint.log/targeted.log/XML
are listed but not exported; their outcomes are not inferred from commit or hashes.
No supplied W1b acceptance failure is demonstrated. New sandbox baseline: 140 passed.

Final targeted characterization: 178 passed (38 new, 96 W1b, 44 lifecycle), zero
failures/errors/skips, 32.91 seconds. Ruff attempt failed to start: No module named
ruff. Local lint remains required. No production or existing test changes; no native
VISA, hardware, actual sleep, physical outputs, full-suite or Qt execution.

Observed current behavior: NaN readback can evade mismatch; positive/negative infinity
mismatch; malformed text raises ValueError after the current write. The recommended
check is post-write verification, not a pre-write interlock. get_current remains raw
float conversion under this decision; direct GUI reads and their second post-set
query are outside the proposed setter-only change. No retry, output-off, new close,
transport fault state, tolerance, enable sequencing, delay or timeout policy change.

Next bounded task: implement only the recorded setter readback guard, revising both
new and existing NaN-readback expectations while retaining finite/tolerance/conversion
and cleanup coverage. ID900 stays deferred with its return instructions unchanged.
This section supersedes earlier next-task pointers for readback scheduling only;
historical W1b and acceptance records below remain scoped to their original evidence.

## Current W1b implementation checkpoint (2026-11-05)

**Constructor/current/temperature finite checks are implemented and fake-transport
validated. Local lint and Windows execution remain unverified.** This section
supersedes historical statements that W1b is only a decision or unimplemented.
It does not broaden W1b into complete finite-input safety or physical acceptance.

Authority: labtools_source_20261105_125159.txt, created UTC
2026-11-05T12:51:59.3162870Z, HEAD 3e41ca827913e022a981b9010d34d82c6dec3a55,
branch feature/shared-instrument-session, upstream +5/-0, tracked worktree/index
recorded clean. The corrected fixture import and _fake binding are the baseline;
no corrected local lint/pytest transcript is supplied. Preserve the original
contract installer backup and separate lint-fix backup; do not restore old payloads.

After both constructor float conversions, math.isfinite checks reject nonfinite
threshold_current and max_current with field-specific ValueError before VISA opens.
Current and temperature setters reject nonfinite converted requests before transport.
Existing bounds, defaults, float coercion/conversion exceptions, units, .9g formatting,
successful command/query order, readback tolerance and W1 cleanup remain unchanged.
No new temperature limit, type whitelist, bool/string rejection or output-off policy.

Fresh baseline: 97 targeted cases passed. Final implementation: 140 passed, comprising
96 finite-contract cases and all 44 unchanged lifecycle cases; zero failures/errors/
skips. All original 53 finite-contract parameter cases remain covered with affected
expectations revised; 43 cases were added. Final duration 26.19 seconds. Tests use
isolated fake PyVISA; sleep/output-enabling paths are stubbed where characterized.
Ruff attempt exited 1: No module named ruff. Offline tool-cache lookup also found no
Ruff. No dependencies were installed; local lint is required before commit.

Only the wrapper, its finite-contract test and six documents change. AST checks
confirm all other production methods are identical; the three changed methods differ
only by the four finite guards. The import of math is the only other source change.
Existing lifecycle tests, callers, schemas, dependencies, limits, simulation and
plotting are unchanged. No full-suite, GUI, native VISA, network or hardware execution.

Enable sequencing/preflight, TEC delay, timeout, nonfinite readback/tolerance and
public-attribute mutation remain excluded and unfixed. Finite temperature extremes
remain accepted by policy, not approved for hardware. A finite current request can
still receive NaN readback without mismatch; enable may still perform TEC work before
current rejection. Pulse methods and other wrappers are unchanged, not certified.
ID900 histogram work remains deferred, P0 open, with its return instructions intact.
No original full-audit, operator-visible, native-SDK or hardware acceptance is claimed.

Next bounded task: review the ITC4000 current-setpoint nonfinite-readback contract
only, using fake replies; record a decision before implementation. Do not combine
with enable sequencing, delays, timeout, output-off policy or ID900 work.

Implementation details: src/labtools/devices/itc4000.py constructor lines 42-88,
set_current 258-288 and set_temperature 294-304. Regression coverage is in
tests/test_itc4000_finite_contract.py and tests/test_itc4000_lifecycle.py.
Historical sections below retain earlier evidence and are not current gate results.

## Status: decision recorded, validation behavior NOT implemented

Authority: labtools_source_20261105_121030.txt, created UTC
2026-11-05T12:10:30.2510517Z. Branch feature/shared-instrument-session, HEAD
c6cd2a96e73c80130f589ed75cb3210bbbfb803f, upstream +4/-0, tracked worktree/index
recorded clean. The ID900 deferral is committed and all six documents match its
installed backup payload. Preserve its instructions and all untracked artifacts.
This assistant uses an isolated reconstruction, not the live Windows worktree.

## Observed implementation and exact references

Source: src/labtools/devices/itc4000.py (baseline line numbers).

- Constructor 41-81: float(threshold_current) then float(max_current), before
  ResourceManager creation. Negative threshold, nonpositive ceiling and threshold
  above ceiling raise ValueError before transport. Defaults remain 0.049 A,
  0.100 A and 5000 ms. Equal threshold/ceiling and zero threshold are accepted.
  Numeric strings and bool values are float-coercible. Invalid strings raise
  ValueError; None raises TypeError, before any fake transport event.
- NaN threshold or ceiling passes constructor comparisons; positive infinite ceiling
  passes, and threshold=ceiling=positive infinity passes. Negative infinities fail
  existing comparisons. Constructor opens/configures VISA and writes *CLS; it does
  not set current or enable outputs. timeout_ms is forwarded unchanged, including
  values the fake accepts; this establishes no real PyVISA acceptance policy.
- set_current 251-278: float conversion precedes inclusive 0 <= current <= max_current.
  With a finite ceiling, NaN/infinities/out-of-range requests raise ValueError before
  writes. A NaN ceiling rejects even finite current. An infinite ceiling permits
  positive infinite current. Accepted values use .9g formatting, then write,
  *OPC?, SYST:ERR?, SOUR:CURR?. No current-setpoint cache is updated.
- Current verification uses max(1e-6, abs(current)*1e-4) and a difference comparison.
  A NaN readback does not trigger mismatch; a finite request with infinite readback
  does. An infinite request/readback can also evade mismatch through NaN arithmetic.
  These are fake-transport observations, not claims about controller replies.
- set_temperature 284-292: float conversion, .9g C-suffixed command, *OPC?, SYST:ERR?.
  No finite or range check and no temperature readback verification. NaN and both
  infinities are formatted and passed to the fake. No temperature limits are inferred.
- enable 205-228: only negative tec_stabilise_s is rejected initially. A numeric
  string delay raises TypeError at comparison; NaN/positive infinity reach the sleep
  call when TEC was off. Tests replace sleep with a recorder, so actual sleep
  behavior is not tested. TEC query/enable/delay precede current validation.
  Invalid current may therefore be discovered after TEC work. No sequencing change
  is made here. disable_diode 159-175 switches off/verifies before threshold reset.
- _write_checked 114-128 and close/context handling 300 onward preserve W1 command
  ordering, acquired-handle cleanup, explicit retry, primary-exception retention
  and idempotent closure. Invalid setters may raise conversion/ValueError before
  closed-state checking; no precedence change is proposed incidentally.

## Callers and documented intent

- runtime/lazy_devices.py:4-12 forwards construction lazily; it adds no validation.
- gui/spectrum_gui_horiba.py:73-75, 469, 1020-1024, 1090-1100 uses 0.049/0.100 A
  constants, a bounded GUI control, explicit construction and float current requests.
- gui/intensity_map_gui.py:1373-1377 and 1470-1485 uses the same composition pattern.
  UI bounds are not a guarantee for direct wrapper callers; no GUI execution here.
- acquisition/run_hyperspectral_scan.py:94,117 constructs the wrapper with defaults.
  This legacy acquisition entry point was read, never run.
- Existing lifecycle tests assert negative threshold fails before transport and
  preserve startup/close transcripts; they do not establish finite-value policy.
- docs/itc4000-lifecycle-checkpoint.md explicitly leaves finite-input policy W1b
  open. Existing max_current is a caller-configured ceiling, not an independently
  approved physical operating limit. No new laser or TEC safety policy is inferred.

## One recommended decision

Adopt a narrow finite-input boundary for constructor current configuration and
current/temperature setters, implemented only in the next separate checkpoint:

1. Retain float coercion and its existing TypeError/ValueError behavior. Do not
   add a new type whitelist, bool rejection, string rejection or trimming policy.
2. After both constructor float conversions, reject nonfinite threshold_current
   and max_current with field-specific ValueError before ResourceManager creation.
   Then retain the existing ordered bounds: threshold >= 0, max > 0, threshold <= max.
3. After setter float conversion, reject nonfinite current/temperature with
   field-specific ValueError before any transport. Retain current bounds, units,
   .9g formatting, existing finite temperature behavior and no new temperature range.
4. Preserve defaults, timeout forwarding, successful command/query order, readback
   tolerance, cache behavior, lifecycle cleanup and exception identity. No source
   changes implement these rules in this checkpoint.

Intentional compatibility change: nonfinite constructor/temperature values and
infinite-current requests with an infinite ceiling will no longer reach transport.
Previously valid finite values, numeric strings and coercible bools remain accepted
subject to existing bounds. No real-device safety or operating-range approval follows.

## Alternatives and explicit exclusions

- Preserve all nonfinite behavior: rejected as the future policy because constructor
  comparisons can admit unusable ceilings and temperature commands can contain nan/inf.
- Strict numeric types/bool rejection or new temperature/current limits: rejected
  for W1b; breaks additional compatibility or invents device/configuration policy.
- Broaden to enable sequencing, delay/timeout validation and nonfinite readbacks:
  deferred to separate decisions. These are observed gaps, not silently fixed by
  finite setter checks. The next implementation must not claim complete finite-input
  safety: enable may still perform TEC work before rejecting current; a finite
  request may still receive a NaN readback. No automatic diode/TEC-off is authorized.
- Mutation of public max_current/threshold_current after construction is not prevented
  by this decision. Do not add properties, immutability or new mutation semantics.

## Characterization evidence

New tests/test_itc4000_finite_contract.py reuses the existing isolated fake-PyVISA
fixture from test_itc4000_lifecycle. It does not load native VISA or contact hardware.
53 new parameterized cases plus 44 existing lifecycle cases: 97 passed, zero failures,
errors or skips, 20.29 seconds. This is current-behavior characterization, not a test
of the proposed policy. Future implementation must explicitly revise affected
characterization expectations; do not delete coverage or keep incompatible tests.

Command: PYTHONPATH=src python -m pytest -q tests/test_itc4000_finite_contract.py
 tests/test_itc4000_lifecycle.py (single command; XML/logs in delivery evidence).
Lint attempted: python -m ruff check tests/test_itc4000_finite_contract.py.
Exit 1: No module named ruff. Lint is blocked, not passed; no dependencies installed.
No full-suite, GUI, native-SDK or hardware gate rerun. Production and existing tests
are unchanged. Recorded historical Windows acceptance is not broadened.

## Exactly one next bounded task

Implement only the constructor/current/temperature finite checks above, preserving
W1 lifecycle behavior. Revise characterization cases to assert the decided ValueError
and zero transport effects for rejected values; keep finite/boundary/conversion
transcripts and lifecycle tests. Do not change enable sequencing/delay, timeout,
readback policy, laser safety, other wrappers or ID900 scheduling.

IDQ ID900 histogram work remains deferred pending approved evidence; P0 stays open.
Do not select fixture collection merely because another snapshot is supplied.
Actual local owner acceptance and v4 raw-artifact verification outputs remain absent;
original audit, operator-visible, native-SDK and hardware acceptance are not claimed.
