from pathlib import Path

import pytest

from labtools.config.spectrum import SpectrumSettings
from labtools.measurements import (
 MeasurementRecipe,
 MeasurementRuntime,
 SpectrumRequest,
 execute_recipe,
)


def sim_recipe(kind="spectrum"):
 s=SpectrumSettings("dispatch-v1","syncerity",.065,0,0,.1,500,510,backend="simulation")
 return MeasurementRecipe(kind,SpectrumRequest(s,owner="dispatch"))
def test_simulation_spectrum_and_dark():
 assert execute_recipe(sim_recipe()).provenance.synthetic
 assert execute_recipe(sim_recipe("dark")).settings.configuration_id=="dispatch-v1"
def test_path_dispatch():
 result=execute_recipe(Path("examples/measurements/recipes/alignment_simulation.json"));assert result.provenance.synthetic
def test_borrowed_runtime_stays_open():
 with MeasurementRuntime(backend="simulation") as runtime:
  execute_recipe(sim_recipe(),runtime=runtime);assert not runtime.status().closed
def test_backend_mismatch():
 with MeasurementRuntime(backend="simulation") as runtime:
  real=MeasurementRecipe("spectrum",SpectrumRequest(SpectrumSettings("x","syncerity",.065,0,0,.1,500,510,backend="real")))
  with pytest.raises(PermissionError):execute_recipe(real,runtime=runtime)
def test_real_confirmation_required_before_runtime():
 real=MeasurementRecipe("spectrum",SpectrumRequest(SpectrumSettings("x","syncerity",.065,0,0,.1,500,510,backend="real")))
 with pytest.raises(PermissionError):execute_recipe(real)
 with pytest.raises(RuntimeError,match="confirmed"):
  execute_recipe(real,confirm_real=lambda _:(_ for _ in ()).throw(RuntimeError("confirmed before backend")))
def test_rejected_confirmation():
 real=MeasurementRecipe("spectrum",SpectrumRequest(SpectrumSettings("x","syncerity",.065,0,0,.1,500,510,backend="real")))
 with pytest.raises(PermissionError):execute_recipe(real,confirm_real=lambda _:False)
def test_intensity_map_progress_and_cancel(tmp_path):
 from dataclasses import replace

 from labtools.measurements import load_recipe
 recipe=load_recipe("examples/measurements/recipes/intensity_map_simulation.json")
 recipe=MeasurementRecipe("intensity_map",replace(recipe.request,config=replace(recipe.request.config,output_root=tmp_path)))
 seen=[];calls=[0]
 def stop():calls[0]+=1;return calls[0]>2
 result=execute_recipe(recipe,progress=seen.append,cancel_requested=stop);assert not result.result.complete and seen
