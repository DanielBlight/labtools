"""Set and verify key HORIBA monochromator configuration values.

This utility controls only the hardware elements confirmed for this setup:

- Slit A width;
- exit-mirror position;
- grating turret position.

Edit the TARGET values below before running. The selected settings are retained
when the script exits.

Changing the exit mirror or grating can redirect light or alter the calibrated
spectral range. Use an appropriate safe optical condition while testing.

Run from the labtools project root with:

    uv run python set_horiba_configuration.py
"""

from __future__ import annotations

import asyncio
from typing import TypeVar

from horiba_sdk.devices.single_devices.monochromator import Monochromator

from labtools.devices.horiba_spectrometer import HoribaSpectrometer


PRESET = "syncerity"

# Edit these three values before running the script.
TARGET_SLIT_A_WIDTH_MM = 0.500
TARGET_EXIT_MIRROR = Monochromator.MirrorPosition.AXIAL
TARGET_GRATING = Monochromator.Grating.FIRST

COMMAND_REGISTRATION_DELAY_S = 0.5
POLL_INTERVAL_S = 0.2
MOVEMENT_TIMEOUT_S = 60.0
STABLE_READBACKS_REQUIRED = 3

T = TypeVar("T")


async def wait_until_idle(
    spec: HoribaSpectrometer,
    *,
    timeout_s: float = MOVEMENT_TIMEOUT_S,
) -> None:
    """Wait for the monochromator while preserving USB connection checks."""
    await spec._wait_for_mono(  # noqa: SLF001
        timeout_s=timeout_s,
        poll_interval_s=POLL_INTERVAL_S,
    )


async def verify_stable_readback(
    readback,
    expected: T,
    *,
    label: str,
    timeout_s: float = MOVEMENT_TIMEOUT_S,
) -> T:
    """Require several consecutive matching readbacks."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    stable_count = 0
    last_value = None

    while loop.time() < deadline:
        last_value = await readback()
        print(f"  {label} readback: {last_value}")

        if last_value == expected:
            stable_count += 1
        else:
            stable_count = 0

        if stable_count >= STABLE_READBACKS_REQUIRED:
            return last_value

        await asyncio.sleep(POLL_INTERVAL_S)

    raise RuntimeError(
        f"{label} did not reach a stable target. "
        f"Expected {expected!r}; final readback was {last_value!r}."
    )


async def set_slit_a(spec: HoribaSpectrometer) -> float:
    """Set and verify Slit A width in millimetres."""
    if TARGET_SLIT_A_WIDTH_MM <= 0:
        raise ValueError("TARGET_SLIT_A_WIDTH_MM must be greater than zero.")

    print()
    print(f"Setting Slit A to {TARGET_SLIT_A_WIDTH_MM:.6f} mm...")

    await spec.mono.set_slit_position(
        Monochromator.Slit.A,
        TARGET_SLIT_A_WIDTH_MM,
    )
    await asyncio.sleep(COMMAND_REGISTRATION_DELAY_S)
    await wait_until_idle(spec)

    async def readback() -> float:
        return float(
            await spec.mono.get_slit_position_in_mm(Monochromator.Slit.A)
        )

    tolerance_mm = 0.005
    loop = asyncio.get_running_loop()
    deadline = loop.time() + MOVEMENT_TIMEOUT_S
    stable_count = 0
    last_value = await readback()

    while loop.time() < deadline:
        last_value = await readback()
        difference_mm = abs(last_value - TARGET_SLIT_A_WIDTH_MM)
        print(
            f"  Slit A readback: {last_value:.6f} mm; "
            f"difference: {difference_mm:.6f} mm"
        )

        if difference_mm <= tolerance_mm:
            stable_count += 1
        else:
            stable_count = 0

        if stable_count >= STABLE_READBACKS_REQUIRED:
            return last_value

        await asyncio.sleep(POLL_INTERVAL_S)

    raise RuntimeError(
        "Slit A did not reach a stable target. "
        f"Requested {TARGET_SLIT_A_WIDTH_MM:.6f} mm; "
        f"final readback was {last_value:.6f} mm."
    )


async def set_exit_mirror(spec: HoribaSpectrometer) -> Monochromator.MirrorPosition:
    """Set and verify the exit-mirror position."""
    print()
    print(f"Setting exit mirror to {TARGET_EXIT_MIRROR.name}...")

    await spec.mono.set_mirror_position(
        Monochromator.Mirror.EXIT,
        TARGET_EXIT_MIRROR,
    )
    await asyncio.sleep(COMMAND_REGISTRATION_DELAY_S)
    await wait_until_idle(spec)

    async def readback() -> Monochromator.MirrorPosition:
        return await spec.mono.get_mirror_position(Monochromator.Mirror.EXIT)

    return await verify_stable_readback(
        readback,
        TARGET_EXIT_MIRROR,
        label="Exit mirror",
    )


async def set_grating(spec: HoribaSpectrometer) -> Monochromator.Grating:
    """Set and verify the grating turret position."""
    print()
    print(f"Setting grating turret to {TARGET_GRATING.name}...")

    await spec.mono.set_turret_grating(TARGET_GRATING)
    await asyncio.sleep(COMMAND_REGISTRATION_DELAY_S)
    await wait_until_idle(spec, timeout_s=180.0)

    async def readback() -> Monochromator.Grating:
        return await spec.mono.get_turret_grating()

    return await verify_stable_readback(
        readback,
        TARGET_GRATING,
        label="Grating",
        timeout_s=180.0,
    )


async def main() -> None:
    """Connect, set all requested values, verify them, and disconnect."""
    spec = HoribaSpectrometer(preset=PRESET)

    try:
        print("Connecting to HORIBA devices...")
        await spec.connect()

        initial_slit = float(
            await spec.mono.get_slit_position_in_mm(Monochromator.Slit.A)
        )
        initial_mirror = await spec.mono.get_mirror_position(
            Monochromator.Mirror.EXIT
        )
        initial_grating = await spec.mono.get_turret_grating()

        print()
        print("Initial configuration")
        print("---------------------")
        print(f"Slit A width:         {initial_slit:.6f} mm")
        print(f"Exit mirror position: {initial_mirror.name}")
        print(f"Grating position:     {initial_grating.name}")

        final_slit = await set_slit_a(spec)
        final_mirror = await set_exit_mirror(spec)
        final_grating = await set_grating(spec)

        print()
        print("Verified final configuration")
        print("----------------------------")
        print(f"Slit A width:         {final_slit:.6f} mm")
        print(f"Exit mirror position: {final_mirror.name}")
        print(f"Grating position:     {final_grating.name}")
        print()
        print("The verified settings have been retained.")

    finally:
        try:
            await spec.disconnect()
        except Exception as exc:  # noqa: BLE001
            print(f"Disconnect warning: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
