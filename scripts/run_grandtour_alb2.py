#!/usr/bin/env python3
"""Feed one prepared standard-format recording to unmodified VSLAM-LAB APIs."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import yaml

from check_vio_inputs import camera_imu_window, csv_rows
from config_paths import config_path
from run_results import create_run_directory
from evaluate_result import validate_protocol

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'external/VSLAM-LAB'
sys.path.insert(0, str(LAB))
from Baselines.get_baseline import get_baseline
from Datasets.get_dataset import get_dataset
from Run.run_functions import create_calibration_exp_yaml, create_rgb_exp_csv
from vslamlab_utilities import Experiment


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def write_experiment_log(path, module, dataset, sequence, result):
    headers = ['method_name', 'dataset_name', 'sequence_name', 'exp_it', 'STATUS',
               'SUCCESS', 'TIME', 'RAM', 'SWAP', 'GPU', 'COMMENTS', 'EVALUATION']
    row = [module, dataset, sequence, 0, 'running' if result is None else 'finished',
           False if result is None else result['success'],
           0 if result is None else result['wall_time_s'],
           *[0 if result is None else result.get(key, 0) for key in ('ram', 'swap', 'gpu')],
           '' if result is None else result.get('comments', ''), 'none']
    with path.open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerow(row)


def main():
    action = sys.argv[1:]
    if action not in ([], ['audit']):
        raise ValueError('Only optional "audit" is accepted; configure the experiment in YAML')
    experiment_config = config_path('${VIO_EXPERIMENT_CONFIG}', ROOT)
    config = yaml.safe_load(experiment_config.read_text())
    if len(config) != 1:
        raise ValueError('This adapter supports one experiment')
    name, settings = next(iter(config.items()))
    evaluation_protocol = validate_protocol(settings['Evaluation'])
    sequences = yaml.safe_load((ROOT / settings['Config']).read_text())
    if len(sequences) != 1 or len(next(iter(sequences.values()))) != 1:
        raise ValueError('This adapter supports one dataset/sequence')
    dataset_name, names = next(iter(sequences.items()))
    seq = str(names[0])
    storage_path = ROOT / settings['StorageConfig']
    storage = yaml.safe_load(storage_path.read_text())
    data_root = config_path(storage['data_dir'], storage_path.parent)
    dataset = get_dataset(dataset_name)
    # Instance-local paths: no changes to path_constants or framework source files.
    dataset.dataset_path = data_root / 'VSLAM-LAB-Benchmark' / dataset.dataset_folder
    folder = dataset.sequence_path(seq)
    selected, audit = camera_imu_window(folder)
    results_root = config_path(settings['ResultsDir'], ROOT)
    if action == ['audit']:
        print(json.dumps(audit, indent=2))
        return
    if settings.get('NumRuns', 1) != 1:
        raise ValueError('This adapter supports NumRuns: 1')
    baseline = get_baseline(settings['Module'])
    baseline.settings_yaml = ROOT / settings['MethodSettings']
    os.chdir(LAB)
    baseline.ensure_installed()
    report = create_run_directory(results_root)
    print('Results:', report, flush=True)
    exp = Experiment(name, settings)
    exp.folder = report / 'VSLAM-LAB-Evaluation' / name
    exp.log_csv = exp.folder / 'vslamlab_exp_log.csv'
    exp.config_yaml = ROOT / settings['Config']
    exp.parameters = dict(settings['Parameters'], rgb_idx=audit['framework_rgb_idx_inclusive'])
    exp_folder = exp.folder / dataset.dataset_folder / seq
    exp_folder.mkdir(parents=True)
    write_json(report / 'input_audit.json', audit)
    create_calibration_exp_yaml(exp, dataset, seq, baseline.default_parameters)
    create_rgb_exp_csv(exp, dataset, seq, baseline.default_parameters)
    if csv_rows(exp_folder / 'rgb_exp.csv') != selected:
        raise RuntimeError('Framework camera selection differs from the audited interval')
    command = baseline.build_execute_command(0, exp, dataset, seq)
    exit_file = exp_folder / 'exit_code.txt'
    measured = '/usr/bin/time -v -o ' + shlex.quote(str(exp_folder / 'process_timing.txt')) + ' ' + command
    measured += '; code=$?; printf "%s\\n" "$code" > ' + shlex.quote(str(exit_file)) + '; exit "$code"'
    write_json(report / 'run_provenance.json', {
        'framework_revision': subprocess.check_output(['git', '-C', str(LAB), 'rev-parse', 'HEAD'], text=True).strip(),
        'command': command, 'experiment_config': str(experiment_config),
        'settings_path': str(baseline.settings_yaml),
        'settings_sha256': hashlib.sha256(baseline.settings_yaml.read_bytes()).hexdigest(),
        'experiment_config_sha256': hashlib.sha256(experiment_config.read_bytes()).hexdigest(),
        'calibration_sha256': hashlib.sha256((exp_folder / 'calibration_exp.yaml').read_bytes()).hexdigest(),
        'input_directory': str(folder), 'output_directory': str(exp_folder),
        'run_directory': str(report), 'results_root': str(results_root),
        'parameters': exp.parameters, 'input_audit': audit,
        'evaluation_protocol': evaluation_protocol,
        'module': settings['Module'], 'dataset_name': dataset_name, 'sequence_name': seq,
        'reference_used_by_algorithm': False,
    })
    write_experiment_log(exp.log_csv, settings['Module'], dataset_name, seq, None)
    print('Command:', command, flush=True)
    started = time.monotonic()
    result = baseline.execute(measured, 0, exp_folder, timeout_seconds=900)
    result['wall_time_s'] = time.monotonic() - started
    result['exit_code'] = int(exit_file.read_text()) if exit_file.exists() else None
    result['success'] = bool(result['success'] and result['exit_code'] == 0)
    write_json(report / 'execution.json', result)
    write_experiment_log(exp.log_csv, settings['Module'], dataset_name, seq, result)
    print(json.dumps(result, indent=2), flush=True)
    if not result['success']:
        raise RuntimeError('Run failed; see execution.json and system_output_00000.txt')


if __name__ == '__main__':
    main()
