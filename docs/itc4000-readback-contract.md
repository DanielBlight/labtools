# ITC4000 current-setpoint nonfinite-readback contract

## Status and authority

Decision recorded; readback handling is NOT implemented. Production source and all
existing tests are unchanged. This checkpoint adds characterization and documentation.

Authority: labtools_source_20261105_131803.txt, created UTC
2026-11-05T13:18:03.8991125Z. Branch feature/shared-instrument-session, HEAD
013afc9fa6d7b6181de571ffe911383071eaf9ec, upstream +6/-0. Tracked worktree/index
recorded clean. W1b is committed as Reject nonfinite ITC4000 constructor and setpoint
inputs; all eight installed W1b payloads match the implementation backup.

The snapshot lists .labtools-validation/itc4000-w1b-implementation-20261105T1315522235677Z/
lint.log, targeted.log and targeted.xml, with manifest metadata but no exported
contents. Their local outcomes cannot be established. Installed tool versions and
a commit are not acceptance. No actual W1b failure is supplied. We proceed with a
read-only behavior review and fresh fake-PyVISA baseline, not a local acceptance claim.
Preserve all installer backups, the separate lint-fix backup, validation artifacts,
measurement data and unrelated files. Work is an isolated reconstruction, not the
live Windows checkout. No Git mutation or hardware access.

## Observed source and caller references

Baseline line references in src/labtools/devices/itc4000.py:

- _query:107-110 checks session state, calls the instrument query and strips its
  response. It does not parse a number or wrap transport exceptions.
- _write_checked:119-133 writes, queries *OPC?, then SYST:ERR?.
- set_current:258-288 converts/validates the finite request and existing bounds,
  performs the checked current write, calls get_current, then computes tolerance
  max(1e-6, abs(current)*1e-4). Only abs(readback-current) > tolerance raises the
  existing RuntimeError mismatch. The write has already happened before readback.
- get_current:290-292 returns float(_query("SOUR:CURR?")), with no finite check.
- _retain_cleanup:89-93 attaches cleanup structurally as _itc4000_cleanup_failures
  and notes without replacing the primary error. close:404-436 independently closes
  handles; __exit__:442-449 preserves a body exception when close also fails.
- Existing tests/test_itc4000_finite_contract.py:93-102 already covers nan, inf and
  finite mismatch 0.09 for requested 0.05. It is unchanged in this review.
- Existing tests/test_itc4000_lifecycle.py covers successful transcript, owner-thread
  execution, startup/close failures, primary exception identity and cleanup retry.

Callers (read only, not executed):
- gui/spectrum_gui_horiba.py:1088-1102 calls set_current then separately get_current;
  the latter value is used for the UI. Connection/output paths also read current at
  1027, 1063 and 1079.
- gui/intensity_map_gui.py:1466-1491 similarly calls set_current then get_current;
  connection/output paths also read current at 1381, 1425 and 1453.
- Wrapper enable:234 and disable_diode:184 call set_current internally. Their existing
  sequencing remains outside this contract. No output commands are added here.

No conflict was found between current source and W1b's explicitly excluded readback
policy. Historical sections describe earlier baselines and are not current acceptance.

## Characterized behavior, not controller/firmware claims

All replies below are injected fake data. No claim is made that hardware emits them.

- nan, NaN, signed/whitespace NaN convert to float NaN. The difference comparison is
  false, so set_current can return success. No extra query, close, retry or output-off.
- Positive/negative infinity and overflow-form numeric text such as 1e309 convert
  to infinity and raise existing mismatch RuntimeError for a finite request.
- Matching finite forms, including whitespace/scientific notation, preserve success.
  Both signs of the absolute floor and relative tolerance were checked using adjacent
  representable floats inside/outside the boundary. Finite behavior is unchanged.
- Empty/whitespace, malformed numeric text and unit-suffixed text raise ValueError
  from float after the write and three verification queries. No wrapping occurs.
- Nontext fake replies None/numeric objects fail at .strip with AttributeError,
  not a float TypeError. This is a fake transport contract violation, not wire grammar.
- Sentinel objects with strip/float hooks establish conversion ValueError/TypeError
  identity; they are test doubles, not possible instrument text.
