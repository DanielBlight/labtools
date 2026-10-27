import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import asyncio
import time
from threading import get_ident
import pytest
pytest.importorskip("PyQt6.QtWidgets",exc_type=ImportError)
from PyQt6.QtWidgets import QApplication,QMessageBox
from labtools.gui.alignment_gui_horiba import HoribaAlignmentWindow


def options(preset):
    return dict(gains=(("gain",2),),speeds=(("speed",0),),default_gain=2,default_speed=0,
                minimum_exposure_s=.065 if preset=="syncerity" else .1)


def spin(app,predicate):
    deadline=time.monotonic()+5
    while not predicate():
        app.processEvents()
        assert time.monotonic()<deadline,"Qt lifecycle timeout"
        time.sleep(.002)
    app.processEvents()


@pytest.mark.parametrize("mode",["stop","close","failure"])
def test_window_lifecycle(mode,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox,"exec",lambda self:0)
    calls=[]
    class Spec:
        def record(self,name): calls.append((name,get_ident()))
        async def connect(self): self.record("connect")
        async def configure(self,**kw): self.record("configure")
        async def set_wavelength(self,value): self.record("move"); return value
        async def get_spectrum(self,**kw):
            self.record("capture"); await asyncio.sleep(.02)
            if mode=="failure": raise OSError("fake failure")
            return [690,691],[1,2]
        async def disconnect(self): self.record("disconnect")
    w=HoribaAlignmentWindow(factory=lambda **kw:Spec(),options_provider=options)
    assert not calls
    w.preset_combo.setCurrentText("symphony")
    assert w.exposure_box.minimum()==.02
    w.exposure_box.setValue(.02); w.show()
    try:
        for repeat in range(2):
            w.show()
            spin(app, lambda: w.isVisible())
            w.start_alignment(); thread=w._thread
            assert not w.start_button.isEnabled() and not w.setup_group.isEnabled()
            w.start_alignment(); assert w._thread is thread
            if mode=="failure":
                spin(app,lambda:w._thread is None)
                assert "fake failure" in w._error
            else:
                spin(app,lambda:w._latest is not None)
                if mode=="close": assert not w.close()
                else: w.stop_alignment()
                spin(app,lambda:w._thread is None)
            assert w.start_button.isEnabled() and not w.stop_button.isEnabled()
            assert calls[-1][0]=="disconnect"
        assert sum(c[0]=="connect" for c in calls)==2
        assert sum(c[0]=="move" for c in calls)==2
        assert all(c[1]!=get_ident() for c in calls)
    finally:
        w.stop_alignment()
        if w._thread is not None:
            assert w._thread.wait(5000)
            app.processEvents()
        w.close()
