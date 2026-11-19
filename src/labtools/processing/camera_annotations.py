"""Image-coordinate camera overlays. No Qt, camera imports or image mutation."""

from dataclasses import dataclass
from math import hypot, isfinite


@dataclass(frozen=True)
class Circle:
    x: float
    y: float
    radius: float
    label: str


class CameraAnnotations:
    """Bounded, in-memory annotations in full-resolution raw image pixels.

    Geometry/source changes clear annotations rather than implying registration
    between different cameras. Undo removes the most recently completed circle.
    """

    def __init__(self):
        self.geometry = None
        self.circles = []
        self.crosshair = False
        self.rings = False
        self.ring_spacing = 50.
        self.ring_count = 3
        self._history = []

    def set_geometry(self, width, height):
        if type(width) is not int or type(height) is not int or not 1 <= width <= 100000 or not 1 <= height <= 100000:
            raise ValueError("Invalid image dimensions")
        geometry = (width, height)
        changed = self.geometry is not None and geometry != self.geometry
        if geometry != self.geometry:
            self.reset()
            self.geometry = geometry
        return changed

    def reset(self):
        self.circles.clear()
        self._history.clear()

    def configure(self, *, crosshair, rings, spacing, count):
        if type(spacing) not in (int, float) or not isfinite(spacing) or not 1 <= spacing <= 100000:
            raise ValueError("Ring spacing must be 1..100000 raw pixels")
        if type(count) is not int or not 1 <= count <= 20:
            raise ValueError("Ring count must be 1..20")
        self.crosshair, self.rings = bool(crosshair), bool(rings)
        self.ring_spacing, self.ring_count = float(spacing), count

    def add(self, centre, edge, label=""):
        if self.geometry is None:
            raise ValueError("Wait for an image before annotating")
        if len(self.circles) >= 200:
            raise ValueError("Maximum 200 circles; undo or clear some annotations")
        points = (*centre, *edge)
        if any(type(value) not in (int, float) or not isfinite(value) for value in points):
            raise ValueError("Circle coordinates must be finite")
        width, height = self.geometry
        if any(not (0 <= x <= width and 0 <= y <= height) for x, y in (centre, edge)):
            raise ValueError("Draw inside the image, not the letterbox margins")
        radius = hypot(edge[0] - centre[0], edge[1] - centre[1])
        if radius < 1:
            raise ValueError("Circle radius must be at least one raw pixel")
        if not isinstance(label, str):
            raise TypeError("Circle label must be text")
        label = " ".join(label.split())[:80] or f"Circle {len(self.circles) + 1}"
        self._remember()
        circle = Circle(float(centre[0]), float(centre[1]), radius, label)
        self.circles.append(circle)
        return circle

    def _remember(self):
        self._history.append(tuple(self.circles))
        self._history = self._history[-200:]

    @property
    def can_undo(self):
        return bool(self._history)

    def undo(self):
        if not self._history:
            return False
        self.circles[:] = self._history.pop()
        return True

    def clear(self):
        if self.circles:
            self._remember()
            self.circles.clear()


def image_point(x, y, rect, geometry):
    """Map letterboxed display coordinates to raw image coordinates, or None."""
    left, top, width, height = rect
    if width <= 0 or height <= 0 or geometry is None:
        return None
    if not left <= x <= left + width or not top <= y <= top + height:
        return None
    return ((x - left) * geometry[0] / width, (y - top) * geometry[1] / height)
