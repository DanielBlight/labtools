"""Read the current HORIBA monochromator configuration.

This diagnostic is read-only. It reports:

- monochromator USB open state;
- monochromator busy state;
- current wavelength;
- current grating turret position;
- Slit A width;
- exit-mirror position.

Run from the labtools project root with:

    uv run python check_horiba_configuration.py
"""

from __future__ import annotations

import asyncio

from horiba_sdk.devices.single_devices.monochromator import Monochromator

from labtools.devices.horiba_spectrometer import HoribaSpectrometer


PRESET = "syncerity"


async def main() -> None:
    """Connect, print the current configuration, and disconnect."""
    spec = HoribaSpectrometer(preset=PRESET)

    try:
        print("Connecting to HORIBA devices...")
        await spec.connect()

        mono_is_open = await spec.mono.is_open()
        mono_is_busy = await spec.mono.is_busy()
        wavelength_nm = float(await spec.mono.get_current_wavelength())
        grating = await spec.mono.get_turret_grating()
        slit_a_width_mm = float(
            await spec.mono.get_slit_position_in_mm(Monochromator.Slit.A)
        )
        exit_mirror = await spec.mono.get_mirror_position(
            Monochromator.Mirror.EXIT
        )

        print()
        print("HORIBA monochromator configuration")
        print("---------------------------------")
        print(f"Preset:               {PRESET}")
        print(f"USB connection open:  {mono_is_open}")
        print(f"Monochromator busy:   {mono_is_busy}")
        print(f"Current wavelength:   {wavelength_nm:.3f} nm")
        print(f"Grating position:     {grating.name}")
        print(f"Slit A width:         {slit_a_width_mm:.6f} mm")
        print(f"Exit mirror position: {exit_mirror.name}")

    finally:
        try:
            await spec.disconnect()
        except Exception as exc:  # noqa: BLE001
            print(f"Disconnect warning: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
