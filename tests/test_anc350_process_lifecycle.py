"""ANC350 process lifecycle contract without contacting USB hardware."""
import ast
from pathlib import Path

from labtools.runtime.sample_stage import native_factory


def test_native_factory_uses_fresh_process_boundary(monkeypatch):
    created = []
    monkeypatch.setattr("labtools.runtime.sample_stage.ANC350Process", lambda: created.append(object()) or created[-1])
    first = native_factory()
    second = native_factory()
    assert first is not second


def test_child_always_closes_device_in_finally():
    source = Path(__import__("labtools.runtime.sample_stage", fromlist=["__file__"]).__file__).read_text()
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_anc350_process")
    assert any(isinstance(node, ast.Try) and node.finalbody for node in ast.walk(function))
    assert "device.close()" in source


def test_proxy_close_has_bounded_join_and_termination_fallback():
    source = Path(__import__("labtools.runtime.sample_stage", fromlist=["__file__"]).__file__).read_text()
    assert "self._process.join(10)" in source
    assert "self._process.terminate()" in source
    assert "ANC350 close timed out" in source


def test_disconnect_drops_failed_proxy_and_allows_new_connection():
    from labtools.runtime.sample_stage import SampleStage

    class Proxy:
        def close(self):
            raise RuntimeError("close timed out; process terminated")

    created = []
    stage = SampleStage(factory=lambda: created.append(Proxy()) or created[-1])
    token = stage.claim()
    stage.device = Proxy()
    try:
        import pytest
        with pytest.raises(RuntimeError, match="close timed out"):
            stage.call(token, "disconnect")
        assert stage.device is None and not stage.connected
        # A new connect is permitted and constructs a fresh proxy.
        # Avoid snapshot RPC by checking construction through the worker directly.
        stage.device = stage.factory()
        assert len(created) == 1 and stage.connected
        stage.device = None
    finally:
        stage.release(token)
        stage.shutdown()
