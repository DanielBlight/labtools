"""Explicit, non-destructive scientific transformations and plot state."""
import warnings
from dataclasses import asdict, dataclass, fields

import numpy as np

from .models import AnalysisError

# Same calibration as visualisation.intensity_map, kept independent of GUI imports.
MIRROR_ASPECT = 0.75
integrate = getattr(np, 'trapezoid', None) or np.trapz


@dataclass
class PlotState:
    quantity: str = 'rates'
    channel: int = -1
    cube_view: str = 'sum'
    variant: str = 'intensity'
    low_nm: float | None = None
    high_nm: float | None = None
    pixel_x: int = 0
    pixel_y: int = 0
    normalise: str = 'none'
    baseline: str = 'none'
    background_roi: str = ''
    fit_model: str = 'Gaussian'
    fit_peaks: int = 1
    fit_centres: str = ''
    fit_component: int = 1
    fit: bool = False
    residuals: bool = False
    comparison: str = 'none'
    reference_key: str = ''
    cmap: str = 'inferno'
    log: bool = False
    common: bool = False
    vmin: float | None = None
    vmax: float | None = None
    group_view: str = 'overlay'
    trend_metric: str = 'integral'
    trend_axis: str = 'index'
    dpi: int = 300

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) - {f.name for f in fields(cls)}:
            raise AnalysisError('Invalid plot recipe settings')
        state = cls(**data)
        state.validate()
        return state

    def validate(self):
        choices = {
            'fit_model': {'Gaussian', 'Lorentzian', 'Voigt'},
            'group_view': {'overlay', 'trend'},
            'trend_metric': {'integral', 'mean', 'median', 'maximum', 'gradient_rms', 'centre_nm', 'fwhm_nm', 'area', 'shared_mean'},
            'trend_axis': {'index', 'cycle', 'cumulative_dwell_s', 'requested_dc_v'},
            'quantity': {'rates', 'counts', 'summed'},
            'cube_view': {'sum', 'area', 'band', 'wavelength', 'peak', 'peak_wavelength', 'fit_width', 'fit_area'},
            'variant': {'intensity', 'raw', 'dark', 'corrected'},
            'normalise': {'none', 'maximum', 'area'},
            'baseline': {'none', 'linear', 'minimum'},
            'comparison': {'none', 'overlay', 'side-by-side', 'difference', 'ratio'},
        }
        for name, options in choices.items():
            if not isinstance(getattr(self, name), str) or getattr(self, name) not in options:
                raise AnalysisError(f'Invalid {name}')
        for name in ('low_nm', 'high_nm', 'vmin', 'vmax'):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value)):
                raise AnalysisError(f'{name} must be finite or empty')
        for name in ('channel', 'pixel_x', 'pixel_y', 'dpi'):
            if type(getattr(self, name)) is not int:
                raise AnalysisError(f'{name} must be an integer')
        if self.channel < -1 or self.pixel_x < 0 or self.pixel_y < 0 or not 72 <= self.dpi <= 1200:
            raise AnalysisError('Invalid channel, pixel or export DPI')
        for name in ('fit', 'residuals', 'log', 'common'):
            if type(getattr(self, name)) is not bool:
                raise AnalysisError(f'{name} must be boolean')
        if (type(self.fit_peaks) is not int or not 1 <= self.fit_peaks <= 4
                or type(self.fit_component) is not int or not 1 <= self.fit_component <= self.fit_peaks
                or not isinstance(self.fit_centres, str) or not isinstance(self.background_roi, str)):
            raise AnalysisError('Invalid peak count, component, centres or background region')
        if not isinstance(self.cmap, str) or not isinstance(self.reference_key, str):
            raise AnalysisError('Invalid colour map or reference')
        if self.low_nm is not None and self.high_nm is not None and self.low_nm > self.high_nm:
            raise AnalysisError('Lower wavelength exceeds upper wavelength')
        if (self.vmin is None) != (self.vmax is None):
            raise AnalysisError('Set both colour limits or leave both empty')
        if self.vmin is not None and self.vmin >= self.vmax:
            raise AnalysisError('Colour minimum must be less than maximum')
        if self.log and self.vmin is not None and self.vmin <= 0:
            raise AnalysisError('Log colour minimum must be positive')
        return self

    def to_dict(self):
        return asdict(self)


