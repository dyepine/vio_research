#!/usr/bin/env python3
"""Feed one prepared standard-format recording to unmodified VSLAM-LAB APIs."""
import argparse
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
from dataset_inputs import load_comparison, dataset_at_root, write_method_settings
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
    parser = argparse.ArgumentParser()
    parser.add_argument('action', nargs='?', choices=['audit'])
    parser.add_argument('--config', help='Experiment YAML; defaults to VIO_EXPERIMENT_CONFIG')
    parser.add_argument('--rgb-max', type=int, help='Override frame limit for a research smoke run')
    parser.add_argument('--variant', help='Variant name from Methods')
    parser.add_argument('--dataset', help='Dataset from Datasets')
    parser.add_argument('--sequence', help='Sequence from Datasets')
    args = parser.parse_args()
    experiment_config, name, comparison, pairs = load_comparison(args.config)
    if (args.dataset is None) != (args.sequence is None):
        parser.error('Specify both --dataset and --sequence')
    if args.dataset is not None:
        selected_pair = (args.dataset, args.sequence)
        if selected_pair not in pairs:
            parser.error('Requested sequence is not in Datasets')
        pairs = [selected_pair]
    methods = comparison['Methods']
    if args.variant is None and len(methods) != 1:
        parser.error('Choose one research variant with VARIANT=...')
    variant = args.variant or next(iter(methods))
    if variant not in methods:
        parser.error(f'Unknown variant {variant!r}')
    settings = dict(methods[variant], Evaluation=dict(comparison.get('Evaluation', {}), **methods[variant].get('Evaluation', {})),
                    NumRuns=comparison.get('NumRuns', 1), ResultsDir='${VIO_RESULTS_DIR}')
    if args.rgb_max is not None:
        if args.rgb_max < 100:
            parser.error('--rgb-max must be >= 100')
        settings['Parameters'] = dict(settings.get('Parameters', {}), rgb_max=args.rgb_max)
    name = f'{name}_{variant}'
    evaluation_protocol = validate_protocol(settings['Evaluation'])
    if len(pairs) != 1:
        raise ValueError('Choose one research sequence with DATASET=... SEQUENCE=...')
    dataset_name, seq = pairs[0]
    dataset = dataset_at_root(dataset_name)
    folder = dataset.sequence_path(seq)
    selected, audit = camera_imu_window(folder)
    results_root = config_path(settings['ResultsDir'], ROOT)
    if args.action == 'audit':
        print(json.dumps(audit, indent=2))
        return
    if settings.get('NumRuns', 1) != 1:
        raise ValueError('This adapter supports NumRuns: 1')
    baseline = get_baseline(settings['Module'])
    if isinstance(baseline, str):
        raise ValueError(f'Unknown catalog method {settings["Module"]!r}')
    os.chdir(LAB)
    baseline.ensure_installed()
    report = create_run_directory(results_root)
    print('Results:', report, flush=True)
    (report / 'comparison.yaml').write_bytes(experiment_config.read_bytes())
    baseline.settings_yaml = write_method_settings(
        baseline, settings.get('Settings', {}), report / 'method_settings.yaml')
    exp = Experiment(name, dict(settings, Config=str(report / 'sequences.yaml'),
                                Parameters=settings.get('Parameters', {})))
    exp.folder = report / 'VSLAM-LAB-Evaluation' / name
    exp.log_csv = exp.folder / 'vslamlab_exp_log.csv'
    exp.config_yaml = report / 'sequences.yaml'
    exp.config_yaml.write_text(yaml.safe_dump({dataset_name: [seq]}))
    exp.parameters = dict(baseline.default_parameters, **settings.get('Parameters', {}))
    if exp.parameters.get('mode') not in baseline.modes:
        raise ValueError(f'Supported modes: {baseline.modes}')
    exp.parameters['verbose'] = settings.get('Parameters', {}).get('verbose', 0)
    exp.parameters['rgb_idx'] = audit['framework_rgb_idx_inclusive']
    exp_folder = exp.folder / dataset.dataset_folder / seq
    exp_folder.mkdir(parents=True)
    write_json(report / 'input_audit.json', audit)
    create_calibration_exp_yaml(exp, dataset, seq, baseline.default_parameters)
    create_rgb_exp_csv(exp, dataset, seq, baseline.default_parameters)
    actual_frames = csv_rows(exp_folder / 'rgb_exp.csv')
    requested_max = exp.parameters.get('rgb_max')
    if requested_max is not None:
        if isinstance(requested_max, bool) or not isinstance(requested_max, int) or requested_max < 100:
            raise ValueError('Explicit rgb_max must be an integer >= 100 for a VIO smoke run')
        expected_frames = selected[:requested_max]
    else:
        expected_frames = selected
    if actual_frames != expected_frames:
        raise RuntimeError('Framework camera selection differs from the audited interval/cap')
    audit['images_used_by_framework'] = len(actual_frames)
    audit['duration_used_by_framework_s'] = (int(actual_frames[-1][0]) - int(actual_frames[0][0])) / 1e9
    write_json(report / 'input_audit.json', audit)
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
        'preparation_report': json.loads((folder / 'preparation_report.json').read_text()) if (folder / 'preparation_report.json').exists() else None,
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
