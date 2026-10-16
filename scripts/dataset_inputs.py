"""Dataset selection and compact experiment configuration."""
from pathlib import Path
import re
import yaml
from config_paths import config_path

ROOT = Path(__file__).resolve().parents[1]


class NativeSettingsDumper(yaml.SafeDumper):
    """OpenCV requires flow sequences for native sensor-name arrays."""


NativeSettingsDumper.add_representer(
    list, lambda dumper, values: dumper.represent_sequence(
        'tag:yaml.org,2002:seq', values, flow_style=True))


def selection_pairs(selection):
    if not isinstance(selection, dict) or not selection:
        raise ValueError('Expected nonempty VSLAM-LAB dataset/sequence selection')
    pairs = []
    for dataset, sequences in selection.items():
        if not isinstance(dataset, str) or not isinstance(sequences, list) or not sequences:
            raise ValueError(f'{dataset}: expected a nonempty list of sequence names')
        if any(not isinstance(seq, str) or not seq for seq in sequences):
            raise ValueError(f'{dataset}: sequence names must be nonempty strings (quote numeric names)')
        pairs.extend((dataset, seq) for seq in sequences)
    if len(set(pairs)) != len(pairs):
        raise ValueError('Duplicate dataset/sequence selection')
    return pairs


def experiment_inputs(path=None):
    """Read a plain download selection or the Datasets in an experiment."""
    path = config_path(str(path or '${VIO_EXPERIMENT_CONFIG}'), ROOT)
    config = yaml.safe_load(path.read_text())
    settings = config if isinstance(config, dict) and 'Datasets' in config else {}
    selection = settings['Datasets'] if settings else config
    return path, path.stem, settings, selection_pairs(selection)


def load_comparison(path=None):
    path, name, settings, pairs = experiment_inputs(path)
    unknown = set(settings) - {'Datasets', 'Methods', 'NumRuns', 'Evaluation', 'Preparation'}
    if unknown:
        raise ValueError(f'Unknown experiment fields: {sorted(unknown)}')
    methods = settings.get('Methods')
    if not isinstance(methods, dict) or not methods:
        raise ValueError('Expected nonempty Methods mapping')
    if type(settings.get('NumRuns', 1)) is not int or settings.get('NumRuns', 1) < 1:
        raise ValueError('NumRuns must be a positive integer')
    if not isinstance(settings.get('Evaluation', {}), dict):
        raise ValueError('Evaluation must be a mapping')
    for variant, method in methods.items():
        if not isinstance(variant, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', variant):
            raise ValueError('Method variant names must contain only letters, digits, _ or -')
        if not isinstance(method, dict) or set(method) - {'Module', 'Parameters', 'Settings', 'Evaluation'}:
            raise ValueError(f'{variant}: expected Module, Parameters and optional Settings/Evaluation')
        if not isinstance(method.get('Module'), str):
            raise ValueError(f'{variant}: Module is required')
        for key in ('Parameters', 'Settings', 'Evaluation'):
            if not isinstance(method.get(key, {}), dict):
                raise ValueError(f'{variant}: {key} must be a mapping')
    return path, name, settings, pairs


def write_method_settings(baseline, overrides, destination):
    """Copy stock settings, replacing only explicitly specified top-level keys."""
    baseline.ensure_installed()
    if not baseline.download_vslamlab_settings():
        raise FileNotFoundError(f'Cannot obtain stock settings: {baseline.settings_yaml}')
    original = baseline.settings_yaml.read_text()
    if not overrides:
        destination.write_bytes(baseline.settings_yaml.read_bytes())
        return destination
    settings = yaml.safe_load(original)
    if not isinstance(settings, dict):
        raise ValueError(f'{baseline.settings_yaml}: expected a YAML mapping')
    settings.update(overrides)
    # Preserve the native YAML directive (e.g. OpenCV's %YAML 1.2).
    directive = original.splitlines()[0] if original.startswith('%YAML') else ''
    destination.write_text((directive + '\n---\n' if directive else '') +
                           yaml.dump(settings, Dumper=NativeSettingsDumper, sort_keys=False))
    return destination


def dataset_at_root(dataset_name, data_root=None):
    from Datasets.get_dataset import get_dataset
    dataset = get_dataset(dataset_name)
    if isinstance(dataset, str):
        raise ValueError(f'Unsupported dataset: {dataset_name}')
    root = config_path(str(data_root or '${VIO_DATA_DIR}'), ROOT)
    dataset.dataset_path = root / 'VSLAM-LAB-Benchmark' / dataset.dataset_folder
    return dataset
