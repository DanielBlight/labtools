"""Unique, reproducible figure/data exports and verified plot recipes."""
import csv
import gc
import json
import shutil
import subprocess
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .loaders import LoadSession, fingerprint, read_json
from .models import AnalysisError
from .plotting import render
from .processing import PlotState, colour_limits, map_values


def serialise(value):
    if isinstance(value, np.ndarray):
        return {'shape': list(value.shape), 'dtype': str(value.dtype)}
    if isinstance(value, np.generic):
        return serialise(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): serialise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialise(v) for v in value]
    return value


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(serialise(value), handle, indent=2, allow_nan=False)


def recipe(root, node, state, source, reference=None):
    source = Path(source).resolve()
    paths = sorted({item.source.resolve() for item in root.walk() if item.source.is_file()})
    # Retained run.json depends on arrays.npz; record both, plus sidecars.
    extra = set()
    for path in paths:
        for name in ('arrays.npz', 'metadata.json', 'intensity_map_metadata.json', 'spectrum_metadata.json', 'hyperspectral_metadata.json'):
            if (path.parent / name).is_file():
                extra.add(path.parent / name)
    for item in root.walk():
        if item.source.is_dir():
            for name in ('metadata.json', 'result.json', 'program.json', 'sequence.json', 'run.json'):
                if (item.source / name).is_file():
                    extra.add(item.source / name)
    paths = sorted(set(paths) | extra)
    base = source if source.is_dir() else source.parent
    identities = []
    for path in paths:
        try:
            relative = str(path.relative_to(base))
        except ValueError:
            relative = str(path)
        identities.append({'path': relative, 'sha256': fingerprint(path)})
    try:
        revision = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[3]), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = 'unavailable'
    return {'schema': 'labtools-analysis-recipe', 'version': 1, 'source': str(source),
            'source_is_directory': source.is_dir(), 'identities': identities,
            'node_key': node.key, 'reference_key': reference.key if reference else '',
            'state': state.to_dict(), 'software_revision': revision,
            'analysis_version': 'offline-analysis-v1', 'source_base_revision': 'ca3ecf342b8696e437b345f3e59e4c0f0ce06b06',
            'synthetic': node.synthetic, 'metadata': serialise(node.metadata)}


def open_recipe(path, source_override=None, cancel=None):
    document = read_json(path)
    if document.get('schema') != 'labtools-analysis-recipe' or document.get('version') != 1:
        raise AnalysisError('Unsupported plot recipe schema/version')
    state = PlotState.from_dict(document.get('state'))
    source = Path(source_override or document.get('source', '')).expanduser().resolve()
    if not source.exists():
        raise AnalysisError('Recipe source moved or is missing; choose Relink recipe source')
    base = source if source.is_dir() else source.parent
    identities = document.get('identities')
    if not isinstance(identities, list) or not identities:
        raise AnalysisError('Recipe has no source identities')
    for identity in identities:
        if cancel is not None and cancel():
            raise AnalysisError('Recipe loading cancelled')
        if not isinstance(identity, dict) or set(identity) != {'path', 'sha256'}:
            raise AnalysisError('Invalid source identity in recipe')
        target = Path(identity['path'])
        if not target.is_absolute():
            target = base / target
        if not target.is_file() or fingerprint(target, cancel) != identity['sha256']:
            raise AnalysisError(f'Recipe source missing or changed: {target.name}')
    session = LoadSession(cancel=cancel)
    try:
        root = session.load(source)
        nodes = {item.key: item for item in root.walk()}
        if document['node_key'] not in nodes:
            raise AnalysisError('Recipe measurement is not present in this source')
        reference = nodes.get(document.get('reference_key', ''))
        if document.get('reference_key') and reference is None:
            raise AnalysisError('Recipe reference measurement is missing')
        return session, root, nodes[document['node_key']], state, reference, source
    except BaseException:
        session.close()
        raise



def _publish_directory(staging: Path, final: Path) -> None:
    """Atomically publish a completed export with bounded Windows lock retries."""
    last_error: PermissionError | None = None
    for attempt in range(20):
        try:
            staging.rename(final)
            return
        except PermissionError as error:
            last_error = error
            # Matplotlib backends and Windows scanners can briefly retain handles.
            # Releasing Python finalizers before retrying avoids publishing partial data.
            gc.collect()
            time.sleep(0.015 * (attempt + 1))
    raise PermissionError(
        f"Windows kept the completed Analysis export locked for 2.85 s: {staging}"
    ) from last_error

