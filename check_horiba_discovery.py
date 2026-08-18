"""Diagnose HORIBA ICL startup and device discovery."""

import asyncio
import traceback

from horiba_sdk.devices.device_manager import DeviceManager


async def main():
    manager = DeviceManager(start_icl=True)

    try:
        print("Starting HORIBA DeviceManager...")
        await manager.start()

        print("\nDeviceManager started successfully.")

        monochromators = getattr(
            manager,
            "monochromators",
            [],
        )

        ccds = getattr(
            manager,
            "charge_coupled_devices",
            [],
        )

        print(f"Monochromators: {len(monochromators)}")
        print(f"CCDs: {len(ccds)}")

        for index, device in enumerate(monochromators):
            print(f"Monochromator {index}: {device}")

        for index, device in enumerate(ccds):
            print(f"CCD {index}: {device}")

    except Exception:
        print("\nHORIBA discovery failed:")
        traceback.print_exc()

    finally:
        try:
            await manager.stop()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
