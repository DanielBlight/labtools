"""Failure injection: no real hardware, no changes to checkpoint schemas."""
from contextlib import contextmanager
import pytest
from labtools.runtime.cleanup import cleanup_actions
from labtools.acquisition import intensity_map as acquisition
from labtools.acquisition.intensity_map import IntensityMapConfig


@pytest.mark.parametrize('primary', [False, True])
@pytest.mark.parametrize('failed', [(), ('checkpoint',), ('home',), ('close',), ('checkpoint', 'home', 'close')])
def test_independent_cleanup(primary, failed):
    calls = []
    original = TimeoutError('acquisition failed')
    def action(name):
        def run():
            calls.append(name)
            if name in failed:
                raise OSError(name)
        return run
    def run():
        with cleanup_actions(*[(n, action(n)) for n in ('checkpoint', 'home', 'close')]):
            if primary:
                raise original
    if primary:
        with pytest.raises(TimeoutError) as caught:
            run()
        assert caught.value is original
        assert len(getattr(original, '__notes__', [])) == len(failed)
    elif failed:
        with pytest.raises(ExceptionGroup) as caught:
            run()
        assert len(caught.value.exceptions) == len(failed)
    else:
        run()
    assert calls == ['checkpoint', 'home', 'close']


@pytest.mark.parametrize('failure', ['configure', 'open', 'move', 'count', 'checkpoint', 'home', 'close', 'multiple'])
def test_acquisition_cleanup_at_every_failure(tmp_path, monkeypatch, failure):
    calls = []
    primary = TimeoutError('original count failure')
    def record(name):
        calls.append(name)
        if name == 'checkpoint' and 'devices opened' not in calls:
            return
        if name == failure or (failure == 'multiple' and name in ('checkpoint', 'home', 'close')):
            raise OSError(name)
        if failure == 'multiple' and name == 'count':
            raise primary
    class Mirror:
        def move(self, *args): record('move')
        def home(self): record('home')
    class Gate:
        def open(self): record('open')
        def close(self): record('close')
    class Counter:
        def configure_channel(self, *args, **kwargs): record('configure')
        def get_simultaneous_counts(self, channels, *args, **kwargs):
            record('count')
            return {c: 10 for c in channels}
    @contextmanager
    def devices(config):
        try:
            calls.append('devices opened')
            yield Mirror(), Gate(), Counter()
        finally:
            calls.append('devices released')
    monkeypatch.setattr(acquisition, 'open_map_devices', devices)
    monkeypatch.setattr(acquisition, '_save_checkpoint', lambda *a, **k: record('checkpoint'))
    config = IntensityMapConfig(
        x_start_v=-1., x_stop_v=1., x_points=2,
        y_start_v=-1., y_stop_v=1., y_points=2,
        channels=(1,), channel_thresholds_v=(.1,), channel_edges=('rising',),
        integration_time_s=.01, settle_time_s=0., output_root=tmp_path,
        backend='simulation', save_results=False, checkpoint_every_points=100,
    )
    with pytest.raises(Exception) as caught:
        acquisition.acquire_intensity_map(config)
    assert 'home' in calls and 'close' in calls and 'devices released' in calls
    assert calls.index('home') < calls.index('close') < calls.index('devices released')
    if failure == 'multiple':
        assert caught.value is primary
        assert len(primary.__notes__) == 4
    elif failure in ('configure', 'open', 'move', 'count'):
        assert isinstance(caught.value, OSError)
        assert str(caught.value) == failure
    else:
        assert isinstance(caught.value, ExceptionGroup)


def test_cleanup_failure_inside_unrelated_exception_handler():
    def fail():
        raise OSError("cleanup")
    try:
        raise ValueError("unrelated")
    except ValueError:
        with pytest.raises(ExceptionGroup):
            with cleanup_actions(("close", fail)):
                pass
