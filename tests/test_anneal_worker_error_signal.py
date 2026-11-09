"""Offline signal test for AnnealWorker error diagnostics."""

from threading import Event

import pytest

pytest.importorskip("PyQt6")

from labtools.acquisition.laser_anneal import LaserAnnealConfig
from labtools.gui import laser_anneal_gui


def test_anneal_worker_failed_signal_includes_group_children_and_notes(monkeypatch):
    shutter = RuntimeError("shutter close failed")
    shutter.add_note("Cleanup action: close shutter")
    group = ExceptionGroup("Acquisition cleanup failed", [shutter])
    group.add_note("LabJack cleanup also failed: OSError('close failed')")

    def fail_anneal(*_args, **_kwargs):
        raise group

    monkeypatch.setattr(laser_anneal_gui, "run_laser_anneal", fail_anneal)
    worker = laser_anneal_gui.AnnealWorker(LaserAnnealConfig(), Event())
    messages = []
    worker.failed.connect(messages.append)

    worker.run()

    assert messages == [
        "ExceptionGroup: Acquisition cleanup failed (1 sub-exception)\nNote: LabJack cleanup also failed: OSError('close failed')\nFailure 1: RuntimeError: shutter close failed\nFailure 1: Note: Cleanup action: close shutter"
    ]
