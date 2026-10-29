# W5 scanning-mirror/LJTick-DAC two-axis preflight

## Input and scope

Input `labtools_source_20261029_092442.txt`, created 2026-10-29T09:24:42,
HEAD `d2e29eb929567cdcc10bdf3fff907044c6815369`, branch
`feature/shared-instrument-session`, upstream +3/-0. Tracked index/worktree recorded
clean; six untracked installers are preserved. Live Git is authoritative.

W5 changes only scanning-mirror DAC conversion/write failure reporting, adds one fake
LabJack test module and updates docs. No Git mutation, hardware, discovery, diagnostics,
service, deployment, account, ACL, dependency, profile or map schema/model change occurred.

## Implementation and preserved contracts

Both requested voltages and both calibrated codes are now computed before the first DAC
write. Voltages and floating calibrated results must be finite; integer codes must be in
0..65535. Conversion still uses `int(voltage * slope + offset)`, preserving truncation.
No clipping, rescaling or invented voltage/travel limit is added.

EEPROM 0x50, register 64, 36-byte request, DAC 0x12, SCL=`dio_pin`, SDA=`dio_pin+1`,
calibration decoding/formula, commands 48 then 49, high/low byte encoding, A-before-B
and home=(0,0) are unchanged. The unproven `255 in response` heuristic is unchanged.

If A fails, its original exception propagates and B is not attempted. If A succeeds and
B raises an ordinary Exception, `MirrorPartialMovementError` states that position is
uncertain and retains the original failure as `__cause__`. No rollback/home/extra write
or LabJack close occurs. BaseException cancellation/interrupt is not wrapped. The mirror
continues to borrow, not own, the LabJack.

## Validation

- Whole-module fake LabJack/I2C tests: **11 passed**.
- Focused mirror/map/session/project selection: **89 passed**.
- Full offline suite: **404 passed, 5 skipped, 172 warnings**.
- Five skips because PyQt6 is absent: QtCore plus four QtWidgets modules. This is not
  acquisition acceptance; no collision-safe map allocation or launcher was implemented.
- Changed-file Ruff format/check, compileall, CLI help, TOML parsing, wheel build and
  native-free mirror-backend import passed. An initial smoke referenced a nonexistent
  factory name and was corrected to import the actual module; no production issue.
- Python 3.12.15, temporary Ruff 0.17.3, pytest 9.1.1. Exact locked Windows environment
  and physical LabJack/LJTick-DAC calibration/wiring are unverified.

Tests stub `labtools.devices.labjack_u6` before importing the complete mirror module and
check exact EEPROM/DAC transcripts, invalid A/B zero-write preflight, boundary/truncation,
A failure, B partial failure, home and borrowed ownership. No u6 import or device access.

## Changed files

Production: `src/labtools/devices/scanning_mirror.py`.
New test: `tests/test_scanning_mirror_preflight.py`.
Relevant handover, roadmap, architecture, audit/plan, development/commands, hardware and
deployment docs are updated, plus this checkpoint. No file is deleted.

## Install, validate, rollback and commit

```powershell
python .\apply_labtools_scanning_mirror_w5.py --check
python .\apply_labtools_scanning_mirror_w5.py --list
python .\apply_labtools_scanning_mirror_w5.py --apply
$changedPaths = @(python .\apply_labtools_scanning_mirror_w5.py --list)
$changedPython = @($changedPaths | Where-Object { $_ -like '*.py' })
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
$env:MPLBACKEND = 'Agg'
uv run --no-sync ruff format --check @changedPython
uv run --no-sync ruff check @changedPython
uv run --no-sync python -m pytest tests/test_scanning_mirror_preflight.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git diff --stat
git status --short
```

Do not enable hardware tests. The guarded installer verifies affected baselines with
LF/CRLF/BOM tolerance, refuses new-file collisions and main/master/detached HEAD, creates
an exact-byte external backup, writes files atomically and restores ordinary partial
failures. It performs no Git/hardware/dependency action and does not claim multi-file
power-loss atomicity.

```powershell
python .\apply_labtools_scanning_mirror_w5.py --rollback 'ACTUAL_BACKUP_DIRECTORY'
```

After review, inspect the whole index and stage only listed files:

```powershell
git add -- @changedPaths
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
git commit `
  -m 'Preflight both LJTick-DAC channels before mirror movement' `
  -m 'Validate finite requests and representable calibrated codes before either I2C write while preserving conversion and byte order.' `
  -m 'Report channel-B transport failure as uncertain partial movement without rollback, home or borrowed-device shutdown.' `
  -m 'Add whole-module fake-LabJack transcript coverage and update wrapper audit, roadmap, handover and release caveats.'
```

## Remaining acceptance and next task

Physical calibration bytes, representable operating voltages, wiring/pins, device
acknowledgements and partial-movement recovery remain maintainer-controlled acceptance.
IDQ `eval(raw)` remains P0 without approved response fixtures. Qt acquisition remains gated.

Next fixture-independent task: UC480 partial acquisition startup/cleanup only, preserving
owned frame copies and existing independent stop/close aggregation. If approved IDQ
fixtures arrive, prioritize parser hardening instead. Do not combine wrappers.
