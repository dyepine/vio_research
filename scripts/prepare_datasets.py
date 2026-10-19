#!/usr/bin/env python3
"""Prepare selected recordings using the registered VSLAM-LAB dataset lifecycle."""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import os
import math
import numpy as np
import yaml

from dataset_inputs import ROOT, experiment_inputs, dataset_at_root
from check_vio_inputs import camera_imu_window, csv_rows
from config_paths import config_path

LAB = ROOT / 'external/VSLAM-LAB'
sys.path.insert(0, str(LAB))
GB = 10**9


def validate_dataset(dataset, sequence):
    folder = dataset.sequence_path(sequence)
    if not dataset.check_sequence_integrity(sequence, verbose=True):
        raise ValueError(f'Incomplete standard layout: {folder}; preserve/move the partial folder before reimporting')
    _, audit = camera_imu_window(folder)
    calibration = yaml.safe_load((folder / 'calibration.yaml').read_text())
    for i in (0, 1):
        camera = next(c for c in calibration['cameras'] if c['cam_name'] == f'rgb_{i}')
        from PIL import Image
        for row in csv_rows(folder / 'rgb.csv'):
            image_path = folder / row[2 * i + 1]
            if not image_path.is_file():
                raise ValueError(f'Missing image: {image_path}')
            with Image.open(image_path) as image:
                if list(image.size) != camera['image_dimension']:
                    raise ValueError(f'Image/calibration dimensions differ: {image_path}')
        T = np.array(camera['T_BS']).reshape(4, 4)
        if (not np.isfinite(T).all() or not np.allclose(T[3], [0, 0, 0, 1]) or
                not np.allclose(T[:3, :3].T @ T[:3, :3], np.eye(3), atol=1e-5) or
                not np.isclose(np.linalg.det(T[:3, :3]), 1, atol=1e-5)):
            raise ValueError('Invalid camera extrinsics')
    poses = csv_rows(folder / 'groundtruth.csv')
    ts = np.array([int(r[0]) for r in poses], dtype=np.int64)
    values = np.array([[float(v) for v in r[1:]] for r in poses])
    if (len(poses) < 3 or np.any(np.diff(ts) <= 0) or not np.isfinite(values).all() or
            np.any(np.abs(np.linalg.norm(values[:, 3:], axis=1) - 1) > .005)):
        raise ValueError('Invalid 6DoF reference')
    if ts[-1] < int(csv_rows(folder / 'rgb.csv')[0][0]) or ts[0] > int(csv_rows(folder / 'rgb.csv')[-1][0]):
        raise ValueError('GT and camera intervals do not overlap')
    if dataset.dataset_name == 'grandtour-alphasense':
        # Require IE source for our selected outdoor recordings, never a prism-only fallback.
        mission = dataset._mission_path(sequence)
        if not (mission / 'data/cpt7_ie_tc_odometry.tar').is_file() and not (mission / 'data/cpt7_ie_tc_odometry').is_dir():
            raise ValueError('GNSS/INS source not retained; cannot accept provenance of this reference')
        audit['groundtruth_source'] = 'cpt7_ie_tc_odometry; body frame alphasense_imu'
    elif dataset.dataset_name == 'fomo':
        audit['groundtruth_source'] = 'PPK GNSS fusion; position only, identity quaternion placeholders'
    else:
        audit['groundtruth_source'] = json.loads((folder / 'reference_metadata.json').read_text())
    audit['groundtruth_count'] = len(poses)
    return audit


