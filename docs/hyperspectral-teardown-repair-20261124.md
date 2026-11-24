# Hyperspectral thread teardown repair, 2026-11-24

## Observed Windows failure

The supplied mirror-update validation has NOT passed. The shutter/mirror/SC10
cleanup tracebacks followed by PASSED are intentional fault-injection output.
The final 30-second faulthandler dump is different: validation stops at
`test_worker_control_exception_reports_failure_and_reaches_idle[error1]`,
inside `HyperspectralController._clear`, line 89 (`self.thread = None`).
A faulthandler_timeout prints stacks; it does not itself terminate a hung test.
No final 475-pass or Targeted validation passed marker was supplied for this run.
Do not record the earlier Linux pass as Windows acceptance.

## Narrow repair

The controller source was read from the supplied 18:15:10 export, HEAD
2f0312d0cbdc3434281d9eed3f816430de2f3e42. Its contents were unchanged by the
subsequent mirror update. This installer accepts that exact controller hash
(normalising CRLF/BOM) or the already-installed repaired hash. It prints actual
HEAD/status and does not assume whether the mirror changes have been committed.
It touches only this controller, a new regression test and this note. Mirror
controls, sequence positioning, output retention and profiles are not replaced.

Previously, QThread.finished queued thread.deleteLater and _clear, and _clear
immediately dropped thread/worker references. Qt finished is not a native join:
thread-local/deferred/Python teardown may still be completing. Dropping wrappers
at this boundary is consistent with the observed hang. The stack alone does not
prove every native/GIL detail, so Windows confirmation remains required.

The repair parents QThread to the controller and retains both references until
thread.wait(0) reports native teardown complete. If not ready, a 5 ms GUI timer
retries the zero-time join. There is no blocking GUI wait, deadline extension,
forced terminate, test reorder, removed assertion or real-acquisition delay.
Only after join does the controller release wrappers, schedule thread deletion
and emit idle once. Busy remains true throughout teardown; restart remains refused.
Worker deletion retains the standard thread.finished -> worker.deleteLater link.

## Evidence and limits

- Focused lifecycle selection: 21 passed in 12.46 s.
- All hyperspectral test modules in ordinary lexical order, capture enabled:
  112 passed, 13 warnings in 17.52 s. This includes the six new tests.
- New tests include a deterministic finished-but-not-joined probe (busy and refs
  retained, no idle, restart refused), plus 20 runs each of success, RuntimeError,
  CancelledError, KeyboardInterrupt and SystemExit with GC pressure and native
  join verified at idle. Existing lifecycle/worker assertions are unchanged.
- The exact installer-focused order, original failing worker module first:
  21 passed, 13 warnings in 10.88 s.
- Ruff check --fix and compilation passed. Updater smoke passed in a temporary
  Git checkout: read-only preflight, conflict refusal, exact apply, idempotency,
  guarded rollback, original restoration and preservation of unrelated applied
  mirror work. No user Git checkout was changed.
- No physical hardware was opened. No new Windows pass is claimed.

A broader Linux mixed GUI run segfaulted in the unchanged retained_run_controls
QTimer callback. A separate workflow run also failed to complete. The unmodified
export's experiment-panel selection independently segfaulted in this environment,
so that broader problem is not established as a regression of this repair. It is
not counted as a pass and is not silently fixed in this bounded controller patch.
The evidence archive includes the incomplete runs as well as completed results.
This delivery certifies only the stated targeted Linux tests. Python3.12/Qt6 uses
offscreen raster with temporary Chromium ANGLE loader shims in this environment.
Windows validation and normal GUI rehearsal remain the relevant next checks.

## Apply

Stop the stalled validation with Ctrl+C. If the console remains unresponsive,
end only that validation Python process, not unrelated Python/Labtools processes.
Close Labtools before applying. Do not rerun or roll back the mirror installer.

Save install_hyperspectral_teardown_20261124.py in Downloads:

```powershell
Set-Location "C:\Dev\labtools"
py "C:\Users\mbcx4db7\Downloads\install_hyperspectral_teardown_20261124.py" --repo "C:\Dev\labtools" --validate
if ($LASTEXITCODE -ne 0) { throw "Hyperspectral teardown repair or validation failed" }
```

The installer backs up originals, refuses conflicting edits, supports guarded
rollback and logs actual command exits. It installs no dependencies, connects no
hardware and makes no Git changes. Its first test command runs the original
failing worker audit, then lifecycle/reaping tests. It also runs all hyperspectral
modules, and runs tests/test_workspace_mirror_position.py separately if present.
The latter test is expected on the applied mirror checkout but is not claimed as
locally rerun here because the supplied export predates that new file.

The previous mirror installer's --validate-only hashes include this controller as
an unchanged anchor, so it will correctly refuse after this repair. Use this new
validation entry point; do not bypass the older installer's hash guards. The new
validation is targeted and is not a claim that the entire original 816-test mirror
selection has been rerun on Windows.

After validation, launch normal simulation:

```powershell
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" -m labtools workspace launch "examples\workspace\working-lab\candidate.json" --simulate --simulation-realtime
```

Rehearse Mirrors Move/Home/close/reopen, a non-home baseline-first Spectrum
sequence, Stop and close cleanup. Preserve the existing reviewed optical setup
and local profile for later connected checks; this repair changes no limits.

## Git commands

If the mirror update is still uncommitted, stage it too using its existing
--print-paths output before committing this repair. Review staged scope:

```powershell
$paths = @(py "C:\Users\mbcx4db7\Downloads\install_hyperspectral_teardown_20261124.py" --print-paths)
if ($LASTEXITCODE -ne 0) { throw "Cannot obtain repair paths" }
git add -- $paths
if ($LASTEXITCODE -ne 0) { throw "Git staging failed" }
git diff --cached --stat
git commit -m "Retain hyperspectral worker ownership until native thread teardown completes"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed" }
git push
git rev-parse HEAD
git status --short
```

## Next bounded continuation prompt

Continue from the applied hyperspectral teardown repair over the mirror-position
update. Inspect actual HEAD/status, current controller and Windows validation log.
Do not mark the earlier timed-out mirror validation as passed. Confirm the original
worker control-exception audit, repeated lifecycle tests and native-join-before-idle
regression complete without hanging, reordering tests or extending deadlines. Keep
mirror/sequence-position changes intact. Rehearse normal GUI Move/Home/close/reopen,
non-home Spectrum sequence baseline/post-anneal targets and Stop/active-close cleanup.
Record exact Windows results separately from Linux and from connected acceptance.
If a hang remains, capture the complete log and current source before further edits;
do not mask it with ordering or timeout changes. Commit the intended mirror and
repair scope only after review, then perform small connected checks at that exact
revision with the existing reviewed profile/laser policy. Deliver observed evidence,
exact Git commands and the next bounded prompt.
