# Archived HORIBA alignment GUI v2

## Archive references

- Branch: `archive/horiba-alignment-v2`
- Tag: `archive-horiba-alignment-v2`
- Commit: `9024b3adbd132bfb3db7ea8b83a803ffbd98f915`

## Status

This commit contains the working standalone HORIBA continuous-alignment GUI that existed on the previous `main` branch.

The implementation is archived for later integration and is not part of the current `0.2.0-rc.1` release candidate.

## Useful behaviour retained in the archive

- continuous back-to-back spectrum acquisition
- per-frame dark subtraction
- standalone alignment GUI styling
- operator controls designed for rapid alignment
- a 0.02-second alignment exposure override

## Why it is not integrated now

The archived implementation owns a parallel HORIBA acquisition lifecycle rather than using the release candidate's shared `SpectrumWorker` and `SpectrumService` boundary.

Directly merging the old implementation would risk:

- duplicate device ownership
- conflicting cleanup and fault handling
- overlapping acquisition workers
- bypassing shared busy-state refusal
- importing the unvalidated 20 ms exposure override

The 0.02-second exposure must not be adopted until connected HORIBA testing confirms that the detector, shutter, readout mode and signal quality support it.

## Future integration target

Port the useful visual design and continuous-alignment operator workflow onto the shared worker/service architecture.

Future work should preserve:

- operation-scoped ownership
- shared busy-state refusal
- conservative detector exposure limits
- simulation without native HORIBA imports
- cleanup-sensitive fault reporting
- private-worker closure and injected-worker lifetime rules

## Retrieval

Inspect the archived GUI with:

```powershell
git show archive/horiba-alignment-v2:src/labtools/gui/alignment_gui_horiba.py
```

Compare it with the integration branch using:

```powershell
git diff integration/0.2.0-rc1..archive/horiba-alignment-v2 -- `
  docs/horiba-alignment.md `
  src/labtools/acquisition/alignment_spectrum.py `
  src/labtools/devices/horiba_spectrometer.py `
  src/labtools/gui/alignment_gui_horiba.py `
  tests/test_alignment_gui.py `
  tests/test_alignment_spectrum.py
```
