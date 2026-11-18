# Offline validation evidence runner

This guide supersedes older output-location and full-gate skip instructions for
`scripts/validate_source_audit.py`. It does not supersede historical test results.

## Purpose

The existing source-audit runner now fails acceptance if any selected pytest gate
records failures, errors, skips, zero tests, missing XML or malformed XML. A process
exit of zero alone is not acceptance. Hardware exclusions are not test passes.

No instrument imports occur in the runner itself. Its full selection uses the
repository's current hardware-exclusion hooks and `-m "not hardware"`, never
`--run-hardware`. This is not an operating-system sandbox: maintain hardware markers
and fake-device tests when adding tests.

## Validate this tooling change only

From the repository root, using the existing environment:

```powershell
uv run --no-sync ruff check --fix scripts/validate_source_audit.py tests/test_source_audit_runner.py
uv run --no-sync pytest -q tests/test_source_audit_runner.py
```

The runner tests use temporary repositories, simulated child results and short
Python-only child processes. They do not run the acquisition suite or use Qt/devices.

## Future validation, only when new source changes justify it

```powershell
uv run --no-sync python scripts/validate_source_audit.py --gate all
```

Do not run this now merely to replace an already accepted full-suite result.
`all` retains the existing lint/core/widgets/full sequence. Individual gates remain
available, but only `all` can set `all_gates_passed=true`. Core/widgets overlap with
full; counts from separate gates must not be added together as unique coverage.

Lint uses `ruff check --fix src tests scripts/validate_source_audit.py`. If it edits
Python/configuration inputs, the runner stops before subsequent tests and records
changed paths. Review and retain/revert those edits explicitly; it does not undo them.

Evidence defaults to a unique `labtools-source-audit-<timestamp>` directory beside
the repository. A custom `--output` must be outside the repository and must not
already exist. Existing evidence is never overwritten. No Git operations are run.
Source hashes cover Python files under src/tests/scripts and pyproject.toml/uv.lock;
they are content provenance, not proof of a clean or committed Git checkout.

Each gate records its exact command, exit status, timeout/interruption state and raw
combined stdout/stderr log. Pytest uses verbose test names and `-ra`; full explicitly
selects `tests`. JUnit counts and before/after source hashes are retained in
`results.json`. Child environments use QT_QPA_PLATFORM=offscreen and MPLBACKEND=Agg;
the parent shell environment is unchanged. Existing 60/240/600-second limits remain.

The console prints the active gate and log path, not a live stream. If needed, inspect
that log from a second terminal with `Get-Content -LiteralPath '<printed log path>' -Tail 30`.
Ctrl+C during a gate stops only the child process tree owned by the runner and records
an incomplete gate. Timeout, interruption and skips never establish acceptance.

Native drivers, connected devices, physical safety, operator acceptance and deployment
remain separate. Do not use this runner to authorize hardware execution.
