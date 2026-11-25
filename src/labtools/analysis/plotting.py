"""One renderer for the Qt canvas and headless exports; no pyplot or Qt imports."""
import numpy as np
from matplotlib.colors import LogNorm, Normalize

from .models import AnalysisError
from .processing import (
    MIRROR_ASPECT,
    colour_limits,
    compare,
    fit_peak,
    integrate,
    map_comparison,
    map_values,
    metrics,
    spectrum_values,
)


def _edges(values):
    if values.size == 1:
        return np.array([values[0] - .5, values[0] + .5])
    middle = (values[:-1] + values[1:]) / 2
    return np.r_[values[0] - (middle[0] - values[0]), middle, values[-1] + (values[-1] - middle[-1])]


def _map(figure, axes, node, values, state, limits):
    lo, hi = limits
    norm = LogNorm(lo, hi) if state.log else Normalize(lo, hi)
    display = np.ma.masked_invalid(values)
    if state.log:
        display = np.ma.masked_less_equal(display, 0)
    image = axes.pcolormesh(_edges(node.arrays['x']), _edges(node.arrays['y']), display,
                            cmap=state.cmap, norm=norm, shading='flat', rasterized=True)
    axes.set_xlim(_edges(node.arrays['x'])[[0, -1]])
    axes.set_ylim(_edges(node.arrays['y'])[[0, -1]])
    axes.set_aspect(MIRROR_ASPECT, adjustable='box')
    axes.set(xlabel='Mirror X voltage (V)', ylabel='Mirror Y voltage (V)', title=node.label)
    unit = 'Counts' if state.quantity == 'counts' else 'Count rate (counts/s)'
    if node.kind == 'cube':
        unit = 'Wavelength / width (nm)' if state.cube_view in {'peak_wavelength', 'fit_width'} else 'Intensity (saved units)'
        if state.cube_view in {'area', 'fit_area'}:
            unit += ' x nm'
    if state.comparison == 'ratio':
        unit = 'Ratio (dimensionless)'
    figure.colorbar(image, ax=axes, pad=.03, label=unit)


def _spectrum(axes, node, state, output, prefix=''):
    x, y = spectrum_values(node, state)
    axes.plot(x, y, label=node.label)
    output[prefix + 'wavelength_nm'] = x
    output[prefix + 'intensity'] = y
    details = {}
    if state.fit:
        fitted, details = fit_peak(x, y)
        axes.plot(x, fitted, label='Gaussian fit')
        output[prefix + 'fit'] = fitted
        output[prefix + 'residual'] = y - fitted
    axes.set(xlabel='Wavelength (nm)', ylabel='Normalised intensity' if state.normalise != 'none' else 'Intensity (saved units)')
    return details


