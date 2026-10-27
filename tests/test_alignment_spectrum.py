import asyncio
from dataclasses import replace
from threading import Event
import numpy as np
import pytest
from labtools.acquisition.alignment_spectrum import AlignmentConfig, LatestSpectrum, run_alignment


def options(preset):
    return dict(gains=(("gain",2),), speeds=(("speed",0),), minimum_exposure_s=.065 if preset == "syncerity" else .1,
                default_gain=2, default_speed=0)


def make(stop, fail=None, stop_at=None, delay=0):
    calls, loops, starts = [], [], []
    class Spec:
        def record(self, name):
            calls.append(name); loops.append(id(asyncio.get_running_loop()))
            if stop_at == name: stop.set()
            if fail == name: raise OSError(name)
        async def connect(self): self.record("connect")
        async def configure(self, **kw):
            self.record("configure")
            assert kw == dict(gain=2,speed=0,exposure_time=.1,roi=None,minimum_exposure_override_s=.02)
        async def set_wavelength(self, value):
            self.record("move"); assert value == 690; return 690.1
        async def get_spectrum(self, **kw):
            self.record("capture")
            assert kw == dict(n_frames=1,mode="single",dark_frame_mode="none")
            starts.append(asyncio.get_running_loop().time())
            await asyncio.sleep(delay)
            return [691.,690.], [2.,1.]
        async def disconnect(self): self.record("disconnect")
    return lambda **kw: Spec(), calls, loops, starts


@pytest.mark.parametrize("preset",["syncerity","symphony"])
def test_one_connection_move_and_loop(preset):
    stop=Event(); factory,calls,loops,starts=make(stop); frames=[]
    def received(f):
        frames.append(f)
        if len(frames)==3: stop.set()
    assert asyncio.run(run_alignment(AlignmentConfig(preset=preset,subtract_dark=False),stop,received,
                       factory=factory,options_provider=options)) == 3
    assert calls == ["connect","configure","move","capture","capture","capture","disconnect"]
    assert len(set(loops))==1
    np.testing.assert_array_equal(frames[0].wavelength_nm,[690,691])
    np.testing.assert_array_equal(frames[0].intensity,[1,2])
    assert not frames[0].intensity.flags.writeable


@pytest.mark.parametrize("stage",["connect","configure","move","capture"])
def test_failure_cleanup(stage):
    stop=Event(); factory,calls,_,_=make(stop,fail=stage)
    with pytest.raises(OSError,match=stage):
        asyncio.run(run_alignment(AlignmentConfig(),stop,lambda f:None,factory=factory,options_provider=options))
    assert calls[-1]=="disconnect"


@pytest.mark.parametrize("stage",["connect","configure","move","capture"])
def test_stop_at_each_stage(stage):
    stop=Event(); factory,calls,_,_=make(stop,stop_at=stage)
    asyncio.run(run_alignment(AlignmentConfig(),stop,lambda f:None,factory=factory,options_provider=options))
    assert calls[-1]=="disconnect"
    assert calls.count("capture")==int(stage=="capture")


@pytest.mark.parametrize("field,value",[("preset","bad"),("centre_nm",float("nan")),("centre_nm",-1),
    ("exposure_s",0),("exposure_s",float("inf")),("subtract_dark",1),("gain",True),("speed",1.2),
    ("exposure_s",.01),("gain",99)])
def test_invalid_before_hardware(field,value):
    stop=Event(); factory,calls,_,_=make(stop)
    with pytest.raises(ValueError):
        asyncio.run(run_alignment(replace(AlignmentConfig(),**{field:value}),stop,lambda f:None,
                                 factory=factory,options_provider=options))
    assert not calls


def test_already_stopped():
    stop=Event(); stop.set(); factory,calls,_,_=make(stop)
    assert asyncio.run(run_alignment(AlignmentConfig(),stop,lambda f:None,factory=factory,options_provider=options))==0
    assert not calls


def test_latest_only():
    box=LatestSpectrum()
    for i in range(100): box.put(i)
    assert box.take()==99 and box.take() is None


def test_primary_preserved_on_cleanup_failure():
    class Spec:
        async def connect(self): raise ValueError("primary")
        async def disconnect(self): raise OSError("cleanup")
    with pytest.raises(ValueError,match="primary") as caught:
        asyncio.run(run_alignment(AlignmentConfig(),Event(),lambda f:None,
                                 factory=lambda **kw:Spec(),options_provider=options))
    assert "disconnect also failed" in caught.value.__notes__[0]


