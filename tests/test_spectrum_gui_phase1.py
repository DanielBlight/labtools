"""Offscreen Phase 1 spectrum-window tests; injected services, never hardware."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
SCRIPT = r"""
import asyncio, json, sys, time
from dataclasses import replace
from pathlib import Path
import numpy as np
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from labtools.acquisition.spectrum_service import DarkRecord, SpectrumResult
from labtools.config.spectrum import SpectrumSettings
from labtools.gui.spectrum_gui_horiba import HoribaRangeWindow
from labtools.io.spectrum_records import save_dark_record
app = QApplication([])
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, sys.argv[2])
messages=[]
QMessageBox.warning=lambda parent,title,text,*a,**k: messages.append((title,text)) or QMessageBox.StandardButton.Ok
QMessageBox.critical=lambda parent,title,text,*a,**k: messages.append((title,text)) or QMessageBox.StandardButton.Ok
QMessageBox.exec=lambda *a,**k: QMessageBox.StandardButton.Ok
OPTIONS={
 "syncerity":{"gains":(("g",2),),"speeds":(("s",0),),"default_gain":2,"default_speed":0,"minimum_exposure_s":.065},
 "symphony":{"gains":(("g",2),),"speeds":(("s",0),),"default_gain":2,"default_speed":0,"minimum_exposure_s":.100},
}
def spin(predicate, timeout=5):
 end=time.monotonic()+timeout
 while not predicate():
  app.processEvents(); assert time.monotonic()<end; time.sleep(.002)
 app.processEvents()
def result(settings, mode="none"):
 x=np.array([500.,600.]); raw=np.array([10.,20.])
 return SpectrumResult(settings,x,raw,raw if mode in {"none","pre_taken"} else None,
                       mode,"dark-id" if mode=="pre_taken" else None)
class Service:
 def __init__(self, behavior="success"): self.behavior=behavior; self.calls=[]
 async def test_connection(self, settings, *, cancel_requested=None): self.calls.append(("test",settings))
 async def capture_dark(self, settings, *, cancel_requested=None):
  self.calls.append(("dark",settings)); return DarkRecord(settings,[500,600],[1,2],"dark-id","2026-10-28T00:00:00+00:00")
 async def acquire(self, settings, *, dark_mode="none", dark=None, cancel_requested=None):
  self.calls.append(("acquire",settings,dark_mode,dark))
  if self.behavior=="error": raise OSError("injected")
  if self.behavior=="cancel":
   while not cancel_requested(): await asyncio.sleep(.005)
   raise asyncio.CancelledError()
  await asyncio.sleep(.05)
  return result(settings,dark_mode)
mode=sys.argv[1]; service=Service("cancel" if mode=="cancel" else "error" if mode=="error" else "success")
w=HoribaRangeWindow(service=service,configuration_id="test-config",backend="simulation",preset_options=OPTIONS)
w.show()
try:
 w.mode_combo.setCurrentText("median"); assert w.frames_box.minimum()==3
 settings=w._snapshot_settings()
 assert settings.configuration_id=="test-config" and settings.backend=="simulation"
 dark=DarkRecord(settings,[500,600],[1,2],"dark-id","2026-10-28T00:00:00+00:00")
 w.pre_taken_dark=dark; w._update_background_controls(); assert "valid" in w.background_status.text().lower()
 w.exposure_box.setValue(.2); w._update_background_controls(); assert "stale" in w.background_status.text().lower()
 w.use_background.setChecked(False); assert w.pre_taken_dark is dark; assert "retained" in w.background_status.text().lower()
 if mode=="legacy":
  legacy=Path(sys.argv[2])/"legacy.csv"; legacy.write_text("wavelength_nm,intensity\n500,1\n600,2\n")
  QFileDialog.getOpenFileName=lambda *a,**k:(str(legacy),"")
  w.load_pre_taken_dark(); assert w.pre_taken_dark is dark
  assert "recapture" in messages[-1][1].lower()
 elif mode=="npz":
  path=Path(sys.argv[2])/"dark.npz"; save_dark_record(path,dark)
  QFileDialog.getOpenFileName=lambda *a,**k:(str(path),"")
  w.load_pre_taken_dark(); assert w.pre_taken_dark.record_id=="dark-id"
 elif mode=="save":
  w._save_options=(True,False,Path(sys.argv[2])); out=result(settings,"none")
  w._maybe_save_result(out)
  archive=next(Path(sys.argv[2]).glob("horiba_*.npz"))
  with np.load(archive,allow_pickle=False) as data:
   meta=json.loads(data["metadata"].item()); assert meta["settings"]["configuration_id"]=="test-config"
   assert meta["dark_mode"]=="none" and meta["raw_available"] is True
  assert next(Path(sys.argv[2]).glob("horiba_*.csv")).exists()
 else:
  w.mode_combo.setCurrentText("single"); w.exposure_box.setValue(.1); w.acquire_spectrum()
  spin(lambda:w._spectrometer_busy)
  assert not w.close()
  if mode=="cancel": w.request_stop()
  spin(lambda:not w._spectrometer_busy and not w._async_tasks)
  assert w.acquire_button.isEnabled()
  if mode in {"cancel","error"}: service.behavior="success"
  w.acquire_spectrum(); spin(lambda:not w._spectrometer_busy and not w._async_tasks)
  assert len([c for c in service.calls if c[0]=="acquire"])==2
finally:
 if w._spectrometer_busy: w.request_stop()
 spin(lambda:not w._spectrometer_busy and not w._async_tasks)
 w.close(); app.processEvents()
"""


@pytest.mark.parametrize(
    "mode", ["success", "cancel", "error", "legacy", "npz", "save"]
)
def test_spectrum_window_phase1(mode, tmp_path):
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        MPLBACKEND="Agg",
        XDG_CONFIG_HOME=str(tmp_path),
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
    )
    completed = subprocess.run(
        [sys.executable, "-c", SCRIPT, mode, str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
