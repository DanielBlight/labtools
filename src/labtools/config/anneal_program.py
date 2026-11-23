"""Native-free point-dose programs; no instrument-profile schema changes."""

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class AnnealProgram:
    base: object
    mode: str = "Uniform array"
    last_dwell_s: float = 0.001
    spacing: str = "Linear"

    def points(self):
        self.base.validate()
        if self.mode not in {"Uniform array", "Single point", "Dwell ramp array"}:
            raise ValueError("Unknown annealing mode")
        if self.spacing not in {"Linear", "Logarithmic"}:
            raise ValueError("Unknown dwell spacing")
        first = self.base.point_dwell_s
        last = self.last_dwell_s if self.mode == "Dwell ramp array" else first
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (first, last)):
            raise ValueError("Dwell endpoints must be finite and nonnegative")
        if self.mode == "Dwell ramp array" and self.spacing == "Logarithmic" and min(first, last) <= 0:
            raise ValueError("Logarithmic dwell endpoints must be strictly positive")
        nx, ny = (1, 1) if self.mode == "Single point" else (self.base.x_points, self.base.y_points)
        count = nx * ny
        if count * self.base.passes > 100000:
            raise ValueError("Program exceeds 100000 point exposures")
        if count == 1 and self.mode == "Dwell ramp array" and first != last:
            raise ValueError("A one-point ramp requires equal first and last dwell")
        result = []
        for yi in range(ny):
            indices = range(nx - 1, -1, -1) if self.base.serpentine and yi % 2 else range(nx)
            for xi in indices:
                i = len(result)
                fraction = i / (count - 1) if count > 1 else 0
                dwell = math.exp(math.log(first) + fraction * (math.log(last) - math.log(first))) if self.mode == "Dwell ramp array" and self.spacing == "Logarithmic" else first + fraction * (last - first)
                if i == 0:
                    dwell = first
                if i == count - 1:
                    dwell = last
                x = self.base.x_start_v + (self.base.x_stop_v - self.base.x_start_v) * xi / (nx - 1) if nx > 1 else self.base.x_start_v
                y = self.base.y_start_v + (self.base.y_stop_v - self.base.y_start_v) * yi / (ny - 1) if ny > 1 else self.base.y_start_v
                point = replace(self.base, x_start_v=x, x_stop_v=x, y_start_v=y, y_stop_v=y,
                                x_points=1, y_points=1, passes=1, point_dwell_s=dwell)
                point.validate()
                result.append(point)
        estimate = self.base.passes * sum(p.point_dwell_s + p.mirror_settle_s for p in result)
        if estimate > self.base.maximum_open_time_s:
            raise ValueError("Total programmed dwell/settle exceeds the existing maximum open-time budget")
        return tuple(result) * self.base.passes