def preparation_estimate(dataset, sequence):
    if dataset.check_sequence_availability(sequence, verbose=False) == 'available':
        return 0
    if dataset.dataset_name == 'geode-gamma':
        missing = sum(asset['size'] for asset in dataset.assets_for(sequence).values()
                      if not (dataset._raw() / asset['name']).is_file()
                      or (dataset._raw() / asset['name']).stat().st_size != asset['size'])
        # Full-resolution grayscale PNGs, both cameras, 500 s at 10 Hz plus
        # overhead. Retain source bag; no intermediate native/color extraction.
        image_bound = dataset.cfg.get('image_count_bounds', {}).get(sequence, 5000)
        return int(missing + image_bound * 2 * 1224 * 1024 * 1.1 + 100_000_000)
    if dataset.dataset_name == 'botanicgarden':
        # Upper bound based on published 10 Hz image counts/durations, grayscale PNG,
        # including conservative overhead. Both retained source and output are included.
        source = Path(os.environ.get('BOTANICGARDEN_SOURCE_DIR', str(dataset._raw())))
        asset = dataset.cfg['bags'][sequence]
        bag = source / f'{sequence}_VLIO.bag'
        missing = 0 if bag.exists() and bag.stat().st_size == asset['size'] else asset['size']
        image_bound = math.ceil(dataset.cfg['durations_s'][sequence] * dataset.rgb_hz * 1.2)
        return missing + image_bound * 2 * 960 * 600 * 1.2 + 100_000_000
    if dataset.dataset_name == 'grandtour-alphasense':
        from huggingface_hub import HfApi
        from Datasets.dataset_files.dataset_grandtour import OPTIONAL_TOPICS
        mission = dataset._mission(sequence)
        wanted = {f'{mission}/data/{t}.tar' for t in dataset._data_topics() + sorted(OPTIONAL_TOPICS)}
        wanted |= {f'{mission}/images/{tag}.tar' for tag, _ in dataset.CAMERAS}
        size = sum(e.size for e in HfApi().list_repo_tree(dataset.hf_repo_id, repo_type='dataset',
                   path_in_repo=mission, recursive=True) if getattr(e, 'path', '') in wanted)
        if not size:
            raise ValueError('Could not estimate published GrandTour inputs')
        # Retained tar + native extraction + resized outputs; source compression varies.
        # Explicit conservative planning factor, not a guaranteed physical upper bound.
        return size * 12 + 100_000_000
    if dataset.dataset_name == 'fomo':
        from Datasets.dataset_files.dataset_fomo import RAW_FILES, RAW_PREFIXES, CAMERAS
        prefix = dataset._recording_prefix(sequence)
        objects = [item for item in dataset._s3_list(prefix, recursive=False)
                   if item[0][len(prefix):] in RAW_FILES]
        for sub in RAW_PREFIXES:
            objects.extend(dataset._s3_list(prefix + sub + '/'))
        missing = sum(size for key, size in objects
                      if not (dataset._raw_path(sequence) / key[len(prefix):]).is_file()
                      or (dataset._raw_path(sequence) / key[len(prefix):]).stat().st_size != size)
        images = sum(key.startswith(tuple(prefix + cam + '/' for cam in CAMERAS))
                     and key.endswith('.png') for key, _ in objects)
        # Retained originals plus RGB outputs; allow lossless PNG overhead above raw RGB.
        if dataset.target_resolution is None:
            processed = sum(size for key, size in objects
                            if key.startswith(tuple(prefix + cam + '/' for cam in CAMERAS)))
        else:
            processed = images * np.prod(dataset.target_resolution) * 3 * 1.05
        return int(missing + processed + 100_000_000)
    raise ValueError(f'No storage estimate for supported migration target {dataset.dataset_name}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'prepare', 'validate'])
    parser.add_argument('--config', help='Dataset selection YAML or experiment with Datasets')
    args = parser.parse_args()
    config, _, settings, pairs = experiment_inputs(args.config)
    data_root = config_path('${VIO_DATA_DIR}', ROOT)
    data_root.mkdir(parents=True, exist_ok=True)
    with (data_root / '.prepare.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as ex:
            raise RuntimeError('Another preparation is running in this data directory') from ex
        datasets = [(dataset_at_root(name), seq) for name, seq in pairs]
        for dataset, seq in datasets:
            if not dataset.contains_sequence(seq):
                raise ValueError(f'Unknown sequence {dataset.dataset_name}/{seq}')
        if args.action != 'validate':
            prep = settings.get('Preparation', {})
            for key, default in [('reserve_gb', 15), ('max_data_gb', 30)]:
                value = prep.get(key, default)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
                    raise ValueError(f'Preparation.{key} must be a finite nonnegative number')
            reserve = float(prep.get('reserve_gb', 15)) * GB
            limit = float(prep.get('max_data_gb', 30)) * GB
            estimate = sum(preparation_estimate(ds, seq) for ds, seq in datasets)
            used = sum(p.stat().st_size for p in data_root.rglob('*') if p.is_file())
            free = shutil.disk_usage(data_root).free
            report = {'experiment_config': str(config), 'selection': pairs, 'estimated_additional_gb': estimate / GB,
                      'existing_data_gb': used / GB, 'free_gb': free / GB, 'reserve_gb': reserve / GB,
                      'max_data_gb': limit / GB, 'estimate_caveat': 'Conservative heuristic; does not reserve disk space'}
            print(json.dumps(report, indent=2), flush=True)
            if args.action == 'plan':
                return
            if free < estimate + reserve or used + estimate > limit:
                raise RuntimeError('Storage preflight failed; use a larger stable disk or change Preparation limits')
        os.chdir(LAB)
        for dataset, seq in datasets:
            if args.action == 'prepare':
                if dataset.check_sequence_availability(seq, verbose=False) == 'corrupted':
                    raise ValueError(f'Partial layout: {dataset.sequence_path(seq)}. Preserve it by moving the whole sequence directory to a backup, then rerun prepare; no files have been removed.')
                dataset.download_sequence(seq)
            audit = validate_dataset(dataset, seq)
            provenance = {'framework_revision': subprocess.check_output(['git', '-C', str(LAB), 'rev-parse', 'HEAD'], text=True).strip(),
                          'framework_dirty': bool(subprocess.check_output(['git', '-C', str(LAB), 'status', '--porcelain'], text=True)),
                          'dataset': dataset.dataset_name, 'sequence': seq, 'target_resolution': dataset.target_resolution,
                          'retention': ('STANDARD (GEODE preserves sources)' if dataset.dataset_name == 'geode-gamma'
                                        else 'STANDARD (BotanicGarden preserves sources)'), 'experiment_config': str(config),
                          'data_revision': ('HF unpinned' if dataset.dataset_name.startswith('grandtour') else
                                            'Public S3, unpinned' if dataset.dataset_name == 'fomo' else
                                            'Pinned Drive MD5/SHA256; explicit GT timestamp sort; local origin translation v1; orientation convention v1' if dataset.dataset_name == 'geode-gamma' else
                                            'Published MD5 + pinned calibration'),
                          'audit': audit}
            (dataset.sequence_path(seq) / 'preparation_report.json').write_text(json.dumps(provenance, indent=2))
            print(json.dumps(provenance, indent=2), flush=True)


if __name__ == '__main__':
    main()
