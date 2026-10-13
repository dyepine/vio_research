#!/usr/bin/env python3
"""Expand a comparison and delegate method execution to VSLAM-LAB."""
import argparse
from datetime import datetime, timezone
import json
import os
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
        _, audits[(dataset_name, sequence)] = camera_imu_window(dataset.sequence_path(sequence))
    native = {}
    for variant, method in settings['Methods'].items():
        protocol = dict(settings.get('Evaluation', {}), **method.get('Evaluation', {}))
        if 'estimate_frame' not in protocol:
            raise ValueError(f'{variant}: declare Evaluation.estimate_frame (camera or body)')
        protocol = validate_protocol(protocol)
        baseline = get_baseline(method['Module'])
        if isinstance(baseline, str):
            raise ValueError(f'Unknown catalog method {method["Module"]!r}; use make methods')
        parameters = dict(baseline.default_parameters, **method.get('Parameters', {}))
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
            name = f'{inputs.parent.name}_{variant}_{index}'
            selection = inputs / f'sequences_{index}.yaml'
            selection.write_text(yaml.safe_dump({dataset_name: [sequence]}))
            audit = audits[(dataset_name, sequence)]
            recipe = {'Config': str(selection), 'Module': method['Module'],
                      'NumRuns': settings.get('NumRuns', 1),
                      'Parameters': dict(parameters, rgb_idx=audit['framework_rgb_idx_inclusive']),
                      'Evaluation': dict(protocol)}
            recipe['MethodSettings'] = str(settings_path)
            native[name] = recipe
    experiment = inputs / 'experiment.yaml'
    experiment.write_text(yaml.safe_dump(native, sort_keys=False))
    (inputs / 'evaluation.yaml').write_text(yaml.safe_dump(settings.get('Evaluation', {})))
    (inputs / 'input_audits.json').write_text(json.dumps(
        {f'{dataset}/{seq}': audit for (dataset, seq), audit in audits.items()}, indent=2))
    return experiment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='Comparison YAML; defaults to VIO_EXPERIMENT_CONFIG')
    parser.add_argument('--rgb-max', type=int, help='Override frame limit for every method')
    parser.add_argument('--plan', action='store_true', help='Generate native configs without running methods')
    args = parser.parse_args()
    from Baselines.get_baseline import get_baseline
    from vslamlab_utilities import (validate_experiment_yaml, update_experiment_csv_logs,
                                  check_experiment_state, run_exp, load_experiments)
    name = f'comparison_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}'
    experiment = materialize(args.config, Path(os.environ['VSLAMLAB_EVALUATION']) / name / 'inputs',
                             get_baseline, args.rgb_max)
    validate_experiment_yaml(experiment)
    print(f'Native experiment: {experiment}', flush=True)
    if args.plan:
        return
    update_experiment_csv_logs(experiment)
    check_experiment_state(experiment)
    run_exp(experiment)
    from utilities import read_csv
    failed = []
    for exp in load_experiments(experiment).values():
        log = read_csv(exp.log_csv)
        if not log['STATUS'].eq('completed').all() or not log['SUCCESS'].astype(str).str.lower().eq('true').all():
            failed.append(str(exp.log_csv))
    if failed:
        raise RuntimeError(f'Native methods failed; see {failed}')


if __name__ == '__main__':
    main()
