# HORIBA alignment

The alignment window submits repeated, complete single-centre jobs through
`SpectrumWorker` and `SpectrumService`. Jobs are sequential; a second spectrum client
is rejected while one job owns the worker. Stop is cooperative at the existing
service boundary and does not forcibly interrupt a native SDK call.

Exposure uses the existing detector preset minimum: 0.065 s for Syncerity and
0.1 s for Symphony. Alignment does not override the wrapper minimum. With dark subtraction enabled, each update
captures a fresh closed-shutter dark followed by a signal; wavelength axes must match.
Raw and corrected arrays remain distinct in the immutable result.

An injected worker is application-owned and survives window close. A standalone
window creates a private worker and closes it after active cleanup. A real job failure
faults the worker and requires application teardown; there is no simulation fallback.

No physical HORIBA, shutter-timing or optical alignment validation is claimed. Presets
may move grating/exit-mirror hardware. Launch the standalone module only in a reviewed
setup with `LABTOOLS_SPECTRUM_CONFIGURATION_ID` set:

```powershell
uv run --no-sync python -m labtools.gui.alignment_gui_horiba
```
