"""Headless synthetic example. No hardware, no output files unless --output is supplied."""
import argparse
import asyncio
from pathlib import Path

from labtools.config.spectrum import SpectrumSettings
from labtools.io.spectrum_records import save_dark_record, save_spectrum_result
from labtools.runtime.spectrum_backend import create_spectrum_service


async def acquire(output=None):
    settings = SpectrumSettings("toy-scene-v1", "syncerity", .1, 2, 0, .5,
                                500., 600., backend="simulation")
    service = create_spectrum_service(backend="simulation")
    dark = await service.capture_dark(settings)
    result = await service.acquire(settings, dark_mode="pre_taken", dark=dark)
    print(f"SYNTHETIC DATA ONLY: {result.intensity.size} points; dark {dark.record_id}")
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        save_dark_record(output / "synthetic-dark.npz", dark)
        save_spectrum_result(output / "synthetic-spectrum.npz", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    asyncio.run(acquire(parser.parse_args().output))