def render(figure, node, state, *, reference=None, common_nodes=()):
    """Return the exact displayed arrays and provenance; never mutate source data."""
    state.validate()
    if node.kind in {'map', 'cube'} and state.comparison == 'overlay':
        raise AnalysisError('Map overlays are ambiguous; use side-by-side, difference or ratio')
    if node.kind == 'cube' and state.comparison == 'side-by-side':
        raise AnalysisError('Cube viewer reserves the second plot for the linked spectrum; use difference or ratio')
    if state.fit and state.comparison in {'difference', 'ratio'}:
        raise AnalysisError('Disable fitting for difference/ratio views; fits refer to individual spectra')
    figure.clear()
    output, details = {}, {'label': node.label, 'kind': node.kind, 'synthetic': node.synthetic,
                            'status': node.status, 'aspect_y_per_x': MIRROR_ASPECT}
    if node.kind in {'map', 'cube'}:
        values = map_values(node, state)
        if state.comparison in {'difference', 'ratio'}:
            if reference is None:
                raise AnalysisError('Choose a reference dataset')
            values = map_comparison(node, reference, state)
        output.update(x_v=node.arrays['x'], y_v=node.arrays['y'], displayed_map=values,
                      completed_mask=node.arrays['mask'])
        details['metrics'] = metrics(values)
        if node.kind == 'cube' and state.cube_view in {'fit_width', 'fit_area'}:
            details['fit_map'] = {'model': 'Gaussian + constant', 'maxfev': 5000,
                'bounds': 'positive amplitude; centre within selected wavelengths; sigma from range*1e-6 to range',
                'successful_pixels': int(np.isfinite(values).sum()),
                'failed_acquired_pixels': int(np.count_nonzero(node.arrays['mask'] & ~np.isfinite(values))),
                'failure_representation': 'missing derived value; raw spectrum remains available'}
        candidates = [values]
        if state.common and state.comparison not in {'difference', 'ratio'}:
            candidates = [map_values(item, state) for item in common_nodes if item.kind == node.kind] or candidates
        limits = colour_limits(candidates, state)
        if state.comparison == 'side-by-side' and reference is not None and node.kind == 'map':
            limits = colour_limits([values, map_values(reference, state)], state)
        details['colour_limits'] = list(limits)
        two = node.kind == 'cube' or state.comparison == 'side-by-side'
        cube_residuals = node.kind == 'cube' and state.fit and state.residuals
        if cube_residuals:
            grid = figure.add_gridspec(2, 2)
            axes = figure.add_subplot(grid[:, 0])
        else:
            axes = figure.add_subplot(121 if two else 111)
        _map(figure, axes, node, values, state, limits)
        if node.kind == 'cube':
            spectrum_axes = figure.add_subplot(grid[0, 1]) if cube_residuals else figure.add_subplot(122)
            try:
                details['fit'] = _spectrum(spectrum_axes, node, state, output, 'pixel_')
                spectrum_axes.set_title(f'Pixel X={state.pixel_x}, Y={state.pixel_y}')
                axes.plot(node.arrays['x'][state.pixel_x], node.arrays['y'][state.pixel_y], 'c+', markersize=10)
                spectrum_axes.legend()
                if cube_residuals and 'pixel_residual' in output:
                    residual_axes = figure.add_subplot(grid[1, 1], sharex=spectrum_axes)
                    residual_axes.plot(output['pixel_wavelength_nm'], output['pixel_residual'])
                    residual_axes.set(xlabel='Wavelength (nm)', ylabel='Fit residual')
            except AnalysisError as error:
                spectrum_axes.text(.5, .5, str(error), ha='center', va='center', wrap=True, transform=spectrum_axes.transAxes)
                details['pixel_diagnostic'] = str(error)
        elif state.comparison == 'side-by-side':
            if reference is None:
                raise AnalysisError('Choose a reference map')
            other = map_values(reference, state)
            output['reference_map'] = other
            _map(figure, figure.add_subplot(122), reference, other, state,
                 colour_limits([values, other], state))
    elif node.kind == 'anneal':
        axes = figure.add_subplot(111)
        output.update(node.arrays)
        axes.plot(node.arrays['elapsed_s'], node.arrays['x_voltage_v'], marker='.', label='Mirror X')
        axes.plot(node.arrays['elapsed_s'], node.arrays['y_voltage_v'], marker='.', label='Mirror Y')
        axes.set(xlabel='Saved elapsed time (s)', ylabel='Mirror voltage (V)', title='Recorded anneal positions, not planned completion')
        axes.legend()
        details['recorded_positions'] = int(node.arrays['elapsed_s'].size)
    elif node.kind == 'spectrum':
        axes = figure.add_subplot(211 if state.fit and state.residuals else 111)
        details['fit'] = _spectrum(axes, node, state, output)
        if state.comparison != 'none':
            if reference is None or reference.kind != 'spectrum':
                raise AnalysisError('Choose a reference spectrum')
            x, y = spectrum_values(node, state)
            rx, ry = spectrum_values(reference, state)
            if state.comparison in {'difference', 'ratio'}:
                if x.shape != rx.shape or not np.allclose(x, rx):
                    raise AnalysisError('Spectral comparison needs identical wavelength grids')
                axes.clear()
                values = compare(y, ry, state.comparison)
                axes.plot(x, values, label=state.comparison)
                output['intensity'] = values
                output['reference_intensity'] = ry
                axes.set(xlabel='Wavelength (nm)', ylabel=state.comparison)
            else:
                _spectrum(axes, reference, state, output, 'reference_')
        if state.fit and state.residuals:
            residual_axes = figure.add_subplot(212, sharex=axes)
            residual_axes.plot(output['wavelength_nm'], output['residual'])
            residual_axes.set(xlabel='Wavelength (nm)', ylabel='Fit residual')
        axes.set_title(node.label)
        axes.legend()
    else:
        _group(figure, node, state, output, details, reference)
    title = 'SYNTHETIC DATA | ' if node.synthetic else ''
    derived = node.kind == 'cube' or state.group_view == 'trend' or state.baseline != 'none' or state.normalise != 'none' or state.comparison in {'difference', 'ratio'}
    figure.suptitle(title + ('Derived view | ' if derived else '') + node.label, fontsize=11)
    figure.subplots_adjust(left=.1, right=.93, bottom=.13, top=.85, wspace=.55, hspace=.45)
    return output, details


