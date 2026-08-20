# labtools

Python tools for laboratory automation, instrument control, spectrum acquisition, data processing and experimental diagnostics.

The package currently focuses on:

- HORIBA iHR spectrometer and CCD control
- stitched wavelength-range acquisition
- Syncerity and Symphony detector selection
- open-shutter and dark-frame acquisition
- repeated-frame averaging and outlier rejection
- reusable dark spectra
- ITC4000 laser-controller operation
- PyQt6 acquisition interfaces
- reproducible hardware diagnostics

## Project status

The HORIBA range-acquisition workflow is operational, including:

- CCD and monochromator discovery
- wavelength-axis calibration
- stitched range acquisition
- Slit A control
- grating-position readback
- repeated-frame combination
- acquisition-time dark subtraction modes
- reusable stitched dark spectra
- USB connection checks
- graphical spectrum display

The physical shutter is controlled by detector TTL outputs through an SDrive-500 shutter controller.

Background-subtraction behaviour should be validated after any change to detector wiring, shutter configuration or SDrive operation.

## Repository structure

```text
labtools/
├── docs/
├── scripts/
│   └── horiba/
│       ├── check_horiba_configuration.py
│       ├── set_horiba_configuration.py
│       ├── check_horiba_shutter.py
│       └── check_horiba_slit_width.py
├── src/
│   └── labtools/
│       ├── acquisition/
│       │   └── range_spectrum.py
│       ├── devices/
│       │   ├── horiba_spectrometer.py
│       │   └── itc4000.py
│       ├── gui/
│       │   ├── async_runner.py
│       │   └── spectrum_gui_horiba.py
│       ├── io/
│       ├── processing/
│       └── visualisation/
├── tests/
├── vendor/
├── pyproject.toml
├── uv.lock
└── README.md
```

The exact contents may change as additional instruments and workflows are added.

## Requirements

