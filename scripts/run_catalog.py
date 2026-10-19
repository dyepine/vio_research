#!/usr/bin/env python3
"""Expand a comparison and delegate method execution to VSLAM-LAB."""
import argparse
import csv
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
import os
import multiprocessing
from pathlib import Path
import sys
import uuid
import yaml
from dataset_inputs import ROOT, load_comparison, dataset_at_root, write_method_settings
from check_vio_inputs import camera_imu_window

sys.path.insert(0, str(ROOT / 'external/VSLAM-LAB'))


def materialize(config, inputs, get_baseline, rgb_max=None):
    """Freeze effective inputs; one native experiment per variant and sequence."""
    from Evaluate.protocol import validate_protocol
    path, _, settings, pairs = load_comparison(config)
    inputs.mkdir(parents=True)
    (inputs / 'comparison.yaml').write_bytes(path.read_bytes())
    audits = {}
    for dataset_name, sequence in pairs:
        dataset = dataset_at_root(dataset_name)
        if dataset.check_sequence_availability(sequence, verbose=False) != 'available':
            raise RuntimeError(f'{dataset_name}/{sequence} is not prepared; run make prepare first')
        start = settings.get('FrameStart', {}).get(dataset_name, {}).get(sequence, 0)
        folder = dataset.sequence_path(sequence)
        _, audits[(dataset_name, sequence)] = (camera_imu_window(folder, start_frame=start)
                                              if start else camera_imu_window(folder))
    native = {}
    for variant, method in settings['Methods'].items():
        protocol = dict(settings.get('Evaluation', {}), **method.get('Evaluation', {}))
        if 'estimate_frame' not in protocol:
            raise ValueError(f'{variant}: declare Evaluation.estimate_frame (camera or body)')
        protocol = validate_protocol(protocol)
        baseline = get_baseline(method['Module'])
        if isinstance(baseline, str):
            raise ValueError(f'Unknown catalog method {method["Module"]!r}; inspect the VSLAM-LAB baseline catalog')
        parameters = dict(baseline.default_parameters, **method.get('Parameters', {}))
        noise_profiles = parameters.pop('imu_noise_by_dataset', None)
        if noise_profiles is not None:
            if not isinstance(noise_profiles, dict) or any(dataset not in noise_profiles for dataset, _ in pairs):
                raise ValueError(f'{variant}: imu_noise_by_dataset must cover every selected dataset')
            if any(not isinstance(profile, dict) or not profile for profile in noise_profiles.values()):
                raise ValueError(f'{variant}: IMU noise profiles must be nonempty mappings')
        # Catalog default verbosity may open a viewer; unattended runs default to 0.
        if 'verbose' not in method.get('Parameters', {}):
            parameters['verbose'] = 0
        if parameters.get('mode') not in baseline.modes:
            raise ValueError(f'{variant}: supported modes are {baseline.modes}')
        if 'rgb_idx' in parameters:
            raise ValueError('rgb_idx is determined by the audited camera/IMU interval')
        cap = rgb_max if rgb_max is not None else parameters.get('rgb_max')
        if cap is not None:
            if type(cap) is not int or cap < 100:
                raise ValueError('rgb_max must be an integer >= 100')
            parameters['rgb_max'] = cap
        overrides = method.get('Settings', {})
        settings_path = write_method_settings(baseline, overrides, inputs / f'{variant}_settings.yaml')
        for index, (dataset_name, sequence) in enumerate(pairs):
            name = f'{variant}_{index}'
            selection = inputs / f'sequences_{index}.yaml'
            selection.write_text(yaml.safe_dump({dataset_name: [sequence]}))
            audit = audits[(dataset_name, sequence)]
            recipe = {'Config': str(selection), 'Module': method['Module'],
                      'NumRuns': settings.get('NumRuns', 1),
                      'Parameters': dict(parameters, rgb_idx=audit['framework_rgb_idx_inclusive']),
                      'Evaluation': dict(protocol)}
            if noise_profiles is not None:
                recipe['Parameters']['imu_noise'] = dict(noise_profiles[dataset_name])
            recipe['MethodSettings'] = str(settings_path)
            native[name] = recipe
    experiment = inputs.parent / 'experiment.yaml'
    experiment.write_text(yaml.safe_dump(native, sort_keys=False))
    (inputs / 'evaluation.yaml').write_text(yaml.safe_dump(settings.get('Evaluation', {})))
    (inputs / 'input_audits.json').write_text(json.dumps(
        {f'{dataset}/{seq}': audit for (dataset, seq), audit in audits.items()}, indent=2))
    return experiment


