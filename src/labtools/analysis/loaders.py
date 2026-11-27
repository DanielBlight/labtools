"""Adapters for native maps, spectra, cubes, retained trees and run folders.

Only NumPy and the standard library are imported. NPZ object arrays are never
unpickled. Large members are streamed to private temporary NPY files and mapped
read-only; compressed NPZ files cannot themselves be memory-mapped.
"""
import csv
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path

import numpy as np

from .models import AnalysisError, Dataset, LoadCancelled

ALIASES = {
    'x': ('x_values_v', 'x_v', 'x_mirror'),
    'y': ('y_values_v', 'y_v', 'y_mirror'),
    'wavelength': ('wavelength_nm', 'wavelength'),
    'rates': ('count_rates_cps',),
    'counts': ('counts',),
    'summed': ('summed_count_rate_cps',),
    'mask': ('completed_mask',),
    'channels': ('channels',),
    'intensity': ('intensity', 'cube'),
    'raw': ('raw_intensity', 'intensity_raw'),
    'dark': ('dark',),
}


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as error:
        raise AnalysisError(f"Cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise AnalysisError(f"Expected a JSON object in {path}")
    return value


def is_synthetic(meta):
    if isinstance(meta, dict):
        return any((key in {'synthetic', 'synthetic_data', 'simulation_only'} and value is True)
                   or (key == 'backend' and value == 'simulation')
                   or (isinstance(value, (dict, list)) and is_synthetic(value))
                   for key, value in meta.items())
    if isinstance(meta, list):
        return any(is_synthetic(value) for value in meta)
    return False


class LoadSession:
    """Own read-only arrays/cache for one dataset, close after its viewer closes."""

    def __init__(self, cancel=None, mmap_threshold=32 * 1024 * 1024):
        self.cancel = cancel or (lambda: False)
        self.mmap_threshold = mmap_threshold
        self._temp = tempfile.TemporaryDirectory(prefix='labtools-analysis-')
        self._cache = {}
        self._visited = set()
        self.diagnostics = []

    def check(self):
        if self.cancel():
            raise LoadCancelled("Loading cancelled")

    def close(self):
        for arrays in self._cache.values():
            for value in arrays.values():
                if isinstance(value, np.memmap):
                    value._mmap.close()
        self._cache.clear()
        self._temp.cleanup()

    def archive(self, path):
        path = Path(path).resolve()
        self.check()
        if path in self._cache:
            return self._cache[path]
        result = {}
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > 10000:
                    raise AnalysisError("Archive contains too many members")
                for info in infos:
                    self.check()
                    if not info.filename.endswith('.npy'):
                        raise AnalysisError("NPZ contains a non-NPY member")
                    name = info.filename[:-4]
                    if name in result or '/' in name or '\\' in name:
                        raise AnalysisError("Invalid or duplicate NPZ member name")
                    if info.file_size > 64 * 1024**3:
                        raise AnalysisError("NPZ member exceeds the 64 GiB analysis limit")
                    if info.file_size >= self.mmap_threshold:
                        target = Path(self._temp.name) / f'{len(self._cache)}-{len(result)}.npy'
                        with archive.open(info) as source, target.open('xb') as output:
                            while True:
                                self.check()
                                chunk = source.read(1024 * 1024)
                                if not chunk:
                                    break
                                output.write(chunk)
                        value = np.load(target, mmap_mode='r', allow_pickle=False)
                    else:
                        with archive.open(info) as source:
                            value = np.load(source, allow_pickle=False)
                    if value.dtype.hasobject:
                        raise AnalysisError("Object arrays are not supported")
                    value.flags.writeable = False
                    result[name] = value
        except (OSError, ValueError, EOFError, zipfile.BadZipFile) as error:
            for value in result.values():
                if isinstance(value, np.memmap):
                    value._mmap.close()
            if isinstance(error, LoadCancelled):
                raise
            raise AnalysisError(f"Cannot read NPZ {path.name}: {error}") from error
        self._cache[path] = result
        return result

    def load(self, source):
        source = Path(source).expanduser().resolve()
        if not source.exists():
            raise AnalysisError(f"Dataset not found: {source}")
        node = self._path(source)
        if node is None:
            raise AnalysisError(f"No supported numerical data or run metadata in {source}. " + '; '.join(self.diagnostics[:3]))
        def inherit(parent, synthetic=False):
            parent.synthetic = parent.synthetic or synthetic
            for child in parent.children:
                inherit(child, parent.synthetic)
        inherit(node)
        occurrences = {}
        base = source if source.is_dir() else source.parent
        for child in node.walk():
            target = child.source.resolve()
            relative = target.relative_to(base).as_posix() if target.is_relative_to(base) else str(target)
            identity = (relative, child.kind)
            ordinal = occurrences.get(identity, 0)
            occurrences[identity] = ordinal + 1
            child.key = json.dumps([*identity, ordinal], separators=(',', ':'))
            child.validate()
        return node

    def _path(self, path):
        self.check()
        path = path.resolve()
        if path in self._visited:
            return None
        self._visited.add(path)
        if path.is_dir():
            return self._folder(path)
        if path.suffix.lower() == '.npz':
            if path.name == 'arrays.npz' and (path.parent / 'run.json').exists():
                return self._document(path.parent / 'run.json')
            return self._npz(path)
        if path.suffix.lower() == '.json':
            if path.name not in {'run.json', 'sequence.json', 'program.json'}:
                return self._folder(path.parent)
            return self._document(path)
        if path.suffix.lower() == '.csv':
            return self._csv(path)
        raise AnalysisError(f"Unsupported file: {path.name}. Open a result folder, NPZ, JSON or spectrum CSV.")

    def _metadata(self, path, arrays):
        meta = {}
        for name in ('metadata', 'metadata_json'):
            if name in arrays:
                try:
                    value = json.loads(str(arrays[name].item()))
                except (ValueError, TypeError) as error:
                    raise AnalysisError(f"Invalid embedded metadata in {path.name}") from error
                if not isinstance(value, dict):
                    raise AnalysisError("Embedded metadata must be an object")
                meta.update(value)
        for name in ('metadata.json', 'intensity_map_metadata.json', 'hyperspectral_metadata.json', 'spectrum_metadata.json'):
            sidecar = path.parent / name
            if sidecar.exists():
                meta.update(read_json(sidecar))
        return meta

    def _npz(self, path):
        data = self.archive(path)
        meta = self._metadata(path, data)
        if 'synthetic_data' in data:
            meta['synthetic_data'] = bool(data['synthetic_data'].item())
        if 'backend' in data:
            meta['backend'] = str(data['backend'].item())
        if meta.get('kind') == 'dark':
            version = meta.get('schema_version')
            if version not in {1, 2} or not {'wavelength_nm', 'intensity'} <= data.keys():
                raise AnalysisError('Invalid dark archive')
            arrays = {key: value for key, value in data.items() if key != 'metadata'}
            if version == 2:
                centres = meta.get('centres_nm')
                if not isinstance(centres, list) or not centres:
                    raise AnalysisError('Segmented dark has no centre list')
                for index, centre in enumerate(centres):
                    x = arrays.get(f'segment_{index}_wavelength_nm')
                    y = arrays.get(f'segment_{index}_intensity')
                    if (x is None or y is None or x.ndim != 1 or x.shape != y.shape
                            or type(centre) not in (int, float) or not np.isfinite(centre)):
                        raise AnalysisError('Invalid dark segment')
            return Dataset(path.stem, 'calibration', path, arrays, meta, synthetic=is_synthetic(meta))
        return self._numeric(data, path.stem, path, meta)

    def _numeric(self, data, label, source, meta):
        a = {}
        for canonical, names in ALIASES.items():
            for name in names:
                if name in data and isinstance(data[name], np.ndarray):
                    a[canonical] = data[name]
                    break
        if meta.get('schema_version', 1) != 1:
            raise AnalysisError('Unsupported measurement schema version')
        provenance = meta.get('provenance') or {}
        if isinstance(provenance, dict) and provenance.get('archive_schema_version', 1) != 1:
            raise AnalysisError('Unsupported hyperspectral archive schema version')
        kind = None
        if 'x' in a and 'y' in a:
            kind = 'cube' if 'wavelength' in a and 'intensity' in a and a['intensity'].ndim == 3 else 'map'
            if 'mask' not in a:
                shape = (a['y'].size, a['x'].size)
                candidate = a.get('summed', a.get('intensity', a.get('rates', a.get('counts'))))
                if candidate is None:
                    raise AnalysisError("Map axes exist but numerical data are missing")
                finite = np.isfinite(candidate)
                if kind == 'cube':
                    finite = finite.any(axis=-1)
                elif finite.ndim == 3:
                    finite = finite.any(axis=0)
                if finite.shape != shape:
                    raise AnalysisError("Map shape does not match its coordinate axes")
                a['mask'] = finite
                meta = {**meta, 'analysis_warning': 'No completion mask saved; finite values are displayed, completion is unknown.'}
        elif 'wavelength' in a and 'intensity' in a and a['intensity'].ndim == 1:
            kind = 'spectrum'
        if kind is None:
            raise AnalysisError(f"Unrecognised numerical schema in {source.name}: {', '.join(data)}")
        if kind == 'map':
            a = {k: v for k, v in a.items() if k in {'x', 'y', 'mask', 'channels', 'counts', 'rates', 'summed'}}
        elif kind == 'spectrum':
            a = {k: v for k, v in a.items() if k in {'wavelength', 'intensity', 'raw', 'dark'}}
        else:
            a = {k: v for k, v in a.items() if k in {'x', 'y', 'mask', 'wavelength', 'intensity', 'raw', 'dark'}}
        status = meta.get('status', 'completed' if meta.get('complete') is True or meta.get('completed') is True else 'partial' if meta.get('complete') is False else 'unknown')
        return Dataset(label, kind, source, a, meta, synthetic=is_synthetic(meta), status=str(status)).validate()

    def _decode(self, value, arrays):
        self.check()
        if isinstance(value, dict):
            if 'array' in value and set(value) <= {'array', 'dtype', 'shape'}:
                name = value['array']
                if name not in arrays:
                    raise AnalysisError(f"Retained array {name} is missing")
                array = arrays[name]
                if 'shape' in value and list(array.shape) != value['shape']:
                    raise AnalysisError(f"Retained array {name} shape differs from run.json")
                if 'dtype' in value and str(array.dtype) != value['dtype']:
                    raise AnalysisError(f"Retained array {name} dtype differs from run.json")
                return array
            if set(value) == {'type', 'fields'}:
                return self._decode(value['fields'], arrays)
            return {k: self._decode(v, arrays) for k, v in value.items()}
        if isinstance(value, list):
            return [self._decode(v, arrays) for v in value]
        return value

    def _retained(self, value, label, source, inherited):
        self.check()
        meta = {**inherited}
        if isinstance(value, dict):
            meta.update({k: v for k, v in value.items() if not isinstance(v, (list, np.ndarray))})
            if any(isinstance(value.get(name), np.ndarray) for name in ('wavelength_nm', 'x_values_v', 'x_v', 'x_mirror')):
                return self._numeric(value, label, source, meta)
        node = Dataset(label, 'group', source, metadata=meta, synthetic=is_synthetic(meta), status=str(meta.get('status', 'unknown')))
        iterable = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else []
        for key, child in iterable:
            if key == 'latest_progress' and isinstance(value, dict) and value.get('result') is not None:
                continue
            if isinstance(child, (dict, list)):
                title = str(key)
                if isinstance(child, dict):
                    title = str(child.get('role', child.get('phase', child.get('label', title))))
                    if 'requested_dc_v' in child:
                        title = f"Sweep {int(child.get('sweep', 0)) + 1}, DC {child['requested_dc_v']:g} V"
                    elif 'cycle' in child:
                        title = f"Cycle {child['cycle']} / {title}"
                item = self._retained(child, title, source, meta)
                if item.children or item.kind != 'group' or (isinstance(child, dict) and any(k in child for k in ('status', 'role', 'phase', 'completed'))):
                    node.children.append(item)
        return node

    def _document(self, path):
        document = read_json(path)
        if document.get('schema_version', 1) != 1:
            raise AnalysisError('Unsupported run schema version')
        if 'result' in document and (path.parent / 'arrays.npz').exists():
            decoded = self._decode(document, self.archive(path.parent / 'arrays.npz'))
            node = self._retained(decoded['result'], document.get('label', path.parent.name), path,
                                  {'settings': decoded.get('settings'), 'synthetic_data': is_synthetic(decoded)})
            node.metadata['settings'] = decoded.get('settings')
            return node
        node = Dataset(path.parent.name, 'group', path, metadata=document, synthetic=is_synthetic(document), status=str(document.get('status', 'unknown')))
        if 'maps' in document:
            for index, entry in enumerate(document['maps']):
                self.check()
                relative = entry.get('result_folder', f'map-{index + 1:04d}')
                target = path.parent / relative
                child = self._path(target) if target.exists() else None
                if child is None:
                    child = Dataset(f'Map {index + 1}: missing output', 'group', target)
                child.label = f"Sweep {int(entry.get('sweep', 0)) + 1}, DC {entry.get('requested_dc_v', '?')} V"
                child.metadata.update(entry)
                node.children.append(child)
        elif 'steps' in document:
            spectra = None
            archive = path.parent / 'arrays.npz'
            if archive.exists():
                spectra = self.archive(archive)
            for index, entry in enumerate(document['steps']):
                self.check()
                role = entry.get('role', entry.get('phase', f'Step {index + 1}'))
                child = Dataset(f"{index + 1}. {role}", 'group', path, metadata=entry, synthetic=node.synthetic, status=str(entry.get('status', 'unknown')))
                if spectra is not None and 'spectra' in spectra:
                    selection = entry.get('measurement', {}).get('array_index')
                    if selection is not None:
                        data = {'wavelength_nm': spectra['wavelength_nm'], 'intensity': spectra['spectra'][selection]}
                        child = self._numeric(data, child.label, path, {**entry, 'synthetic_data': node.synthetic})
                relative = entry.get('source') or entry.get('output')
                if relative:
                    target = Path(relative)
                    if not target.is_absolute():
                        target = path.parent / target
                    if not target.exists():
                        # Native sequence metadata may contain a moved absolute path.
                        target = path.parent / Path(str(relative).replace('\\', '/')).name
                    if target.exists():
                        loaded = self._path(target)
                        if loaded is not None:
                            for measurement in loaded.walk():
                                measurement.metadata = {**entry, **measurement.metadata}
                            child.children.append(loaded)
                    else:
                        child.metadata = {**entry, 'analysis_warning': f'Measurement output not found: {relative}'}
                node.children.append(child)
        self._append_folder_children(node, path.parent)
        return node

    def _append_folder_children(self, node, folder):
        for child_path in sorted(folder.iterdir()):
            self.check()
            if child_path.name == 'intensity_map_checkpoint.npz' and (folder / 'intensity_map_complete.npz').is_file():
                continue
            if child_path.name.startswith('.') or child_path.name in {'run.json', 'sequence.json', 'program.json', 'arrays.npz'}:
                continue
            csv_candidate = child_path.suffix.lower() == '.csv' and not child_path.with_suffix('.npz').exists() and (
                child_path.name in {'anneal_positions.csv', 'intensity_map_points.csv'} or 'spectrum' in child_path.stem.lower())
            if child_path.is_dir() or child_path.suffix.lower() == '.npz' or csv_candidate:
                try:
                    child = self._path(child_path)
                    if child is not None:
                        node.children.append(child)
                except LoadCancelled:
                    raise
                except (AnalysisError, OSError) as error:
                    self.diagnostics.append(str(error))

    def _folder(self, path):
        for name in ('run.json', 'sequence.json', 'program.json'):
            if (path / name).exists():
                return self._document(path / name)
        preferred = ('intensity_map_complete.npz', 'intensity_map_checkpoint.npz', 'hyperspectral_cube.npz',
                     'spectral_cube.npz', 'cube.npz', 'spectrum.npz', 'spectrum_complete.npz')
        candidates = [path / name for name in preferred if (path / name).is_file()]
        if candidates:
            redundant = {'dark.npz', 'intensity_map_checkpoint.npz'} if candidates[0].name == 'intensity_map_complete.npz' else {'dark.npz'}
            siblings = [entry for entry in path.iterdir() if not entry.name.startswith('.') and
                        (entry.is_dir() or (entry.suffix.lower() == '.npz' and entry.name not in redundant))]
            if len(siblings) == 1:
                node = self._npz(candidates[0])
                if node.kind == 'cube' and (path / 'dark.npz').is_file():
                    try:
                        calibration = self._npz(path / 'dark.npz')
                        if calibration.kind == 'calibration':
                            node.children.append(calibration)
                    except (AnalysisError, OSError) as error:
                        self.diagnostics.append(str(error))
                return node
        meta = {}
        for name in ('metadata.json', 'result.json'):
            if (path / name).exists():
                meta[name] = read_json(path / name)
        node = Dataset(path.name, 'group', path, metadata=meta, synthetic=is_synthetic(meta))
        self._append_folder_children(node, path)
        return node if node.children or meta else None

    def _csv(self, path):
        if path.with_suffix('.npz').exists():
            return self._npz(path.with_suffix('.npz'))
        with path.open(encoding='utf-8-sig', newline='') as handle:
            lines = handle.readlines()
        synthetic = any(line.lstrip().startswith('#') and 'SYNTHETIC' in line.upper() for line in lines)
        reader = csv.DictReader(line for line in lines if not line.lstrip().startswith('#'))
        names = reader.fieldnames or []
        rows = list(reader)
        # Bounded compatibility adapter for the supplied example CSV schema.
        aliases = {'x_v': 'x_voltage_v', 'y_v': 'y_voltage_v'}
        for name in names:
            match = re.fullmatch(r'ch(\d+)_(counts|cps)', name)
            if match:
                aliases[name] = f'channel_{match[1]}_{match[2]}'
        names = [aliases.get(name, name) for name in names]
        rows = [{aliases.get(key, key): value for key, value in row.items()} for row in rows]
        meta = self._metadata(path, {})
        meta.update(synthetic_data=synthetic or is_synthetic(meta), analysis_warning='CSV provenance is limited to saved sidecars and comments')
        try:
            if {'wavelength_nm', 'intensity'} <= set(names):
                data = {key: np.array([float(row[key]) for row in rows]) for key in ('wavelength_nm', 'intensity')}
                return self._numeric(data, path.stem, path, meta)
            if {'sequence', 'pass', 'x_voltage_v', 'y_voltage_v', 'elapsed_s'} <= set(names):
                data = {key: np.array([float(row[key]) for row in rows]) for key in names}
                return Dataset(path.stem, 'anneal', path, data, meta, synthetic=is_synthetic(meta)).validate()
            if {'x_index', 'y_index', 'x_voltage_v', 'y_voltage_v', 'complete'} <= set(names):
                if not rows:
                    raise AnalysisError('Map CSV has no rows')
                xs = sorted({int(row['x_index']) for row in rows})
                ys = sorted({int(row['y_index']) for row in rows})
                if xs != list(range(len(xs))) or ys != list(range(len(ys))) or len(xs) * len(ys) > 100_000_000:
                    raise AnalysisError('Map CSV indices must form a bounded zero-based grid')
                channels = [int(match[1]) for name in names if (match := re.fullmatch(r'channel_(\d+)_counts', name))]
                if not channels or not all(f'channel_{channel}_cps' in names for channel in channels):
                    raise AnalysisError('Map CSV lacks matching count/count-rate columns')
                shape = (len(ys), len(xs))
                data = {'x_values_v': np.full(len(xs), np.nan), 'y_values_v': np.full(len(ys), np.nan),
                    'channels': np.array(channels), 'counts': np.full((len(channels), *shape), -1, dtype=np.int64),
                    'count_rates_cps': np.full((len(channels), *shape), np.nan), 'completed_mask': np.zeros(shape, bool)}
                seen = set()
                for row in rows:
                    ix, iy = int(row['x_index']), int(row['y_index'])
                    if (iy, ix) in seen:
                        raise AnalysisError('Duplicate pixel in map CSV')
                    seen.add((iy, ix))
                    data['x_values_v'][ix] = float(row['x_voltage_v'])
                    data['y_values_v'][iy] = float(row['y_voltage_v'])
                    flag = row['complete'].lower()
                    if flag not in {'true', 'false', '1', '0'}:
                        raise AnalysisError('Invalid completion flag in map CSV')
                    data['completed_mask'][iy, ix] = flag in {'true', '1'}
                    for channel_index, channel in enumerate(channels):
                        data['counts'][channel_index, iy, ix] = int(row[f'channel_{channel}_counts'])
                        data['count_rates_cps'][channel_index, iy, ix] = float(row[f'channel_{channel}_cps'])
                return self._numeric(data, path.stem, path, meta)
        except (ValueError, KeyError, OverflowError) as error:
            raise AnalysisError(f'Invalid numerical CSV {path.name}: {error}') from error
        raise AnalysisError('Unsupported CSV columns. Use the native NPZ, a spectrum CSV, map-points CSV or anneal_positions.csv')


def fingerprint(path, cancel=None):
    """Hash the actual source file, not just its name, for recipe verification."""
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            if cancel is not None and cancel():
                raise LoadCancelled('Source verification cancelled')
            digest.update(chunk)
    return digest.hexdigest()