- Windows 10 or Windows 11
- Python version defined in `.python-version`
- [`tps://docs.astral.sh/uv/
- HORIBA EzSpec SDK and ICL
- the appropriate HORIBA firmware and spectrometer configuration
- PyQt6
- NumPy
- Matplotlib
- Loguru
- PyVISA for supported VISA instruments

The HORIBA SDK and instrument configuration are system-specific and may require vendor software outside this repository.

## Installation

Clone the repository:

```powershell
git clone https://github.com/DanielBlight/labtools.git
cd labtools
```

Create or synchronise the environment:

```powershell
uv sync
```

If development dependencies are defined:

```powershell
uv sync --dev
```

Check that the package imports correctly:

```powershell
uv run python -c "import labtools; print('labtools import successful')"
```

## Code-quality checks

Compile the main HORIBA modules:

```powershell
uv run python -m py_compile `
    .\src\labtools\devices\horiba_spectrometer.py `
    .\src\labtools\acquisition\range_spectrum.py `
    .\src\labtools\gui\spectrum_gui_horiba.py
```

Format the code:

```powershell
uv run ruff format .
```

Run lint checks:

```powershell
uv run ruff check .
```

Run the test suite:

```powershell
uv run pytest
```

Some integration tests or diagnostic scripts require connected laboratory hardware and should not be treated as ordinary offline unit tests.

## HORIBA spectrum-acquisition GUI

Launch the GUI from the repository root:

```powershell
uv run python `
    .\src\labtools\gui\spectrum_gui_horiba.py
```

The GUI provides controls for:

- detector preset
- start and end wavelength
- exposure time
- number of repeated frames
- frame-combination method
- stitching overlap
- Slit A width
- dark-subtraction mode
- reusable dark capture and loading
- optional CSV and PNG output
- optional ITC4000 control

The GUI presently opens, configures, uses and closes the HORIBA connection for each operation. This keeps the HORIBA WebSocket on the same asyncio event loop throughout an acquisition.

A future improvement is to use one persistent worker thread and asyncio event loop so multiple spectra can be acquired without reconnecting between operations.

## Detector presets

The wrapper currently maps detector presets to CCD discovery indices:

```python
_PRESET_TO_CCD_INDEX = {
    "symphony": 0,
    "syncerity": 1,
}
```

These mappings depend on the device order returned by the installed HORIBA configuration.

The preset does not force a grating position.

The software reads and reports the current grating turret position because the assignment of physical gratings to `FIRST`, `SECOND` and `THIRD` is defined by the spectrometer firmware configuration.

If device discovery order changes, verify that each preset still selects the intended detector.

## HORIBA acquisition configuration

The CCD is configured for one-dimensional spectral acquisition using:

- `AcquisitionFormat.SPECTRA_IMAGE`
- one acquisition per request
- full-height vertical binning by default
- exposure time specified in seconds at the `labtools` API
- millisecond timer resolution in the HORIBA SDK
- configurable gain and speed tokens

For the current Syncerity configuration:

```text
Gain token 0: High Light
Gain token 1: Best Dynamic Range
Gain token 2: High Sensitivity

Speed token 0:   45 kHz
Speed token 1:   1 MHz
Speed token 2:   1 MHz Ultra
Speed token 127: 500 kHz Wrap
```

These token meanings come from the connected detector configuration and should not be assumed to apply to every HORIBA camera.

## Wavelength-range acquisition

Range acquisition is implemented in:

```text
src/labtools/acquisition/range_spectrum.py
```

The overall sequence is:

```text
connect to the monochromator and CCD
configure the CCD
prepare the calibrated wavelength axis
calculate required monochromator centre wavelengths
move to each centre wavelength
acquire the detector spectrum
stitch the spectra
trim the stitched result to the requested interval
disconnect cleanly
```

The monochromator centre wavelength shown in the log is the centre used for a detector capture. It is not necessarily the minimum, maximum or midpoint of the final trimmed output range.

## Frame-combination modes

The HORIBA wrapper supports:

```text
single
mean
median
sigma_clip
```

### `single`

Returns one detector frame.

### `mean`

Calculates the arithmetic mean of repeated frames.

### `median`

Calculates the pixel-wise median of repeated frames.

### `sigma_clip`

Uses a robust median and median absolute deviation estimate to reject strong pixel-level outliers before averaging.

At least three frames are required for `sigma_clip`.

## Slit control

The GUI exposes only:

```text
Slit A width
```

The requested width is specified in millimetres.

The wrapper:

1. sends the movement request;
2. allows ICL to register the movement;
3. waits for the monochromator;
4. reads the reported Slit A position;
5. logs the requested and reported values.

Use only widths supported by the installed monochromator, firmware and experimental configuration.

## Shutter-control architecture

The iHR320 electromechanical shutter is driven by an SDrive-500 shutter controller.

The present hardware arrangement uses:

```text
Syncerity TTL output ─┐
                      ├─> SDrive-500 trigger inputs
Symphony TTL output ──┘

SDrive-500 shutter output ──> iHR320 electromechanical shutter
```

The SDrive-500 has two active-high TTL inputs.

The shutter is open whenever either trigger input is high.

This has an important consequence:

> An inactive detector can hold the shared shutter open if its TTL output remains high.

During shutter debugging, the unused camera’s TTL connection was found to hold the shutter open. Disconnecting that TTL input allowed the selected camera to control the shutter correctly.

Do not connect or disconnect detector or SDrive cables while the associated equipment is powered. Follow the laboratory hardware shutdown and startup procedure before changing cabling.

### SDrive checks

Before diagnosing the acquisition software, verify:

- the SDrive power indicator is on;
- the shutter override switch is in the `SHUT` position for automatic control;
- the selected detector TTL output is connected to SDrive `IN1` or `IN2`;
- the unused detector is not holding the other trigger input high;
- the SDrive shutter-output cable is connected to the iHR320;
- the physical shutter responds to the SDrive manual override.

The `OPEN` override position holds the shutter open regardless of the TTL inputs.

## Open- and closed-shutter acquisition

Signal frames are requested using:

```python
await spec.acquire_frame(
    open_shutter=True
)
```

Dark frames are requested using:

```python
await spec.acquire_frame(
    open_shutter=False
)
```

Internally, these calls use:

```python
await ccd.acquisition_start(
    open_shutter=open_shutter
)
```

For this hardware setup, the selected CCD controls the shutter by changing the detector TTL output connected to the SDrive.

Direct monochromator shutter commands should not be added around every exposure because the iHR is configured for external shutter control through the SDrive.

## Dark-subtraction modes

The range-acquisition workflow supports four dark modes.

### No subtraction

```python
dark_mode="none"
```

Acquires signal frames without acquiring or subtracting a dark.

### One dark per centre wavelength

```python
dark_mode="per_center"
```

Acquires one closed-shutter dark at each monochromator centre and reuses it for repeated signal frames at that centre.

### One dark per repeated frame

```python
dark_mode="per_frame"
```

Pairs each repeated signal acquisition with a closed-shutter acquisition before combining the corrected frames.

### Pre-taken stitched dark

```python
dark_mode="pre_taken"
```

Uses a previously acquired stitched `DarkSpectrum`.

This is intended for acquisitions such as hyperspectral mapping, where repeatedly moving the shutter and acquiring new dark frames would significantly increase acquisition time.

A reusable dark should only be reused when the relevant acquisition conditions remain suitable, including:

- detector
- wavelength range
- exposure
- gain
- speed
- ROI and binning
- grating
- slit width
- detector temperature
- spectrometer configuration

## Reusable dark spectra

A `DarkSpectrum` contains:

```text
wavelength_nm
intensity
```

Reusable darks can be:

- captured over a requested wavelength range;
- held in memory;
- saved as CSV;
- loaded from CSV;
- subtracted from later acquisitions.

Before using a reusable dark, verify that the SDrive shutter closes correctly and that no second detector is holding the shared shutter open.

## HORIBA diagnostic utilities

The HORIBA utilities are located in:

```text
scripts/horiba/
```

Run diagnostic scripts with the acquisition GUI and other HORIBA software closed, unless a script explicitly states otherwise.

### Check instrument configuration

```powershell
uv run python `
    .\scripts\horiba\check_horiba_configuration.py
```

This read-only tool reports:

- monochromator USB state
- busy state
- current wavelength
- grating turret position
- Slit A width
- exit-mirror position

### Set instrument configuration

```powershell
uv run python `
    .\scripts\horiba\set_horiba_configuration.py
```

Review the target values inside the script before running it.

The script sets and verifies:

- Slit A width
- exit-mirror position
- grating turret position

Changing the mirror or grating can change the active optical path or wavelength calibration.

### Test shutter behaviour

```powershell
uv run python `
    .\scripts\horiba\check_horiba_shutter.py
```

The shutter diagnostic acquires:

```text
Closed 1
Open 1
Closed 2
Open 2
Closed 3
Open 3
```

It displays:

- all six raw spectra;
- the mean open and mean closed spectra;
- the mean open-minus-closed spectrum;
- frame statistics;
- exact-equality checks.

The alternating order helps reveal source or detector drift.

If open and closed frames remain similarly illuminated, check the second SDrive trigger input before changing the subtraction code.

### Test Slit A response

```powershell
uv run python `
    .\scripts\horiba\check_horiba_slit_width.py
```

This diagnostic acquires spectra at several Slit A widths and plots the results together.

The original Slit A position should be restored before the script disconnects.

## USB and ICL behaviour

The HORIBA wrapper verifies that the monochromator reports an open USB connection after `mono.open()`.

Monochromator busy-state polling also checks the USB connection before each query.

If the connection is lost, polling stops rather than repeatedly issuing commands against a closed USB session.

If ICL repeatedly reports that the monochromator USB is not open:

1. close the GUI;
2. stop the Python process;
3. close other HORIBA applications;
4. confirm that no other process owns ICL;
5. check monochromator power and USB connection;
6. restart the hardware and ICL using the laboratory procedure;
7. run the read-only configuration check before acquiring.

Only one application should control ICL and the HORIBA devices at a time.

## ITC4000 laser control

The GUI optionally controls an ITC4000-compatible laser controller through PyVISA.

The implementation uses one persistent VISA session for:

- identification;
- current setpoint;
- current readback;
- laser-diode output;
- TEC output;
- controlled shutdown.

The software current limit is not a replacement for hardware limits, interlocks, operating procedures or optical-safety controls.

## Safety

This software controls laboratory hardware capable of moving optical components, energising shutters and enabling optical sources.

Before use:

- follow local laser and optical-safety procedures;
- verify the optical path before enabling a source;
- use suitable protective equipment;
- do not inspect an active optical port directly;
- do not disconnect powered detector or shutter-controller cables;
- do not exceed detector, shutter, laser or spectrometer operating limits;
- do not rely on software as the only safety mechanism;
- verify hardware readbacks after configuration changes.

Configuration-setting utilities intentionally retain the final verified hardware state.

## Development workflow

Create a branch for new work:

```powershell
git switch -c feature-name
```

Check repository state:

```powershell
git status
```

Run checks:

```powershell
uv run ruff format .
uv run ruff check .
uv run pytest
```

Stage selected files:

```powershell
git add path-to-file
```

Review staged changes:

```powershell
git diff --cached
```

Commit:

```powershell
git commit -m "describe the change"
```

Push a new branch:

```powershell
git push -u origin feature-name
```

## Current limitations and planned work

- Validate all dark-subtraction modes now that shared SDrive TTL behaviour is understood.
- Determine how the unused detector should idle without holding the shutter open.
- Add acquisition metadata to reusable dark spectra.
- Add clearer shutter-status guidance to the GUI.
- Improve the GUI layout and ensure the laser indicator remains visible.
- Replace per-operation HORIBA reconnection with a persistent worker connection.
- Verify detector discovery indices across different ICL configurations.
- Expand automated tests that do not require connected hardware.
- Document the installed iHR320 grating, mirror, slit and shutter configuration.
``