def partition_methods(recipes):
    """Keep each variant's sequences/repeats together; never share experiment logs."""
    groups = {}
    for name, recipe in recipes.items():
        variant = name.rsplit('_', 1)[0]
        groups.setdefault(variant, {})[name] = recipe
    return groups


def _run_native_worker(experiment):
    from vslamlab_utilities import run_exp
    path = Path(experiment)
    timing = {'pid': os.getpid(), 'start_utc': datetime.now(timezone.utc).isoformat()}
    timing_path = path.with_suffix('.execution.json')
    timing_path.write_text(json.dumps(timing, indent=2))
    try:
        run_exp(path)
    finally:
        timing['end_utc'] = datetime.now(timezone.utc).isoformat()
        timing_path.write_text(json.dumps(timing, indent=2))


def parallel_context():
    # A single-threaded forkserver imports the framework once. Workers share its
    # read-only pages instead of each allocating another ~200 MB with spawn.
    if 'forkserver' in multiprocessing.get_all_start_methods():
        multiprocessing.set_forkserver_preload(['__main__', 'vslamlab_utilities'])
        return multiprocessing.get_context('forkserver')
    return multiprocessing.get_context('spawn')


def prepare_native(config, inputs, rgb_max, initialize):
    from Baselines.get_baseline import get_baseline
    from vslamlab_utilities import (validate_experiment_yaml, update_experiment_csv_logs,
                                   check_experiment_state)
    experiment = materialize(config, Path(inputs), get_baseline, rgb_max)
    validate_experiment_yaml(experiment)
    print(f'Native experiment: {experiment}', flush=True)
    if initialize:
        update_experiment_csv_logs(experiment)
        check_experiment_state(experiment)
    return str(experiment)


def run_methods(experiment, jobs, context=None):
    if jobs == 1:
        _run_native_worker(experiment)
        return
    recipes = yaml.safe_load(experiment.read_text())
    workers = experiment.parent / 'inputs' / 'workers'
    workers.mkdir()
    paths = []
    for variant, group in partition_methods(recipes).items():
        path = workers / f'{variant}.yaml'
        path.write_text(yaml.safe_dump(group, sort_keys=False))
        paths.append(path)
    # Framework globals and CSV temp files are isolated by process and experiment.
    # Methods run concurrently; sequences of one method remain sequential.
    with ProcessPoolExecutor(max_workers=min(jobs, len(paths)),
                             mp_context=context or parallel_context()) as pool:
        futures = [pool.submit(_run_native_worker, str(path)) for path in paths]
        for future in futures:
            future.result()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='Comparison YAML; defaults to VIO_EXPERIMENT_CONFIG')
    parser.add_argument('--rgb-max', type=int, help='Override frame limit for every method')
    parser.add_argument('--plan', action='store_true', help='Generate native configs without running methods')
    parser.add_argument('--jobs', type=int, default=1, help='Concurrent method variants (sequences stay sequential)')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    name = f'comparison_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}'
    run = Path(os.environ['VSLAMLAB_EVALUATION']) / name
    # Framework modules read this supported setting at import time.
    os.environ['VSLAMLAB_EVALUATION'] = str(run)
    context = parallel_context() if args.jobs > 1 else None
    preparation = (args.config, str(run / 'inputs'), args.rgb_max, not args.plan)
    if context is None:
        experiment = Path(prepare_native(*preparation))
    else:
        # Keep the coordinator lightweight. Importing the framework here would
        # retain an unnecessary private copy for the whole parallel run.
        with ProcessPoolExecutor(max_workers=1, mp_context=context) as pool:
            experiment = Path(pool.submit(prepare_native, *preparation).result())
    if args.plan:
        return
    (run / 'execution.json').write_text(json.dumps({
        'concurrent_method_workers': args.jobs,
        'start_method': context.get_start_method() if context else 'serial',
        'timing_comparable_to_isolated_runs': args.jobs == 1}, indent=2))
    run_methods(experiment, args.jobs, context)
    failed = []
    for name in yaml.safe_load(experiment.read_text()):
        log_path = run / name / 'vslamlab_exp_log.csv'
        rows = []
        if log_path.exists():
            with log_path.open() as stream:
                rows = list(csv.DictReader(stream))
        if not rows or any(row['STATUS'] != 'completed' or row['SUCCESS'].lower() != 'true' for row in rows):
            failed.append(str(log_path))
    if failed:
        raise RuntimeError(f'Native methods failed; see {failed}')


if __name__ == '__main__':
    main()
