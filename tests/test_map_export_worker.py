"""Worker export must not load pyplot/Qt even with a Qt backend selected."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_worker_export_never_imports_pyplot_or_qt(tmp_path):
    code = r'''
import builtins, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name=="matplotlib.pyplot" or name.startswith(("PyQt", "PySide")):
        raise AssertionError("GUI import during worker export: "+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from labtools.acquisition.intensity_map import acquire_intensity_map
from labtools.config.intensity_map import IntensityMapConfig
from labtools.visualisation.intensity_map import plot_intensity_map
from matplotlib.backends.backend_agg import FigureCanvasAgg
root=Path(sys.argv[1])
def run():
    figure,axes=plot_intensity_map([-1,1],[-1,1],[[1,2],[3,4]],show=False,output_path=root/"direct.png")
    assert isinstance(figure.canvas,FigureCanvasAgg)
    assert figure.canvas.manager is None
    figure.clear()
    config=IntensityMapConfig(-1,1,2,-1,1,2,backend="simulation",settle_time_s=0,integration_time_s=.001,output_root=root)
    result=acquire_intensity_map(config)
    assert result.complete
    assert (result.output_directory/"summed_intensity_map.png").is_file()
with ThreadPoolExecutor(max_workers=1) as executor:
    executor.submit(run).result()
assert not any(name.startswith(("PyQt", "PySide")) for name in sys.modules)
print("WORKER EXPORT PASSED WITHOUT GUI IMPORTS")
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), MPLBACKEND="QtAgg")
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=45, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WORKER EXPORT PASSED WITHOUT GUI IMPORTS" in result.stdout
