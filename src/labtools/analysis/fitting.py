"""Bounded multi-component fits with ordered, non-overlapping centre bounds."""
import warnings

import numpy as np

from .models import AnalysisError


def fit_components(x, y, state):
    from scipy.optimize import OptimizeWarning, brentq, curve_fit
    from scipy.signal import find_peaks
    from scipy.special import voigt_profile

    valid = np.isfinite(x) & np.isfinite(y)
    xx, yy = x[valid], y[valid]
    order = np.argsort(xx)
    xx, yy = xx[order], yy[order]
    model, n = state.fit_model, state.fit_peaks
    stride = 4 if model == 'Voigt' else 3
    span = np.ptp(xx) if xx.size else 0
    if xx.size <= n * stride + 2 or span <= 0 or np.ptp(yy) <= 0:
        raise AnalysisError('Too few finite samples or no signal variation for the selected fit')
    floor = max(span * 1e-6, float(np.median(np.diff(xx))) / 10)
    if state.fit_centres.strip():
        try:
            centres = sorted(map(float, state.fit_centres.split(',')))
        except ValueError as error:
            raise AnalysisError('Enter comma-separated peak centres in nm') from error
    elif n == 1:
        centres = [xx[np.argmax(yy)]]
    else:
        peaks, _ = find_peaks(yy, distance=max(2, len(xx) // (n * 8)), prominence=np.ptp(yy) * 0.03)
        centres = sorted(xx[peaks[np.argsort(yy[peaks])[-n:]]])
    if len(centres) != n or not np.isfinite(centres).all() or np.any(np.diff(centres) <= 0) or not xx[0] <= centres[0] <= centres[-1] <= xx[-1]:
        raise AnalysisError('Cannot seed the requested peaks. Enter distinct initial centres in the fit window.')
    edges = [xx[0], *((np.asarray(centres[1:]) + centres[:-1]) / 2), xx[-1]]

    def profile(t, widths):
        w = widths[0]
        if model == 'Gaussian':
            return np.exp(-0.5 * (t / w)**2)
        if model == 'Lorentzian':
            return 1 / (1 + (t / w)**2)
        return voigt_profile(t, *widths) / voigt_profile(0, *widths)

    def curve(t, *parameters):
        values = np.full(np.shape(t), parameters[-1], dtype=float)
        for i in range(n):
            height, center, *widths = parameters[i * stride:(i + 1) * stride]
            values += height * profile(t - center, widths)
        return values

    lo, hi, initial = [], [], []
    offset = float(np.percentile(yy, 10))
    for i, centre in enumerate(centres):
        lo += [0, edges[i], *([floor] * (stride - 2))]
        hi += [np.inf, edges[i + 1], *([span] * (stride - 2))]
        initial += [max(float(np.interp(centre, xx, yy) - offset), np.ptp(yy) / 100),
                    centre, *([max(floor, (edges[i + 1] - edges[i]) / 8)] * (stride - 2))]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', OptimizeWarning)
            parameters, cov = curve_fit(curve, xx, yy, p0=[*initial, offset],
                bounds=([*lo, -np.inf], [*hi, np.inf]), maxfev=5000)
        if not np.isfinite(cov).all() or not np.isfinite(parameters).all():
            raise AnalysisError('Fit parameters or uncertainties are not finite')
        components = []
        for i in range(n):
            height, centre, *widths = parameters[i * stride:(i + 1) * stride]
            w = widths[0]
            if model == 'Gaussian':
                fwhm, area = 2*np.sqrt(2*np.log(2))*w, height*w*np.sqrt(2*np.pi)
            elif model == 'Lorentzian':
                fwhm, area = 2*w, height*np.pi*w
            else:
                fwhm = 2*brentq(lambda t, widths=widths: profile(t, widths) - .5, 0, 20*sum(widths))
                area = height / voigt_profile(0, *widths)
            components.append({
                'amplitude': float(height),
                'centre_nm': float(centre),
                'fwhm_nm': float(fwhm),
                'area': float(area),
                'widths_nm': list(map(float, widths)),
            })
    except (ValueError, RuntimeError, OptimizeWarning, FloatingPointError) as error:
        raise AnalysisError(f'{model} fit did not converge reliably: {error}') from error
    return curve(x, *parameters), {'model': f'{n} × {model} + constant', 'components': components,
        **components[state.fit_component - 1], 'offset': float(parameters[-1]),
        'standard_errors': np.sqrt(np.diag(cov)).tolist()}


def component_curve(x, model, component):
    """Evaluate one fitted component above its shared constant offset."""
    delta = x - component['centre_nm']
    width = component['widths_nm'][0]
    if model == 'Gaussian':
        shape = np.exp(-0.5 * (delta / width)**2)
    elif model == 'Lorentzian':
        shape = 1 / (1 + (delta / width)**2)
    else:
        from scipy.special import voigt_profile

        widths = component['widths_nm']
        shape = voigt_profile(delta, *widths) / voigt_profile(0, *widths)
    return component['amplitude'] * shape