def test_cleanup_failure_not_silenced():
    stop=Event(); factory,calls,_,_=make(stop,stop_at="capture",fail="disconnect")
    with pytest.raises(OSError,match="disconnect"):
        asyncio.run(run_alignment(AlignmentConfig(),stop,lambda f:None,factory=factory,options_provider=options))


def test_bad_data():
    stop=Event(); factory,calls,_,_=make(stop); spec=factory()
    async def invalid(**kw): return [1],[float("nan")]
    spec.get_spectrum=invalid
    with pytest.raises(RuntimeError,match="non-finite"):
        asyncio.run(run_alignment(AlignmentConfig(),stop,lambda f:None,factory=lambda **kw:spec,options_provider=options))
    assert calls[-1]=="disconnect"


@pytest.mark.parametrize("preset", ["syncerity", "symphony"])
@pytest.mark.parametrize("dark", [False, True])
def test_fast_loop_and_002_exposure(preset, dark):
    stop=Event(); calls=[]; frames=[]
    class Spec:
        async def connect(self): calls.append("connect")
        async def configure(self, **kw):
            assert kw["exposure_time"] == .02
            assert kw["minimum_exposure_override_s"] == .02
        async def set_wavelength(self, value): calls.append("move"); return value
        async def get_dark_spectrum(self, **kw):
            calls.append("dark"); return [1,2],[2,3]
        async def get_spectrum(self, **kw):
            calls.append("signal"); return [1,2],[5,8]
        async def disconnect(self): calls.append("disconnect")
    def received(frame):
        frames.append(frame)
        if len(frames)==3: stop.set()
    asyncio.run(run_alignment(AlignmentConfig(preset=preset, exposure_s=.02, subtract_dark=dark),
                stop, received, factory=lambda **kw:Spec(), options_provider=options))
    assert calls == ["connect","move"] + (["dark","signal"] if dark else ["signal"])*3 + ["disconnect"]
    np.testing.assert_array_equal(frames[0].intensity,[3,5] if dark else [5,8])


@pytest.mark.parametrize("problem", ["axis", "shape", "nan", "failure", "stop"])
def test_dark_errors_and_stop_cleanup(problem):
    stop=Event(); calls=[]
    class Spec:
        async def connect(self): pass
        async def configure(self, **kw): pass
        async def set_wavelength(self, value): return value
        async def get_dark_spectrum(self, **kw):
            if problem=="failure": raise OSError("dark failure")
            if problem=="stop": stop.set()
            return ([1,3] if problem=="axis" else [1,2],
                    [1] if problem=="shape" else [float("nan"),1] if problem=="nan" else [1,1])
        async def get_spectrum(self, **kw): calls.append("signal"); return [1,2],[4,5]
        async def disconnect(self): calls.append("disconnect")
    async def run():
        return await run_alignment(AlignmentConfig(subtract_dark=True),stop,lambda f:stop.set(),
                                  factory=lambda **kw:Spec(),options_provider=options)
    if problem=="stop":
        assert asyncio.run(run())==0
        assert calls==["disconnect"]
    else:
        with pytest.raises((RuntimeError,OSError)): asyncio.run(run())
        assert calls[-1]=="disconnect"


def test_wrapper_default_floor_and_explicit_override_contract():
    # Extract actual wrapper method without importing SDK or creating devices.
    import ast
    from pathlib import Path
    source=Path(__file__).resolve().parents[1]/"src/labtools/devices/horiba_spectrometer.py"
    tree=ast.parse(source.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="HoribaSpectrometer")
    method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="configure")
    method.returns=None
    for arg in method.args.args+method.args.kwonlyargs: arg.annotation=None
    module=ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]))
    ns={"np":np,"asyncio":asyncio}
    exec(compile(module,"actual-configure","exec"),ns)
    class Fake:
        mono=object(); ccd=object()
        _preset_name="fake"
        _preset={"minimum_exposure_s":.1}
        _ccd_configuration={}
        def _verify_detector_identity(self,c): pass
        def _validate_detector_token(self,*args): pass
    async def configuration(self): return {}
    class CCD:
        get_configuration=configuration
    f=Fake(); f.ccd=CCD()
    # Default still rejects 0.02 before any optical command.
    with pytest.raises(ValueError,match="at least"):
        asyncio.run(ns["configure"](f,exposure_time=.02))
    # Explicit override passes the floor and reaches the next optical readback.
    with pytest.raises(AttributeError,match="get_current_wavelength"):
        asyncio.run(ns["configure"](f,exposure_time=.02,minimum_exposure_override_s=.02))
    for floor in [.019,float("nan"),True]:
        with pytest.raises(ValueError,match="override"):
            asyncio.run(ns["configure"](f,exposure_time=.02,minimum_exposure_override_s=floor))
