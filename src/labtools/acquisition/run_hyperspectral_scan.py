import os
import asyncio
import numpy as np
from datetime import datetime
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr

from labtools.devices.labjack_u6 import LabJackU6
from labtools.devices.scanning_mirror import ScanningMirror
from labtools.devices.itc4000 import ITC4000
from labtools.devices.horiba_spectrometer import HoribaSpectrometer
from labtools.acquisition.range_spectrum import get_range_spectrum


# ----------------------
# USER SETTINGS  # CAN CHANGE
# ----------------------
PRESET         = "syncerity"   # "syncerity" or "symphony"
EXPOSURE_TIME  = 50            # seconds
START_WL       = 850
END_WL         = 895
SLIT_WIDTH     = 0.1           # mm
OVERLAP        = 10            # pixel overlap between spectra for stitching
N_REPEATS      = 3
DARK_SUBTRACT  = True

X_START, X_STOP, NX = 0.25, 0.35, 3
Y_START, Y_STOP, NY = 1.65, 1.75, 3
LASER_CURRENT  = 0.08
LASER_WARMUP   = 5.0

BANDS = [
    ("NiV", 875, 890)
]

ITC4000_ADDRESS = 'USB0::0x1313::0x804A::M00739898::INSTR'
OUTPUT_DIR      = "C:\\Users\\Legend\\Documents\\test\\Hyperspectral maps\\"

OUTPUT_FOLDER = os.path.join(OUTPUT_DIR, datetime.now().strftime("%Y-%m-%d-%H.%M"))
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ============================================================
# LIVE PREVIEW FIGURE
# ============================================================

def save_live_preview(cube_partial, x_vals, y_vals, wl, last_spectrum, fname):
    """cube_partial: (Ny_done, Nx, Nλ)"""
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))

    im = axes[0].imshow(
        cube_partial.sum(axis=2),
        origin="lower",
        cmap="inferno",
        extent=[x_vals.min(), x_vals.max(), y_vals.min(), y_vals.max()]
    )
    axes[0].set_title("Live integrated intensity")
    axes[0].set_xlabel("Mirror X (V)")
    axes[0].set_ylabel("Mirror Y (V)")
    plt.colorbar(im, ax=axes[0], fraction=0.046)

    axes[1].plot(wl, last_spectrum)
    axes[1].set_title("Last acquired spectrum")
    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel("Intensity")

    plt.tight_layout()
    plt.savefig(fname)
    plt.close(fig)


def save_live_spectrum(wl, last_spectrum, fname):
    plt.plot(wl, last_spectrum)
    plt.title("Last acquired spectrum")
    plt.xlabel("Wavelength (nm)")
    plt.ylabel("Intensity")
    plt.tight_layout()
    plt.savefig(fname)
    plt.close()


# ============================================================
# MAIN ACQUISITION
# ============================================================

