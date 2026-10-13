#!/usr/bin/env python3
"""Select inputs; delegate installation, execution and logs to VSLAM-LAB."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

import yaml

from dataset_inputs import ROOT, experiment_inputs, dataset_at_root
from check_vio_inputs import camera_imu_window

sys.path.insert(0, str(ROOT / 'external/VSLAM-LAB'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='Single-sequence experiment selection')
    parser.add_argument('--method', default='orbslam3', help='VSLAM-LAB catalog module')
    parser.add_argument('--mode', default='stereo-vi')
    parser.add_argument('--verbose', type=int, default=0, help='Native verbosity; 0 runs without a viewer')
    parser.add_argument('--rgb-max', type=int, help='Native frame limit for a smoke run')
    args = parser.parse_args()
    from Baselines.get_baseline import get_baseline, list_available_baselines
    from vslamlab_utilities import (validate_experiment_yaml, update_experiment_csv_logs,
                                  check_experiment_state, run_exp, load_experiments)
    if args.method not in list_available_baselines():
        parser.error(f'Unknown catalog method {args.method!r}; use make methods')
    if args.rgb_max is not None and args.rgb_max < 100:
        parser.error('--rgb-max must be >= 100')
    _, _, _, pairs = experiment_inputs(args.config)
    if len(pairs) != 1:
        parser.error('Choose one sequence using CONFIG=...')
    dataset_name, sequence = pairs[0]
    dataset = dataset_at_root(dataset_name)
    if dataset.check_sequence_availability(sequence, verbose=False) != 'available':
        raise RuntimeError('Dataset is not prepared; run make prepare first')
    _, audit = camera_imu_window(dataset.sequence_path(sequence))
    baseline = get_baseline(args.method)
    if args.mode not in baseline.modes:
        parser.error(f'{args.method} supports modes: {baseline.modes}')
    name = f'{args.method}_{sequence}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}'
    inputs = Path(os.environ['VSLAMLAB_EVALUATION']) / name / 'inputs'
    inputs.mkdir(parents=True)
    selection = inputs / 'sequences.yaml'
    selection.write_text(yaml.safe_dump({dataset_name: [sequence]}))
    parameters = dict(baseline.default_parameters)
    parameters.update(mode=args.mode, verbose=args.verbose, rgb_idx=audit['framework_rgb_idx_inclusive'])
    if args.rgb_max is not None:
        parameters['rgb_max'] = args.rgb_max
    experiment = inputs / 'experiment.yaml'
    experiment.write_text(yaml.safe_dump({name: {'Config': str(selection), 'Module': args.method,
                                              'NumRuns': 1, 'Parameters': parameters}}))
    (inputs / 'input_audit.json').write_text(json.dumps(audit, indent=2))
    validate_experiment_yaml(experiment)
    # run_sequence ensures the method is installed. No interactive resource prompt.
    update_experiment_csv_logs(experiment)
    check_experiment_state(experiment)
    run_exp(experiment)
    from utilities import read_csv
    exp = load_experiments(experiment)[name]
    log = read_csv(exp.log_csv)
    print(f'Native experiment: {experiment}', flush=True)
    if not log['STATUS'].eq('completed').all() or not log['SUCCESS'].astype(str).str.lower().eq('true').all():
        raise RuntimeError(f'Native method failed; see {exp.log_csv}')


if __name__ == '__main__':
    main()