def _variant(node, state):
    a = node.arrays
    if state.variant == 'corrected':
        if 'raw' in a and 'dark' in a:
            if node.kind == 'cube':
                return a['raw']  # Subtract row/pixel-sized dark slices below.
            return np.asarray(a['raw'], dtype=float) - a['dark']
        # Native SpectrumResult.intensity already contains the saved dark mode.
        provenance = node.metadata.get('provenance') or {}
        dark_mode = node.metadata.get('dark_mode')
        if isinstance(provenance, dict):
            dark_mode = provenance.get('dark_mode', dark_mode)
        if dark_mode not in (None, 'none', 'off'):
            return a['intensity']
        raise AnalysisError('No saved dark correction or raw/dark pair is available')
    if state.variant not in a:
        raise AnalysisError(f'No {state.variant} data were saved')
    return a[state.variant]


def wavelength_selection(w, state):
    selection = np.ones(w.shape, dtype=bool)
    if state.low_nm is not None:
        selection &= w >= state.low_nm
    if state.high_nm is not None:
        selection &= w <= state.high_nm
    if not selection.any():
        raise AnalysisError('No wavelengths lie in the selected range')
    return selection


def shared_background(node, state):
    """Median completed spectrum in an explicit rectangle of mirror voltages."""
    if not state.background_roi or node.kind != 'cube':
        return None
    try:
        x0, x1, y0, y1 = map(float, state.background_roi.split(','))
    except ValueError as error:
        raise AnalysisError('Background ROI needs X min, X max, Y min, Y max (V)') from error
    if not np.isfinite([x0, x1, y0, y1]).all() or x0 > x1 or y0 > y1:
        raise AnalysisError('Invalid background voltage bounds')
    a = node.arrays
    mask = a['mask'] & ((a['x'] >= x0) & (a['x'] <= x1))[None, :] & ((a['y'] >= y0) & (a['y'] <= y1))[:, None]
    count = int(mask.sum())
    if count < 3 or count * a['wavelength'].size > 8_000_000:
        raise AnalysisError('Choose a smaller background region with at least three completed spectra (max 8 million samples)')
    cube = _variant(node, state)
    values = np.asarray(cube[mask], dtype=float)
    if state.variant == 'corrected' and 'raw' in a and 'dark' in a:
        values -= a['dark'][mask] if a['dark'].ndim == 3 else a['dark']
    values[~np.isfinite(values)] = np.nan
    if not np.isfinite(values).any(axis=0).all():
        raise AnalysisError('Background region has no finite reference at one or more wavelengths')
    return np.nanmedian(values, axis=0), count


def map_values(node, state, *, cancel=None):
    state.validate()
    a = node.arrays
    if node.kind == 'map':
        key = state.quantity
        if key == 'rates' and 'rates' not in a and 'summed' in a and state.channel == -1:
            key = 'summed'
        if key not in a:
            raise AnalysisError(f'{key} were not saved in this map')
        value = a[key]
        if value.ndim == 3:
            if state.channel == -1:
                # Preserve all-NaN measured pixels rather than inventing zero.
                valid = np.isfinite(value).any(axis=0)
                value = np.where(valid, np.nansum(value, axis=0), np.nan)
            elif state.channel < value.shape[0]:
                value = value[state.channel]
            else:
                raise AnalysisError('Selected channel is not present')
        elif state.channel != -1:
            raise AnalysisError('This archive only contains a summed map')
        result = np.array(value, dtype=float, copy=True)
    elif node.kind == 'cube':
        cube = _variant(node, state)
        background = shared_background(node, state)
        w = a['wavelength']
        if state.cube_view == 'wavelength':
            if state.low_nm is None or not min(w) <= state.low_nm <= max(w):
                raise AnalysisError('Set lower wavelength to a target within the saved spectral range')
            selected = np.zeros(w.shape, dtype=bool)
            selected[int(np.argmin(np.abs(w - state.low_nm)))] = True
        else:
            selected = wavelength_selection(w, state)
        indices = np.flatnonzero(selected)
        if state.cube_view in {'fit_width', 'fit_area'}:
            from importlib.util import find_spec
            if find_spec('scipy') is None:
                raise AnalysisError('Cube fit maps require the existing optional scipy dependency')
            if np.count_nonzero(a['mask']) > 4096:
                raise AnalysisError('Bounded cube fitting supports at most 4096 acquired pixels per map; use a smaller saved cube')
        result = np.full(a['mask'].shape, np.nan)
        # Row-sized working arrays bound extra RAM even for mapped cubes.
        for iy in range(result.shape[0]):
            row = np.asarray(cube[iy, :, indices[0]:indices[-1] + 1], dtype=float)
            if state.variant == 'corrected' and 'raw' in a and 'dark' in a:
                dark = a['dark']
                dark_row = dark[iy, :, indices[0]:indices[-1] + 1] if dark.ndim == 3 else dark[indices[0]:indices[-1] + 1]
                row = row - dark_row
            if background is not None:
                row = row - background[0][indices[0]:indices[-1] + 1]
            valid = np.isfinite(row).any(axis=-1)
            safe = np.where(np.isfinite(row), row, -np.inf)
            if state.cube_view in {'sum', 'band', 'wavelength'}:
                values = np.nansum(row, axis=-1)
            elif state.cube_view == 'area':
                if indices.size < 2:
                    raise AnalysisError('Spectral area needs at least two wavelengths')
                order = np.argsort(w[selected])
                values = integrate(row[:, order], w[selected][order], axis=-1)
            elif state.cube_view in {'fit_width', 'fit_area'}:
                values = np.full(row.shape[0], np.nan)
                for ix in range(row.shape[0]):
                    if cancel is not None and cancel():
                        raise AnalysisError('Fitted map cancelled')
                    if not a['mask'][iy, ix]:
                        continue
                    try:
                        _fitted, parameters = fit_peak(w[selected], row[ix], state)
                        values[ix] = parameters['fwhm_nm' if state.cube_view == 'fit_width' else 'area']
                    except AnalysisError:
                        # Failure is explicitly counted in plot metadata, never a raw-data edit.
                        continue
            elif state.cube_view == 'peak':
                values = safe.max(axis=-1)
            else:
                values = w[selected][safe.argmax(axis=-1)]
            result[iy] = np.where(valid, values, np.nan)
    else:
        raise AnalysisError('Select a map or hyperspectral cube')
    result[~a['mask']] = np.nan
    return result


