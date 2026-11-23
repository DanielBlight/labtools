# HORIBA persistent-alignment hardware acceptance

## Record identity

- Status: PASS: persistent Start/Stop alignment lifecycle
- Recorded: 2026-11-23 11:36:22 +00:00
- Computer: E-U11XX530705P
- Windows user: PLUCS
- Branch: `main`
- Tested source commit: `714405a2cdee2667db2d4a0fcf3261b93cc98627`
- Configuration ID: `working-lab-20261119-source-defaults`
- Python: `Python 3.12.13`
- uv: `uv 0.11.32 (3010295ae 2026-07-23 x86_64-pc-windows-msvc)`

## Connected alignment observations

- Standalone alignment GUI launched successfully: Yes
- Multiple spectra acquired through one Start session: Yes
- Stop completed and returned the GUI to an available state: Yes
- Second Start worked without restarting Python or rebooting: Yes
- No complete HORIBA reconnect observed between displayed frames: Yes
- Dark-subtracted continuous alignment tested: Not tested
- Close while active waited for cleanup and completed: Not tested
- Issues observed: None

## Scope

This is bounded connected-HORIBA evidence for the standalone persistent-alignment
lifecycle at the tested commit. It does not approve the unified-workspace integration,
all detector configurations, all failure modes, packaging, deployment rollback, or the
complete release candidate.

The required lifecycle result is based on multiple frames, normal Stop, restart without
application relaunch, and the absence of a complete reconnect between displayed frames.
Entries marked Not tested remain open acceptance items.

## Follow-up

Alignment should next be integrated into the unified workspace by reusing the existing
`SpectrumWorker.start_alignment` stream. The workspace must hold spectrum ownership
through Stop or close cleanup and must not create a second private native connection.