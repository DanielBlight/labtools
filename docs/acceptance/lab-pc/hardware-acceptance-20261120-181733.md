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
