#!/usr/bin/env python3
"""Evaluate a saved native comparison or a legacy research run via VSLAM-LAB."""
import argparse
import os
from pathlib import Path
import sys
import yaml
from config_paths import config_path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'external/VSLAM-LAB'))
from Evaluate.protocol import calculate, evaluate_run, validate_protocol
from Evaluate.artifacts import select_run


def latest_comparison(root):
    candidates = []
    for path in root.glob('comparison_*/experiment.yaml'):
        recipes = yaml.safe_load(path.read_text())
        if any((path.parent / name / 'vslamlab_exp_log.csv').exists() for name in recipes):
            candidates.append(path)
    return max(candidates, key=lambda p: p.stat().st_mtime_ns) if candidates else None


def current_evaluation_overrides(recipes, config=None):
    """Use current metric settings, retaining the saved trajectory's frame semantics."""
    from dataset_inputs import load_comparison
    path, _, settings, _ = load_comparison(config)
    overrides = {}
    for name, recipe in recipes.items():
        variant = name.rsplit('_', 1)[0]
        if variant not in settings['Methods']:
            raise ValueError(f'{name}: variant absent in {path}; choose matching CONFIG or --saved-protocol')
        method = settings['Methods'][variant]
        if method['Module'] != recipe['Module']:
            raise ValueError(f'{name}: method differs from the saved run; use --saved-protocol')
        current = dict(settings.get('Evaluation', {}), **method.get('Evaluation', {}))
        validate_protocol(current)
        overrides[name] = {k:v for k,v in current.items() if k not in ('estimate_frame', 'camera')}
    return path, overrides


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', help='Saved comparison directory or legacy research run')
    parser.add_argument('--experiment', type=Path, help='Exact saved native experiment YAML')
    parser.add_argument('--config', help='Current experiment config for native metric settings')
    parser.add_argument('--saved-protocol', action='store_true', help='Reuse saved evaluation settings')
    parser.add_argument('--protocol', type=Path, help='Explicit evaluation protocol override')
    parser.add_argument('--gt', type=Path, help='GT override for one legacy research run')
    args = parser.parse_args()
    if args.run_dir and args.experiment:
        parser.error('Choose --run-dir or --experiment')
    run = Path(args.run_dir).expanduser().resolve() if args.run_dir else None
    experiment = args.experiment.expanduser().resolve() if args.experiment else None
    if run and (run / 'run_provenance.json').is_file():
        print('Evaluation:', evaluate_run(run, args.protocol, args.gt))
        return
    if run:
        experiment = run / 'experiment.yaml'
    if not experiment:
        experiment = latest_comparison(config_path('${VIO_RESULTS_DIR}/VSLAM-LAB-Evaluation', ROOT))
    if not experiment:
        run = select_run(None, config_path('${VIO_RESULTS_DIR}', ROOT))
        print('Evaluation:', evaluate_run(run, args.protocol, args.gt))
        return
    if args.gt:
        parser.error('--gt is supported only for a single legacy research run')
    # Derive the saved native result root, independent of the current machine defaults.
    os.environ['VSLAMLAB_EVALUATION'] = str(experiment.parent)
    from vslamlab_utilities import evaluate_exp
    recipes = yaml.safe_load(experiment.read_text())
    override = yaml.safe_load(args.protocol.read_text()) if args.protocol else None
    current = None
    if not args.saved_protocol:
        path, current = current_evaluation_overrides(recipes, args.config)
        print(f'Evaluation config: {path}', flush=True)
    print(f'Saved run: {experiment.parent}', flush=True)
    for name, recipe in recipes.items():
        effective = validate_protocol({**recipe.get('Evaluation', {}),
                                       **(current or {}).get(name, {}), **(override or {})})
        print(f"{name}: align={effective['align']}, dt={effective['max_time_difference_s']:g}s, "
              f"frame={effective['estimate_frame']}/{effective['camera']}", flush=True)
    if override is None and not all('Evaluation' in recipe for recipe in recipes.values()):
        raise ValueError('No saved protocol; pass --protocol explicitly')
    evaluate_exp(experiment, protocol_override=override, evaluation_overrides=current)
    print('Comparison:', experiment.parent / 'comparison.csv')


if __name__ == '__main__':
    main()