async def run():
    x_vals = np.linspace(X_START, X_STOP, NX)
    y_vals = np.linspace(Y_START, Y_STOP, NY)

    # --- mirror ---
    lj = LabJackU6()
    mirror = ScanningMirror(lj, dio_pin=2)

    # --- spectrometer ---
    async with HoribaSpectrometer(preset=PRESET) as spec:
        await spec.reset()
        await spec.configure(exposure_time=EXPOSURE_TIME)
        await spec.set_slit_width(SLIT_WIDTH)
        await spec.set_wavelength(START_WL)

        # --- laser ---
        laser = ITC4000(ITC4000_ADDRESS)

        if DARK_SUBTRACT:
            # acquire dark with laser off
            await asyncio.sleep(LASER_WARMUP)
            wl, DARK_SPECTRUM = await get_range_spectrum(
                spec, START_WL, END_WL,
                stitch_pixel_overlap=OVERLAP,
                n_frames=N_REPEATS,
                mode="sigma_clip",
            )
            laser.enable(current=LASER_CURRENT)
            await asyncio.sleep(LASER_WARMUP)
        else:
            laser.enable(current=LASER_CURRENT)
            await asyncio.sleep(LASER_WARMUP)

        # --- scan ---
        wavelength = None
        cube_list = []

        for iy, y in enumerate(y_vals):
            row_data = []

            for ix, x in enumerate(x_vals):
                mirror.move(x, y)

                wl, spectrum = await get_range_spectrum(
                    spec, START_WL, END_WL,
                    stitch_pixel_overlap=OVERLAP,
                    n_frames=N_REPEATS,
                    mode="sigma_clip",
                )

                if DARK_SUBTRACT:
                    spectrum = spectrum - DARK_SPECTRUM

                if wavelength is None:
                    wavelength = wl

                row_data.append(spectrum)
                save_live_spectrum(wl, spectrum, os.path.join(OUTPUT_FOLDER, "last_spectrum.png"))
                print(f"[SCAN] ({iy+1}/{NY}, {ix+1}/{NX}) complete")

            cube_list.append(row_data)

            cube_partial = np.array(cube_list)
            save_live_preview(
                cube_partial, x_vals, y_vals[:iy+1], wavelength, cube_list[-1][-1],
                os.path.join(OUTPUT_FOLDER, "live_preview.png"),
            )

        # --- shutdown ---
        laser.disable()
        laser.close()
        mirror.home()
        lj.close()

    # ============================================================
    # SAVE RESULTS
    # ============================================================
    cube_np = np.array(cube_list)
    wavelength = np.array(wavelength)

    # xarray (primary storage)
    cube_xr = xr.DataArray(
        cube_np,
        dims=("y_mirror", "x_mirror", "wavelength"),
        coords={"x_mirror": x_vals, "y_mirror": y_vals, "wavelength": wavelength},
        name="PL_intensity",
    )
    cube_xr.attrs["laser_current_A"] = LASER_CURRENT
    cube_xr.attrs["sumCount"] = N_REPEATS
    cube_xr.attrs["timestamp"] = datetime.now().isoformat()
    cube_xr.to_netcdf(os.path.join(OUTPUT_FOLDER, "spectral_cube.nc"))

    # NumPy NPZ
    np.savez(
        os.path.join(OUTPUT_FOLDER, "spectral_cube.npz"),
        cube=cube_np, x_mirror=x_vals, y_mirror=y_vals, wavelength=wavelength,
    )

    # Long-table CSV
    iy_idx, ix_idx, iwl_idx = np.meshgrid(
        np.arange(NY), np.arange(NX), np.arange(len(wavelength)), indexing="ij"
    )
    pd.DataFrame({
        "x_mirror":  x_vals[ix_idx.ravel()],
        "y_mirror":  y_vals[iy_idx.ravel()],
        "wavelength": wavelength[iwl_idx.ravel()],
        "intensity":  cube_np.ravel(),
    }).to_csv(os.path.join(OUTPUT_FOLDER, "spectral_cube_long.csv"), index=False)

    # Integrated intensity map
    plt.imshow(cube_np.sum(axis=2), origin="lower", cmap="inferno")
    plt.colorbar(label="Σ intensity")
    plt.savefig(os.path.join(OUTPUT_FOLDER, "integrated_map.png"))
    plt.close()

    # Band maps
    for name, wlmin, wlmax in BANDS:
        mask = (wavelength >= wlmin) & (wavelength <= wlmax)
        band = cube_np[:, :, mask].sum(axis=2)
        plt.imshow(band, origin="lower", cmap="inferno")
        plt.colorbar()
        plt.title(f"{name} ({wlmin}-{wlmax} nm)")
        plt.savefig(os.path.join(OUTPUT_FOLDER, f"band_{name}.png"))
        plt.close()

    print("[DONE] Acquisition finished cleanly")


if __name__ == "__main__":
    asyncio.run(run())