- Query OSError/TimeoutError/KeyboardInterrupt/CancelledError retain identity through
  context cleanup. Mismatch/conversion failures remain primary if both closes fail;
  the existing cleanup group is attached with notes. Explicit close retry is preserved.
- Direct get_current returns nan/inf/-inf as floats today. This review does not change
  that getter, the GUI's second query or other readback consumers.

## One recommended decision

Add a setter-only post-conversion readback guard in a separate implementation:

Immediately after readback = self.get_current() in set_current, before tolerance
arithmetic, use math.isfinite(readback). If false, raise RuntimeError with this
specified diagnostic format:

    Current readback is nonfinite: requested {current:.9g} A, controller reports {readback!r} A.

This is a verification failure after a command, not invalid request ValueError and
not proof the output was unchanged or safe. It must not claim rollback or certify
physical current. No automatic retry, new query, output-off, close or fault state.

Preserve the existing tolerance formula and strict > comparison for finite replies,
including current mismatch exception type/text. Preserve float conversion and its
exceptions, query exception identity, successful command order and W1 context cleanup.
Do not catch/replace the new error with a cleanup failure; existing __exit__ already
retains the primary and attaches cleanup. No new cleanup mechanism is needed.

## Alternatives and compatibility

- Put the guard in get_current: deferred, not selected. That broadens direct getter,
  GUI connection/output and second-query behavior. It needs a separate consumer review.
- Wrap all malformed/query errors in RuntimeError: rejected here; breaks conversion
  and transport exception compatibility and can obscure cancellation/interrupts.
- Retry, automatically switch outputs off or fault the session: excluded safety/
  recovery-policy changes. No instrument state is inferred from a nonfinite reply.
- Change tolerance or accept a finite substitute: rejected; unrelated to the NaN gap
  and risks masking a failed verification.

Intentional future compatibility change: NaN setter readback will no longer report
success. Infinite setter readbacks remain RuntimeError but gain the explicit
nonfinite diagnostic instead of generic mismatch. Finite matching/mismatching replies,
conversion failures and direct getter behavior stay unchanged. This is not complete
laser safety, transport hardening or validation of every readback. Enable sequencing,
TEC delay, timeout, public attribute mutation, temperature limits, other wrappers,
schemas, dependencies, detector limits and real/simulation behavior stay separate.

## Evidence and validation

Fresh sandbox W1b baseline: 140 passed in 25.79 seconds. This is not Windows evidence.
Final targeted command, with PYTHONPATH=src in the sandbox:

    python -m pytest -q tests/test_itc4000_readback_contract.py tests/test_itc4000_finite_contract.py tests/test_itc4000_lifecycle.py --junitxml=<new evidence path>

Result: 178 passed, comprising 38 new readback cases, 96 unchanged finite-contract
cases and 44 unchanged lifecycle cases; zero failures/errors/skips, 32.91 seconds.
The new module reuses the existing isolated fake-PyVISA fixture and its corrected
explicit fixture re-export convention. No native VISA is loaded.

Draft test corrections: an initial collection error used pytest's reserved request
parameter name; it was renamed requested. Three draft assertions used the wrong
cleanup attribute spelling; corrected to the actual _itc4000_cleanup_failures tuple.
These were new-test errors, not production defects. Final logs/XML supersede drafts.

Lint attempt: python -m ruff check tests/test_itc4000_readback_contract.py.
Exit 1: No module named ruff. Lint is unverified, not passed. No dependency installed.
Syntax checking and targeted pytest do not substitute for local Ruff.

No full-suite/Qt rerun, actual sleep, native SDK, network, hardware or physical output
enabling. No original full-audit, operator-visible, native-SDK or hardware acceptance
is claimed. Actual original v4 raw-artifact verification and prior local owner
acceptance output remain absent. ID900 histogram P0 stays deferred with its return
instructions unchanged; a new snapshot alone is not a reason to select collection.

## Exactly one next bounded task

Implement only the setter readback guard specified above. Update the new NaN/infinite
characterization expectations AND existing finite-contract NaN/inf expectations;
retain direct getter, finite tolerance, conversion/query exception and W1 cleanup
coverage. Add exact new diagnostics and primary-error retention tests as needed.
Do not implement this during the contract review or broaden it to getter/GUI/safety.
