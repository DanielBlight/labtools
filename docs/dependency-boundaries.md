# Dependency boundaries

## Purpose

LabTools supports operator GUIs, instrument integrations, analysis utilities and
notebook-based development. Those uses should not force every installation to carry the
entire research environment.

## Base runtime

A standard installation contains dependencies imported by the packaged application or
required by supported device adapters. This includes PyQt6, NumPy, Matplotlib, Loguru,
Pandas, Xarray, Tifffile, VISA/serial support, LabJack, HORIBA and camera/stage adapter
requirements.

Real-device availability still depends on compatible vendor SDKs, drivers and Windows
architecture. Installing a Python dependency does not constitute hardware acceptance.

## Optional analysis extra

Install additional scientific fitting and HDF5 tools with:

```powershell
uv sync --extra analysis
```

or from a built wheel:

```powershell
py -m pip install "lab-tools[analysis]"
```

The `analysis` extra currently contains H5py, Lmfit and SciPy. These packages are not
imported by the packaged runtime and should not enlarge every operator installation.

## Optional notebooks extra

Install notebook tooling with:

```powershell
uv sync --extra notebooks
```

This adds IPython kernel, Jupyter and JupyterLab. Notebook tooling is a development and
interactive-analysis surface, not an operator-runtime requirement.

## Optional Napari extra

Install Napari only where image exploration or plugin development requires it:

```powershell
uv sync --extra napari
```

Napari is not imported by the packaged runtime. Keeping it optional also prevents its
pytest plugins and GUI stack from affecting the standard test environment.

## Development environment

```powershell
uv sync --frozen --group dev
```

The development group contains test and lint tooling. Add optional extras explicitly
when working on those surfaces, for example:

```powershell
uv sync --frozen --group dev --extra analysis --extra notebooks --extra napari
```

## Change rule

Add a package to the base runtime only when packaged code imports it or an included
adapter requires it at runtime. Add research tools to a named extra. Record new extras
here and validate the base wheel without optional dependencies.