def compare(first, second, mode):
    if first.shape != second.shape:
        raise AnalysisError('Comparison requires matching array shapes')
    valid = np.isfinite(first) & np.isfinite(second)
    result = np.full(first.shape, np.nan)
    if mode == 'difference':
        np.subtract(first, second, out=result, where=valid)
    elif mode == 'ratio':
        np.divide(first, second, out=result, where=valid & (second != 0))
    else:
        raise AnalysisError('Unknown comparison operation')
    return result


def quantity_key(node, state):
    a = node.arrays
    if node.kind == 'map':
        key = state.quantity
        channels = tuple(np.asarray(a.get('channels', ())).tolist())
        channel = channels[state.channel:state.channel + 1] if state.channel >= 0 else channels
        return ('map', node.synthetic, 'counts' if key == 'counts' else 'counts/s', channel)
    details = node.metadata.get('settings') or {}
    if not isinstance(details, dict):
        details = {}
    lineage = node.metadata.get('provenance') or {}
    if not isinstance(lineage, dict):
        lineage = {}
    return (node.kind, node.synthetic, state.cube_view if node.kind == 'cube' else state.normalise,
            str(node.metadata.get('units', node.metadata.get('intensity_units'))),
            str(details.get('exposure_s')), str(details.get('gain')),
            node.metadata.get('dark_mode', lineage.get('dark_mode')), lineage.get('reusable_dark_stage'))


def require_compatible(node, reference, state):
    if quantity_key(node, state) != quantity_key(reference, state):
        raise AnalysisError('Comparison requires matching measurement quantities, channels, units and recorded acquisition settings')
    if node.kind == 'cube':
        x, y = node.arrays['wavelength'], reference.arrays['wavelength']
        if x.shape != y.shape or not np.allclose(x, y, rtol=0, atol=1e-8):
            raise AnalysisError('Cube comparison requires matching wavelength grids')


def map_comparison(node, reference, state, *, derived=None):
    require_compatible(node, reference, state)
    for key in ('x', 'y'):
        if node.arrays[key].shape != reference.arrays[key].shape or not np.allclose(node.arrays[key], reference.arrays[key], rtol=0, atol=1e-12):
            raise AnalysisError('Map comparison requires identical voltage grids; no implicit interpolation')
    if derived is not None:
        return compare(derived(node), derived(reference), state.comparison)
    return compare(map_values(node, state), map_values(reference, state), state.comparison)


