"""Deterministic, explicitly synthetic hyperspectral mirror backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

SIMULATION_MODEL_ID = "gaussian-spatial-modulation-v1"


class SimulatedHyperspectralMirror:
    """Records positions; the service applies the documented scene modulation."""

    backend_identity = f"simulation:{SIMULATION_MODEL_ID}"

    def __init__(self) -> None:
        self.x_v = 0.0
        self.y_v = 0.0
        self.closed = False

    async def move_to(self, x_v: float, y_v: float) -> None:
        if self.closed:
            raise RuntimeError("Simulated mirror is closed")
        self.x_v, self.y_v = float(x_v), float(y_v)

    async def home(self) -> None:
        self.x_v = self.y_v = 0.0

    async def close(self) -> None:
        self.closed = True


@asynccontextmanager
async def open_simulated_hyperspectral_mirror():
    mirror = SimulatedHyperspectralMirror()
    try:
        yield mirror
    finally:
        await mirror.close()
