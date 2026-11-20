# Lab-PC hardware acceptance record

## Baseline

- Date: 2026-11-20 18:17:33 +00:00
- Computer: E-U11XX530705P
- Windows user: PLUCS
- Branch: `lab-pc/0.2.0-rc1-validation`
- Commit: `8675769986253a6c3a97a028bfa6d2c2b85d34cf`
- Tag: ``
- Python: `Python 3.12.13`
- uv: `uv 0.11.32 (3010295ae 2026-07-23 x86_64-pc-windows-msvc)`

## Camera

- Status: PASS, initial hardware acceptance
- Camera detected successfully: Yes
- Preview operated successfully: Yes
- Exposure/gain response checked: Yes
- Camera released after closing: Yes
- Notes:

## HORIBA spectroscopy

- Status: PASS, initial hardware acceptance
- ICL version: `4.0.3.9`
- Symphony/Synapse serial: `26070`
- Syncerity serial: `926`
- Monochromator detected: Yes
- Syncerity configuration verified:
  - Grating: `SECOND`
  - Exit mirror: `AXIAL`
  - Requested centre: `690.000 nm`
  - Reported centre: `689.999 nm`
  - Exposure: `0.100 s`
  - Gain token: `2`
  - Speed token: `0`
- Spectrum acquisition worked: Yes
- Shutter diagnostic status: Diagnostic compatibility correction required
- Diagnostic correction:
  - replaced obsolete `acquire_frame` calls
  - closed frames use `get_dark_spectrum`
  - open frames use `get_spectrum`
- Final shutter open/closed comparison: PENDING

## Intensity-map hardware

- Status: PARTIAL PASS
- IDQ address: `169.254.99.159`
- IDQ port: `5555`
- Lab-PC interface: `Ethernet 3`
- Lab-PC source address: `169.254.139.124`
- TCP connection succeeded: Yes
- PyZMQ required and installed: Yes
- Native map started: Yes
- Mirror movement completed: Yes
- Map acquisition completed: Yes
- Counts: `0` at every point
- Count-input acceptance: PENDING
- Settings used:
  - Primary channel: `1`
  - Threshold: `-0.500 V`
  - Edge: `Rising`
  - Integration time: `0.100 s`
  - Laser output: `OFF`
- Follow-up checks:
  - verify physical IDQ input channel
  - try `Falling` edge for negative pulses
  - verify SPAD power, bias and gate indication
  - inspect live channel frequency in the IDQ application
  - verify LabJack gate-output operation

## Keithley

- Status: NOT TESTED

## ITC4000

- Status: NOT TESTED
- Laser-diode output must remain OFF for initial connection/readback testing.

## Laser Annealing

- Status: NOT TESTED
- Separately gated.
- Begin with laser output disabled.
- Verify shutter closure, mirror/stage return, cancellation and partial-start cleanup before powered operation.

## Candidate assessment

- Offline validation: PASS
- Camera initial acceptance: PASS
- HORIBA initial spectrum acceptance: PASS
- HORIBA shutter comparison: PENDING
- Mirror/map orchestration: PASS
- IDQ count-input acceptance: PENDING
- Keithley acceptance: PENDING
- ITC4000 read-only acceptance: PENDING
- Laser Annealing acceptance: PENDING

## Additional notes

Add observations, output locations, device serial numbers, driver versions and recovery actions here.

## ITC4000 shutdown-current correction

- Status: PASS
- Controller VISA resource: `USB0::0x1313::0x804A::M00739898::INSTR`
- Controller maximum current: `0.040 A`
- Previous shutdown threshold: `0.049 A`
- Previous failure: `-222, Data out of range`
- GUI threshold current after correction: `0.040 A`
- GUI maximum current after correction: `0.040 A`
- Shutdown target is clamped to `min(threshold_current, max_current)`.
- Connection succeeded: Yes
- LD output enabled under approved conditions: Yes
- Output OFF completed without exception: Yes
- Physical LD-output indicator confirmed OFF: Yes
- Reconnection after shutdown succeeded: Yes

## HORIBA Spectrum GUI acceptance

- Date: 2026-11-20 18:41:44 +00:00
- Branch: `lab-pc/0.2.0-rc1-validation`
- Commit: `f7e86d19ccbfff69b9850b8575e879f6f2204fcc`
- Configuration ID: `working-lab-20261119-source-defaults`
- Configuration source: `examples/workspace/working-lab/candidate.json`
- Spectrum GUI launched successfully: Yes
- Connected HORIBA hardware successfully: Yes
- Spectrum acquisition completed: Yes
- Output saved successfully:
- Dark correction tested:
- Stop and restart tested:
- Clean close and reconnect tested:
- Issues observed: None during this test

