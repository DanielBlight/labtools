"""Synthetic map devices. This module never imports hardware wrappers.

The synthetic scene is a development model, not a physical calibration.
"""
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field

import numpy as np

MODEL_VERSION = 'gaussian-scene-v1'


@dataclass
class SimulatedMapState:
    """One shared state for mirror, gate and counter in a single map session."""

    x_v: float = 0.0
    y_v: float = 0.0
    gate_open: bool = False
    measurements: int = 0
    moves: list = field(default_factory=list)
    closed: bool = False


class SimulatedMirror:
    def __init__(self, state, config):
        self.state = state
        self.config = config

    def move(self, x_voltage, y_voltage):
        values = (float(x_voltage), float(y_voltage))
        if self.state.closed:
            raise RuntimeError('Simulated session is closed')
        if not all(math.isfinite(v) and self.config.safe_voltage_min_v <= v <= self.config.safe_voltage_max_v for v in values):
            raise ValueError('Simulated mirror voltage outside configured limits')
        self.state.x_v, self.state.y_v = values
        self.state.moves.append(values)

    def home(self):
        self.move(0.0, 0.0)


class SimulatedGate:
    def __init__(self, state):
        self.state = state

    def open(self):
        if self.state.closed:
            raise RuntimeError('Simulated session is closed')
        self.state.gate_open = True

    def close(self):
        self.state.gate_open = False


class SimulatedTimeController:
    def __init__(self, state, config):
        self.state = state
        self.config = config
        self.channel_settings = {}

    def configure_channel(self, channel, *, threshold_v, edge, enabled=True):
        if channel not in (1, 2, 3, 4) or edge not in ('rising', 'falling'):
            raise ValueError('Invalid simulated channel configuration')
        if not math.isfinite(threshold_v):
            raise ValueError('Threshold must be finite')
        self.channel_settings[channel] = (threshold_v, edge, enabled)

    def get_simultaneous_counts(self, channels, integration_time_s):
        integration_time_s = float(integration_time_s)
        if self.state.closed:
            raise RuntimeError('Simulated session is closed')
        if not math.isfinite(integration_time_s) or integration_time_s <= 0:
            raise ValueError('Integration time must be finite and positive')
        if any(ch not in self.channel_settings or not self.channel_settings[ch][2] for ch in channels):
            raise ValueError('Configure and enable selected channels first')
        limit = self.config.simulation_fail_after_points
        if limit is not None and self.state.measurements >= limit:
            raise TimeoutError('Injected SIMULATION counter timeout')
        if self.config.simulation_realtime:
            time.sleep(integration_time_s)
        c = self.config
        sx = max(abs(c.x_stop_v - c.x_start_v), 1e-6)
        sy = max(abs(c.y_stop_v - c.y_start_v), 1e-6)
        u = (self.state.x_v - (c.x_start_v + c.x_stop_v) / 2) / sx
        v = (self.state.y_v - (c.y_start_v + c.y_stop_v) / 2) / sy
        scene = 2000.0 + 80000.0 * math.exp(-0.5 * ((u / .17) ** 2 + (v / .20) ** 2))
        scene += 18000.0 * math.exp(-0.5 * (((u - .27) / .09) ** 2 + ((v + .22) / .12) ** 2))
        result = {}
        for channel in channels:
            # Per-position/channel RNG makes resumed maps match uninterrupted maps.
            key = f'{MODEL_VERSION}|{c.simulation_seed}|{self.state.x_v.hex()}|{self.state.y_v.hex()}|{channel}|{integration_time_s.hex()}'
            seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:16], 'little')
            rng = np.random.default_rng(seed)
            rate = scene * (1.0 + .25 * (channel - 1)) if self.state.gate_open else 0.0
            result[channel] = int(rng.poisson(rate * integration_time_s))
        self.state.measurements += 1
        return result