def export_view(destination, root, node, state, source, *, reference=None, formats=('png', 'svg', 'pdf'), common_nodes=()):
    """All-or-nothing unique directory; source paths are never opened for writing."""
    destination = Path(destination).resolve()
    # Refuse exports inside an acquisition tree: no future loader pollution.
    source_path = Path(source).resolve()
    source_dir = source_path if source_path.is_dir() else source_path.parent
    if destination == source_dir or source_dir in destination.parents:
        raise AnalysisError('Choose an export directory outside the source acquisition folder')
    if set(formats) - {'png', 'svg', 'pdf'}:
        raise AnalysisError('Unsupported figure format')
    destination.mkdir(parents=True, exist_ok=True)
    tag = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    staging = destination / ('.analysis-' + tag)
    final = destination / ('analysis-' + tag)
    staging.mkdir()
    figure = Figure(figsize=(10, 6))
    FigureCanvasAgg(figure)
    try:
        arrays, details = render(figure, node, state, reference=reference, common_nodes=common_nodes)
        for extension in formats:
            figure.savefig(staging / ('plot.' + extension), dpi=state.dpi)
        with (staging / 'displayed_data.npz').open('xb') as handle:
            np.savez_compressed(handle, **arrays)
        for name, value in arrays.items():
            if name.endswith('wavelength_nm'):
                prefix = name[:-len('wavelength_nm')]
                y = arrays.get(prefix + 'intensity')
                if y is not None:
                    with (staging / (prefix + 'spectrum.csv')).open('x', newline='', encoding='utf-8') as handle:
                        writer = csv.writer(handle)
                        writer.writerow(['wavelength_nm', 'intensity'])
                        writer.writerows(zip(value, y))
        if 'trend_x' in arrays:
            with (staging / 'trend.csv').open('x', newline='', encoding='utf-8') as handle:
                writer = csv.writer(handle)
                writer.writerow([state.trend_axis, state.trend_metric])
                writer.writerows(zip(arrays['trend_x'], arrays['trend_y']))
        write_json(staging / 'recipe.json', recipe(root, node, state, source, reference))
        write_json(staging / 'plot_metadata.json', details)
        figure.clear()
        gc.collect()
        _publish_directory(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        figure.clear()
    return final


def export_collection(destination, root, selection, state, source):
    """One unique batch with common map limits and a stack-wide numerical archive."""
    destination = Path(destination).resolve()
    source_dir = Path(source).resolve()
    if source_dir.is_file():
        source_dir = source_dir.parent
    if destination == source_dir or source_dir in destination.parents:
        raise AnalysisError('Choose an export directory outside the source acquisition folder')
    items = [item for item in selection.walk() if item.kind != 'group']
    if not items:
        raise AnalysisError('Selection contains no numerical measurements')
    state = replace(state, comparison='none', reference_key='')
    maps = [item for item in items if item.kind == 'map']
    if state.common and maps:
        lo, hi = colour_limits((map_values(item, state) for item in maps), state)
        state = replace(state, vmin=lo, vmax=hi)
    tag = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    destination.mkdir(parents=True, exist_ok=True)
    staging, final = destination / ('.batch-' + tag), destination / ('analysis-batch-' + tag)
    staging.mkdir()
    stack_arrays, index = {}, []
    try:
        for number, item in enumerate(items):
            target = export_view(staging, root, item, state, source, common_nodes=items)
            prefix = f'measurement_{number:04d}_'
            if item.kind == 'map':
                for name, value in item.arrays.items():
                    stack_arrays[prefix + name] = value
                stack_arrays[prefix + 'displayed_map'] = map_values(item, state)
            index.append({'prefix': prefix, 'node_key': item.key, 'label': item.label,
                          'kind': item.kind, 'export': target.name, 'metadata': serialise(item.metadata)})
        with (staging / 'stack_data.npz').open('xb') as handle:
            np.savez_compressed(handle, **stack_arrays)
        write_json(staging / 'batch_index.json', {'state': state.to_dict(), 'measurements': index})
        _publish_directory(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final
