"""Isolate acquisition PNG rendering from live GUI font/mathtext state.

The parent transfers only numeric arrays and a title. The child imports no Qt,
pyplot or hardware and renders with Agg. Export failures remain visible to callers.
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread

import numpy as np


def export_intensity_map_png(x_values_v, y_values_v, intensity_cps, *, title, output_path):
    """Render the usual acquisition PNG in a separate interpreter, atomically.

    This is synchronous to the acquisition worker, not to the GUI thread. Numeric
    run outputs are already saved before this call. No acquisition is repeated.
    """
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".map-render-", dir=target.parent) as folder:
        folder = Path(folder)
        payload = folder / "map.npz"
        rendered = folder / "map.png"
        np.savez(payload, x_values_v=np.asarray(x_values_v, dtype=float),
                 y_values_v=np.asarray(y_values_v, dtype=float),
                 intensity_cps=np.asarray(intensity_cps, dtype=float), title=np.asarray(str(title)))
        _renderer.request(payload, rendered)
        if not rendered.is_file() or rendered.stat().st_size == 0:
            raise RuntimeError("Map PNG renderer produced no image; numeric outputs remain saved")
        os.replace(rendered, target)


class _Renderer:
    """One lazy child, serialized requests, no shared GUI rendering state."""

    def __init__(self):
        self.lock = Lock()
        self.process = None

    def _close(self):
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()

    def close(self):
        with self.lock:
            self._close()

    def request(self, payload, rendered):
        with self.lock:
            try:
                if self.process is None or self.process.poll() is not None:
                    self._close()
                    env = os.environ.copy()
                    env["MPLBACKEND"] = "Agg"
                    package_root = str(Path(__file__).resolve().parents[2])
                    env["PYTHONPATH"] = package_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
                    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
                    self.process = subprocess.Popen(
                        [sys.executable, "-m", "labtools.visualisation.map_export", "--serve"],
                        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        text=True, encoding="utf-8", errors="replace", bufsize=1, **options,
                    )
                process = self.process
                process.stdin.write(json.dumps([str(payload), str(rendered)]) + "\n")
                process.stdin.flush()
                response = Queue(maxsize=1)
                def read():
                    try:
                        response.put(process.stdout.readline())
                    except (OSError, ValueError):
                        response.put("")
                reader = Thread(target=read, name="map-render-response", daemon=True)
                reader.start()
                try:
                    line = response.get(timeout=120)
                except Empty as error:
                    raise RuntimeError("Map PNG renderer timed out; numeric outputs remain saved") from error
                if not line:
                    raise RuntimeError(f"Map PNG renderer exited unexpectedly ({process.poll()}); numeric outputs remain saved")
                reply = json.loads(line)
                if not reply.get("ok"):
                    raise RuntimeError("Map PNG renderer failed; numeric outputs remain saved. " + reply.get("error", ""))
            except BaseException:
                self._close()
                raise


_renderer = _Renderer()
atexit.register(_renderer.close)


def _render(payload, target):
    import matplotlib

    matplotlib.use("Agg", force=True)
    from labtools.visualisation.intensity_map import plot_intensity_map

    with np.load(payload, allow_pickle=False) as data:
        figure, _ = plot_intensity_map(data["x_values_v"], data["y_values_v"], data["intensity_cps"],
            title=str(data["title"].item()), output_path=target, show=False)
        figure.clear()
    if any(name.startswith(("PyQt", "PySide")) or name == "matplotlib.pyplot" for name in sys.modules):
        raise RuntimeError("Unexpected GUI import in isolated map renderer")


def _serve():
    # Sequential rendering in a separate interpreter amortizes font-cache startup
    # across sequence maps without concurrent use of Matplotlib in this process.
    for line in sys.stdin:
        try:
            payload, target = json.loads(line)
            _render(Path(payload), Path(target))
            reply = {"ok": True}
        except Exception:  # noqa: BLE001 - terminal child protocol boundary
            reply = {"ok": False, "error": traceback.format_exc()[-4000:]}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    if sys.argv[1:] != ["--serve"]:
        raise SystemExit("Expected --serve")
    _serve()