def _group(figure, node, state, output, details, reference=None):
    maps = [item for item in node.walk() if item.kind in {'map', 'cube'}]
    spectra = [item for item in node.walk() if item.kind == 'spectrum']
    axes = figure.add_subplot(111)
    if state.group_view == 'trend':
        _trend(axes, node, state, output, details)
    elif spectra:
        if state.comparison == 'side-by-side':
            raise AnalysisError('Use overlay, difference or ratio for a spectrum sequence')
        if state.comparison in {'difference', 'ratio'}:
            baseline = reference or spectra[0]
            if baseline.kind != 'spectrum':
                raise AnalysisError('Choose a spectrum reference')
            rx, ry = spectrum_values(baseline, state)
            details['baseline_reference'] = baseline.label
            for index, item in enumerate(spectra):
                x, y = spectrum_values(item, state)
                if x.shape != rx.shape or not np.allclose(x, rx):
                    raise AnalysisError('Sequence spectral comparison needs matching wavelength grids')
                values = compare(y, ry, state.comparison)
                axes.plot(x, values, label=item.label)
                output[f'spectrum_{index:04d}_wavelength_nm'] = x
                output[f'spectrum_{index:04d}_intensity'] = values
            axes.set(xlabel='Wavelength (nm)', ylabel=state.comparison + ' from ' + baseline.label)
        else:
            for index, item in enumerate(spectra):
                _spectrum(axes, item, state, output, f'spectrum_{index:04d}_')
        axes.legend(fontsize=8)
        details['view'] = 'Chronological spectrum overlay; select a child for individual processing'
    elif maps:
        rows = [metrics(map_values(item, state)) for item in maps]
        output['measurement_index'] = np.arange(1, len(rows) + 1)
        for name in ('mean', 'median', 'maximum', 'gradient_rms'):
            values = np.array([r[name] if r[name] is not None else np.nan for r in rows])
            output[name] = values
            axes.plot(output['measurement_index'], values, marker='o', label=name)
        axes.set(xlabel='Saved measurement index (chronological)', ylabel='Map comparison metric (saved units)')
        axes.legend()
        details['metrics'] = rows
        details['metric_definition'] = 'gradient_rms = RMS of finite horizontal and vertical neighbour differences; no filtering, not an automatic best-focus decision'
    else:
        axes.axis('off')
        axes.text(.03, .95, 'Run metadata / timeline\n\nSelect a saved measurement in the dataset browser.\nNo numerical measurement is present at this node.', va='top', transform=axes.transAxes)
        details['view'] = 'metadata only'


def _trend(axes, node, state, output, details):
    rows = []
    failures = []
    for index, item in enumerate(n for n in node.walk() if n.kind in {'map', 'cube', 'spectrum'}):
        meta = item.metadata
        if state.trend_axis == 'index':
            horizontal = index + 1
        elif state.trend_axis == 'cumulative_dwell_s':
            horizontal = meta.get('cumulative_dwell_s', (meta.get('anneal') or {}).get('cumulative_dwell_s'))
        else:
            horizontal = meta.get(state.trend_axis)
        if horizontal is None:
            failures.append(f'{item.label}: no saved {state.trend_axis}')
            continue
        try:
            if item.kind == 'map':
                values = map_values(item, state)
                summary = metrics(values)
                metric = summary.get(state.trend_metric)
                if state.trend_metric == 'integral':
                    metric = float(np.nansum(values)) if np.isfinite(values).any() else None
            else:
                x, y = spectrum_values(item, state)
                valid = np.isfinite(y)
                order = np.argsort(x[valid])
                if state.trend_metric == 'integral':
                    metric = float(integrate(y[valid][order], x[valid][order]))
                elif state.trend_metric in {'centre_nm', 'fwhm_nm', 'area'}:
                    _fit, fit = fit_peak(x, y)
                    metric = fit[state.trend_metric]
                elif state.trend_metric in {'mean', 'median', 'maximum'}:
                    function = {'mean': np.mean, 'median': np.median, 'maximum': np.max}[state.trend_metric]
                    metric = float(function(y[valid]))
                else:
                    metric = None
            if metric is not None and np.isfinite(metric) and np.isfinite(float(horizontal)):
                rows.append((float(horizontal), float(metric), item.label))
            else:
                failures.append(f'{item.label}: metric unavailable')
        except AnalysisError as error:
            failures.append(f'{item.label}: {error}')
    if not rows:
        raise AnalysisError('No valid saved measurements for this trend: ' + '; '.join(failures[:3]))
    output['trend_x'] = np.array([row[0] for row in rows])
    output['trend_y'] = np.array([row[1] for row in rows])
    axes.plot(output['trend_x'], output['trend_y'], marker='o')
    axes.set(xlabel=state.trend_axis, ylabel=state.trend_metric)
    details['trend'] = {'axis': state.trend_axis, 'metric': state.trend_metric, 'labels': [row[2] for row in rows], 'excluded': failures}