## Laser Annealing profile and dry-run acceptance

- Date: 2026-11-20 18:55:37 +00:00
- Branch: `lab-pc/0.2.0-rc1-validation`
- Commit: `ffc1dac8c9a4d428eaf8d26571ce3702809ed443`
- Installed profile: `C:\ProgramData\Labtools\instrument.json`
- Profile ID: `working-lab-20261120-lab-pc`
- Approved profile loaded by GUI: Yes
- ITC4000 LD output remained physically OFF: Yes
- Initial SC10 state was closed: Yes
- One-position unpowered dry run completed: Yes
- Shutter closed after completion: Yes
- Mirror returned to configured home: Yes
- Rotation stage: No failure observed during the completed dry run
- Second dry run started successfully: Yes
- Stop-after-current-point tested: Yes
- Cancellation closed shutter: Yes
- Cancellation returned mirror home: Yes
- Issues observed: None during the completed one-position dry run
- Powered annealing tested: No

## Minimal powered Laser Annealing acceptance

- Date: 2026-11-20 18:57:06 +00:00
- Branch: `lab-pc/0.2.0-rc1-validation`
- Commit: `8d28f3b326c42b08a21f69f5ac4716ca88b51ece`
- Profile ID: `working-lab-20261120-lab-pc`
- Positions: `1`
- Passes: `1`
- ITC4000 current: `0.040 A or below`
- ITC4000 output enabled as intended: Yes
- SC10 opened only for the requested dwell: Yes
- SC10 closed after acquisition: Yes
- ITC4000 output switched OFF successfully: Yes
- Physical LD-output indicator confirmed OFF: Yes
- No `0.049 A` shutdown request: Yes
- No `-222 Data out of range` error: Yes
- Mirror returned home: Yes
- Rotation stage returned or was disabled: Yes
- Output and log created: Yes
- Reconnection after cleanup succeeded: Yes
- Issues observed: None
- Powered Annealing acceptance: PASS

## RC2 profile freeze

- Date: 2026-11-20 19:01:01 +00:00
- Candidate commit: `428498c4d05b3e9bacf57809af362dd1c9046d3b`
- Installed profile: `C:\ProgramData\Labtools\instrument.json`
- Profile ID: `working-lab-20261120-lab-pc`
- Profile approved: `True`
- Profile SHA-256: `6C84299417A132B829CB0FE257443CB3AD22C6C0017B0408AEA745F1D22D17C7`
- Previous rollback tag: `v0.2.0-rc.1`
- Camera acceptance: PASS
- HORIBA Spectrum acceptance: PASS
- ITC4000 shutdown-limit acceptance: PASS
- Intensity-map orchestration: PASS
- IDQ nonzero count-input acceptance: PENDING
- Laser Annealing dry-run acceptance: PASS
- Laser Annealing cancellation acceptance: PASS
- Minimal powered Laser Annealing acceptance: PASS

## HORIBA Alignment GUI hardware finding

- Date: 2026-11-20 19:10:02 +00:00
- Branch: `main`
- Commit: `3329ff7172d3fc1496ffbe3863b21fc6134d7e07`
- Configuration ID: `working-lab-20261119-source-defaults`
- Alignment spectra acquired: Yes
- Observed lifecycle: a new HORIBA connection was opened for every spectrum
- Expected lifecycle: one connection per Start/Stop alignment session
- Hardware acceptance: FAIL
- Impact: excessive initialization latency and unsuitable continuous-alignment performance
- Required correction:
  - connect once when alignment starts;
  - configure once unless settings change;
  - acquire repeated frames through the same worker-owned session;
  - disconnect once after Stop or window-close cleanup;
  - preserve single-client ownership and faulted-worker behavior;
  - never reuse a connection from a different asyncio event loop.
- Previous standalone GUI remains archived for later comparison.

## HORIBA Alignment follow-up

- Date: 2026-11-20 19:35:01 +00:00
- Lab-PC baseline commit: `54ce3563385734f49be567e27530562a14c64014`
- Current Alignment hardware behavior: opens a new HORIBA connection for every spectrum
- Previous old-main behavior: one connection per Start/Stop alignment session
- Hardware acceptance: FAIL, persistent-session regression
- First repair attempt: rolled back after focused lifecycle tests failed
- Focused repair result: `6 failed, 21 passed, 2 teardown errors`
- Release baseline remains unchanged and usable for discrete Spectrum acquisition
- Required development-PC work:
  - persistent worker-owned HORIBA backend context;
  - explicit one-frame request and GUI acknowledgement;
  - no free-running frame producer;
  - cooperative Stop after current capture;
  - exactly one disconnect after cleanup;
  - preserve configuration identity, exposure floors, ownership refusal and fault handling.