def spectrum_values(node, state, *, background=None):
    state.validate()
    a = node.arrays
    if node.kind not in {'cube', 'spectrum'}:
        raise AnalysisError('Select a spectrum or hyperspectral cube')
    w = a['wavelength']
    value = _variant(node, state)
    if node.kind == 'cube':
        iy, ix = state.pixel_y, state.pixel_x
        if iy >= a['mask'].shape[0] or ix >= a['mask'].shape[1]:
            raise AnalysisError('Selected pixel is outside this cube')
        if not a['mask'][iy, ix]:
            raise AnalysisError('Selected pixel was not acquired')
        value = value[iy, ix]
        if state.variant == 'corrected' and 'raw' in a and 'dark' in a:
            dark = a['dark']
            value = value - (dark[iy, ix] if dark.ndim == 3 else dark)
    if background is None:
        background = shared_background(node, state)
    if background is not None:
        value = value - background[0]
    selection = wavelength_selection(w, state)
    x, y = np.array(w[selection], dtype=float), np.array(value[selection], dtype=float)
    if not np.isfinite(y).any():
        raise AnalysisError('Selected spectrum contains no finite data')
    finite = np.isfinite(y)
    if state.baseline == 'minimum':
        y -= np.min(y[finite])
    elif state.baseline == 'linear':
        endpoints = np.flatnonzero(finite)[[0, -1]]
        if endpoints[0] == endpoints[1]:
            raise AnalysisError('Linear baseline needs two finite samples')
        y -= np.interp(x, np.sort(x[endpoints]), y[endpoints][np.argsort(x[endpoints])])
    if state.normalise != 'none':
        if state.normalise == 'maximum':
            divisor = np.max(np.abs(y[finite]))
        else:
            order = np.argsort(x[finite])
            divisor = integrate(y[finite][order], x[finite][order])
        if not np.isfinite(divisor) or divisor == 0:
            raise AnalysisError('Cannot normalise a zero or non-finite spectrum')
        y /= divisor
    return x, y


def fit_peak(x, y, state=None):
    if state is not None and (state.fit_model != 'Gaussian' or state.fit_peaks != 1 or state.fit_centres):
        from .fitting import fit_components

        try:
            return fit_components(x, y, state)
        except ImportError as error:
            raise AnalysisError('Peak fitting requires the optional scipy analysis dependency') from error
    return _fit_gaussian(x, y)


def _fit_gaussian(x, y):
    """Optional bounded Gaussian + constant; never silently alter the data."""
    try:
        from scipy.optimize import OptimizeWarning, curve_fit
    except ImportError as error:
        raise AnalysisError('Peak fitting requires the optional scipy analysis dependency') from error
    valid = np.isfinite(x) & np.isfinite(y)
    xx, yy = x[valid], y[valid]
    if xx.size < 6 or np.ptp(xx) <= 0 or np.ptp(yy) <= 0:
        raise AnalysisError('Peak fit needs six finite samples and a non-flat signal')
    def gaussian(t, amplitude, centre, sigma, offset):
        return offset + amplitude * np.exp(-0.5 * ((t - centre) / sigma)**2)
    initial = [np.ptp(yy), xx[np.argmax(yy)], np.ptp(xx) / 10, np.min(yy)]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', OptimizeWarning)
            params, covariance = curve_fit(gaussian, xx, yy, p0=initial,
                bounds=([0, xx.min(), np.ptp(xx) * 1e-6, -np.inf], [np.inf, xx.max(), np.ptp(xx), np.inf]), maxfev=5000)
    except (ValueError, RuntimeError, OptimizeWarning, FloatingPointError) as error:
        raise AnalysisError(f'Gaussian fit did not converge reliably: {error}') from error
    if not np.isfinite(params).all() or not np.isfinite(covariance).all():
        raise AnalysisError('Gaussian fit has non-finite parameters or uncertainty')
    fitted = gaussian(x, *params)
    return fitted, {'model': 'Gaussian + constant', 'amplitude': float(params[0]), 'centre_nm': float(params[1]),
                    'sigma_nm': float(params[2]), 'fwhm_nm': float(2.354820045 * params[2]),
                    'area': float(params[0] * params[2] * np.sqrt(2 * np.pi)), 'offset': float(params[3]),
                    'standard_errors': np.sqrt(np.diag(covariance)).tolist()}


def metrics(values):
    finite = np.isfinite(values)
    data = values[finite]
    if not data.size:
        return {'finite_pixels': 0, 'mean': None, 'median': None, 'maximum': None, 'gradient_rms': None}
    differences = []
    for dim in (0, 1):
        delta = np.diff(values, axis=dim)
        differences.append(delta[np.isfinite(delta)])
    delta = np.concatenate(differences)
    return {'finite_pixels': int(data.size), 'mean': float(data.mean()), 'median': float(np.median(data)),
            'maximum': float(data.max()), 'gradient_rms': float(np.sqrt(np.mean(delta**2))) if delta.size else None}


def colour_limits(arrays, state):
    state.validate()
    if state.vmin is not None:
        return state.vmin, state.vmax
    low, high = [], []
    for array in arrays:
        valid = np.isfinite(array) & ((array > 0) if state.log else True)
        if valid.any():
            low.append(float(array[valid].min()))
            high.append(float(array[valid].max()))
    if not low:
        raise AnalysisError('No positive finite pixels for log scale' if state.log else 'No finite acquired pixels to plot')
    lo, hi = min(low), max(high)
    if hi == lo:
        hi = lo * 1.01 if state.log else lo + max(1, abs(lo) * .01)
    return lo, hi
