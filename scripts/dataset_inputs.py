"""Shared experiment selection and instance-local VSLAM-LAB dataset paths."""
import os
from pathlib import Path
import yaml
from config_paths import config_path

ROOT = Path(__file__).resolve().parents[1]


def experiment_inputs(path=None):
    path = config_path(str(path or '${VIO_EXPERIMENT_CONFIG}'), ROOT)
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or len(config) != 1:
        raise ValueError('Expected one experiment in YAML')
    name, settings = next(iter(config.items()))
    sequence_config = config_path(settings['Config'], ROOT)
    selection = yaml.safe_load(sequence_config.read_text())
    if not isinstance(selection, dict) or not selection:
        raise ValueError('Expected nonempty VSLAM-LAB dataset/sequence selection')
    pairs = []
    for dataset, sequences in selection.items():
        if not isinstance(sequences, list) or not sequences:
            raise ValueError(f'{dataset}: expected a nonempty list of sequence names')
        pairs.extend((dataset, str(seq)) for seq in sequences)
    if len(set(pairs)) != len(pairs):
        raise ValueError('Duplicate dataset/sequence selection')
    return path, name, settings, pairs


def dataset_at_root(dataset_name, data_root=None):
    from Datasets.get_dataset import get_dataset
    dataset = get_dataset(dataset_name)
    if isinstance(dataset, str):
        raise ValueError(f'Unsupported dataset: {dataset_name}')
    root = config_path(str(data_root or '${VIO_DATA_DIR}'), ROOT)
    dataset.dataset_path = root / 'VSLAM-LAB-Benchmark' / dataset.dataset_folder
    return dataset
