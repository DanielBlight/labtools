"""One renderer for the Qt canvas and headless exports; no pyplot or Qt imports."""
from dataclasses import replace

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
    quantity_key,
    require_compatible,
    shared_background,
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
    hidden = node.arrays['mask'] & np.isfinite(values) & (values <= 0) if state.log else np.zeros(values.shape, bool)
    if hidden.any():
        iy, ix = np.nonzero(hidden)
        axes.scatter(node.arrays['x'][ix], node.arrays['y'][iy], s=6, c='grey', marker='x')
    coverage = f"{np.count_nonzero(node.arrays['mask'])}/{values.size} acquired"
    axes.set_title(f"{node.label} | {coverage}" + (f" | {hidden.sum()} nonpositive hidden" if hidden.any() else ""))
    figure.colorbar(image, ax=axes, pad=.03, label=unit)


def _spectrum(axes, node, state, output, prefix='', *, background=None):
    x, y = spectrum_values(node, state, background=background)
    axes.plot(x, y, label=node.label)
    output[prefix + 'wavelength_nm'] = x
    output[prefix + 'intensity'] = y
    details = {}
    if state.fit:
        fitted, details = fit_peak(x, y, state)
        axes.plot(x, fitted, label=details['model'])
        if len(details.get('components', [])) > 1:
            from .fitting import component_curve

            for index, peak in enumerate(details['components'], start=1):
                values = component_curve(x, state.fit_model, peak)
                axes.plot(x, values + details['offset'], '--', alpha=.65, label=f'Peak {index} + offset')
                output[f'{prefix}fit_peak_{index}'] = values

        output[prefix + 'fit'] = fitted
        output[prefix + 'residual'] = y - fitted
    axes.set(xlabel='Wavelength (nm)', ylabel='Normalised intensity' if state.normalise != 'none' else 'Intensity (saved units)')
    return details


def draw_cube_pixel(figure, node, state, output, details):
    """Change only linked artists; keep map zoom, limits, and colourbar intact."""
    axes, residual_axes, marker = figure._labtools_pixel_axes
    axes.clear()
    marker.set_data([], [])
    if residual_axes is not None:
        residual_axes.clear()
    for key in tuple(output):
        if key.startswith('pixel_'):
            del output[key]
    for key in ('fit', 'pixel_diagnostic'):
        details.pop(key, None)
    try:
        background = (output['background_intensity'], details['background']['completed_pixels']) if 'background_intensity' in output else None
        details['fit'] = _spectrum(axes, node, state, output, 'pixel_', background=background)
        x, y = node.arrays['x'][state.pixel_x], node.arrays['y'][state.pixel_y]
        axes.set_title(f'X={x:g} V, Y={y:g} V')
        marker.set_data([x], [y])
        axes.legend()
        if residual_axes is not None and 'pixel_residual' in output:
            residual_axes.plot(output['pixel_wavelength_nm'], output['pixel_residual'])
            residual_axes.set(xlabel='Wavelength (nm)', ylabel='Fit residual')
    except AnalysisError as error:
        axes.text(.5, .5, str(error), ha='center', va='center', wrap=True, transform=axes.transAxes)
        details['pixel_diagnostic'] = str(error)


def render(figure, node, state, *, reference=None, common_nodes=(), map_cache=None):
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
    def derived(item):
        if map_cache is None:
            return map_values(item, state)
        key = (item.key, tuple((name, value) for name, value in state.to_dict().items()
                               if name not in {'pixel_x', 'pixel_y', 'dpi', 'vmin', 'vmax', 'cmap', 'log', 'common'}))
        if key not in map_cache:
            if len(map_cache) >= 16:
                map_cache.pop(next(iter(map_cache)))
            map_cache[key] = map_values(item, state)
        return map_cache[key]

    if node.kind in {'map', 'cube'}:
        values = derived(node)
        provenance = node.metadata.get('provenance') or {}
        if not isinstance(provenance, dict):
            provenance = {}
        dark_mode = provenance.get('dark_mode', node.metadata.get('dark_mode'))
        dark_stage = provenance.get('reusable_dark_stage')
        details.update(dark_mode=dark_mode, reusable_dark_stage=dark_stage,
                       acquired_pixels=int(node.arrays['mask'].sum()), total_pixels=int(values.size))
        background = shared_background(node, state)
        if background is not None:
            output.update(background_wavelength_nm=node.arrays['wavelength'], background_intensity=background[0])
            details['background'] = {'method': 'spatial median of completed ROI spectra',
                                     'roi_volts': state.background_roi, 'completed_pixels': background[1]}
        if state.comparison in {'difference', 'ratio'}:
            if reference is None:
                raise AnalysisError('Choose a reference dataset')
            values = map_comparison(node, reference, state, derived=derived)
        output.update(x_v=node.arrays['x'], y_v=node.arrays['y'], displayed_map=values,
                      completed_mask=node.arrays['mask'])
        details['metrics'] = metrics(values)
        details['nonpositive_hidden_by_log'] = int(np.count_nonzero(np.isfinite(values) & (values <= 0))) if state.log else 0
        if node.kind == 'cube' and state.cube_view in {'fit_width', 'fit_area'}:
            details['fit_map'] = {'model': f'{state.fit_peaks} x {state.fit_model} + constant', 'maxfev': 5000,
                'component': state.fit_component, 'initial_centres_nm': state.fit_centres,
                'bounds': 'nonnegative amplitudes; ordered centres within fit window; positive widths',
                'successful_pixels': int(np.isfinite(values).sum()),
                'failed_acquired_pixels': int(np.count_nonzero(node.arrays['mask'] & ~np.isfinite(values))),
                'failure_representation': 'missing derived value; raw spectrum remains available'}
        candidates = [values]
        if state.common and state.comparison not in {'difference', 'ratio'}:
            candidates = (derived(item) for item in (node, *common_nodes) if quantity_key(item, state) == quantity_key(node, state))
        limits = colour_limits(candidates, state)
        if state.comparison == 'side-by-side' and reference is not None and node.kind == 'map':
            require_compatible(node, reference, state)
            limits = colour_limits([values, derived(reference)], state)
        signed_intensity = (node.kind == 'cube' and state.cube_view in {'sum', 'area', 'band', 'wavelength', 'peak'}
                            and (background is not None or (dark_mode not in (None, 'none') and state.variant in {'intensity', 'corrected'})))
        if not state.log and (signed_intensity or state.comparison == 'difference'):
            if state.vmin is None:
                bound = max(abs(limits[0]), abs(limits[1]))
                limits = (-bound, bound)
            if state.cmap == 'inferno':
                state = replace(state, cmap='coolwarm')
        details['colour_limits'] = list(limits)
        two = node.kind == 'cube' or state.comparison == 'side-by-side'
        cube_residuals = node.kind == 'cube' and state.fit and state.residuals
        if cube_residuals:
            grid = figure.add_gridspec(2, 2)
            axes = figure.add_subplot(grid[:, 0])
        else:
            axes = figure.add_subplot(121 if two else 111)
        _map(figure, axes, node, values, state, limits)
        if background is not None:
            x0, x1, y0, y1 = map(float, state.background_roi.split(','))
            axes.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], '--', color='cyan', alpha=.7)
        if node.kind == 'cube':
            spectrum_axes = figure.add_subplot(grid[0, 1]) if cube_residuals else figure.add_subplot(122)
            residual_axes = figure.add_subplot(grid[1, 1], sharex=spectrum_axes) if cube_residuals else None
            marker, = axes.plot([], [], 'c+', markersize=10)
            figure._labtools_pixel_axes = (spectrum_axes, residual_axes, marker)
            draw_cube_pixel(figure, node, state, output, details)
        elif state.comparison == 'side-by-side':
            if reference is None:
                raise AnalysisError('Choose a reference map')
            other = derived(reference)
            output['reference_map'] = other
            _map(figure, figure.add_subplot(122), reference, other, state,
                 limits)
    elif node.kind == 'calibration':
        axes = figure.add_subplot(111)
        axes.plot(node.arrays['wavelength_nm'], node.arrays['intensity'], label='Stitched dark')
        output.update(node.arrays)
        for index, centre in enumerate(node.metadata.get('centres_nm', [])):
            axes.plot(node.arrays[f'segment_{index}_wavelength_nm'], node.arrays[f'segment_{index}_intensity'],
                      alpha=.55, label=f'{centre:g} nm centre')
        axes.set(xlabel='Wavelength (nm)', ylabel='Dark intensity', title='Calibration only')
        axes.legend()
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
            require_compatible(node, reference, state)
            x, y = spectrum_values(node, state)
            rx, ry = spectrum_values(reference, state)
            if state.comparison in {'difference', 'ratio'}:
                if x.shape != rx.shape or not np.allclose(x, rx, rtol=0, atol=1e-8):
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
    if details.get('dark_mode') not in (None, 'none'):
        title += 'Saved dark-corrected data | ' if state.variant in {'intensity', 'corrected'} else 'Raw view | '
        if details.get('reusable_dark_stage'):
            title += details['reusable_dark_stage'].replace('_', '-') + ' acquisition | '
    if details.get('background'):
        title += 'ROI background removed | '
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
        if len({quantity_key(item, state) for item in spectra}) > 1:
            raise AnalysisError('Spectrum collection mixes incompatible quantities or settings; select a homogeneous run')
        if state.comparison == 'side-by-side':
            raise AnalysisError('Use overlay, difference or ratio for a spectrum sequence')
        if state.comparison in {'difference', 'ratio'}:
            marked = [item for item in spectra if str(item.metadata.get('role', '')).strip().lower()
                      in {'baseline', 'pre-anneal baseline', 'pre_anneal_baseline'}]
            if reference is None and len(marked) != 1:
                raise AnalysisError('No unique recorded baseline; choose an explicit spectrum reference')
            baseline = reference or marked[0]
            if baseline.kind != 'spectrum':
                raise AnalysisError('Choose a spectrum reference')
            rx, ry = spectrum_values(baseline, state)
            details['baseline_reference'] = baseline.label
            for index, item in enumerate(spectra):
                require_compatible(item, baseline, state)
                x, y = spectrum_values(item, state)
                if x.shape != rx.shape or not np.allclose(x, rx, rtol=0, atol=1e-8):
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
        if len({quantity_key(item, state) for item in maps}) > 1:
            raise AnalysisError('Collection mixes incompatible map quantities; select a homogeneous stack')
        rows = [metrics(map_values(item, state)) for item in maps]
        output['coverage'] = np.array([item.arrays['mask'].mean() for item in maps])
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
    items = [n for n in node.walk() if n.kind in {'map', 'cube', 'spectrum'}]
    if len({quantity_key(item, state) for item in items}) > 1:
        raise AnalysisError('Trend mixes measurement quantities or settings; select a homogeneous run or stack')
    if items and items[0].kind == 'cube':
        for item in items[1:]:
            require_compatible(items[0], item, state)
    shared = None
    if state.trend_metric == 'shared_mean' and items and items[0].kind in {'map', 'cube'}:
        first = items[0]
        for item in items[1:]:
            require_compatible(first, item, state)
            if any(not np.array_equal(item.arrays[key], first.arrays[key]) for key in ('x', 'y')):
                raise AnalysisError('Shared region requires identical spatial grids')
        shared = np.logical_and.reduce([item.arrays['mask'] & np.isfinite(map_values(item, state)) for item in items])
    for index, item in enumerate(items):
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
            coverage = None
            if item.kind in {'map', 'cube'}:
                values = map_values(item, state)
                summary = metrics(values)
                metric = summary.get(state.trend_metric)
                coverage = float(item.arrays['mask'].mean())
                if shared is not None and shared.any():
                    metric = float(np.mean(values[shared]))
                if state.trend_metric == 'integral':
                    metric = float(np.nansum(values)) if np.isfinite(values).any() else None
            else:
                x, y = spectrum_values(item, state)
                valid = np.isfinite(y)
                order = np.argsort(x[valid])
                if state.trend_metric == 'integral':
                    metric = float(integrate(y[valid][order], x[valid][order]))
                elif state.trend_metric in {'centre_nm', 'fwhm_nm', 'area'}:
                    _fit, fit = fit_peak(x, y, state)
                    metric = fit[state.trend_metric]
                elif state.trend_metric in {'mean', 'median', 'maximum'}:
                    function = {'mean': np.mean, 'median': np.median, 'maximum': np.max}[state.trend_metric]
                    metric = float(function(y[valid]))
                else:
                    metric = None
            if metric is not None and np.isfinite(metric) and np.isfinite(float(horizontal)):
                rows.append((float(horizontal), float(metric), item.label, coverage))
            else:
                failures.append(f'{item.label}: metric unavailable')
        except AnalysisError as error:
            failures.append(f'{item.label}: {error}')
    if not rows:
        raise AnalysisError('No valid saved measurements for this trend: ' + '; '.join(failures[:3]))
    output['trend_x'] = np.array([row[0] for row in rows])
    output['trend_y'] = np.array([row[1] for row in rows])
    if rows[0][3] is not None:
        output['coverage'] = np.array([row[3] for row in rows])
        for x, y, _label, covered in rows:
            if covered < 1:
                axes.annotate(f'{covered:.0%}', (x, y), xytext=(3, 5), textcoords='offset points')
    axes.plot(output['trend_x'], output['trend_y'], marker='o')
    ylabel = {'integral': 'Sum over acquired pixels', 'mean': 'Mean over acquired pixels',
              'shared_mean': 'Mean over shared valid region'}.get(state.trend_metric, state.trend_metric) if rows[0][3] is not None else state.trend_metric
    axes.set(xlabel=state.trend_axis, ylabel=ylabel)
    details['trend'] = {'axis': state.trend_axis, 'metric': state.trend_metric, 'labels': [row[2] for row in rows], 'excluded': failures}
