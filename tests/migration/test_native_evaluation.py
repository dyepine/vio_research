"""Exercise native evaluation across variants, sequences, repetitions and failures."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from scipy.spatial.transform import Rotation
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'external/VSLAM-LAB')]
import vslamlab_utilities as native
from Evaluate.protocol import validate_protocol
from Datasets.dataset_files.dataset_botanicgarden import BotanicgardenDataset


class NativeEvaluationTests(unittest.TestCase):
    def write_poses(self, path, poses, stamps):
        with path.open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(['ts (ns)', 'tx (m)', 'ty (m)', 'tz (m)', 'qx', 'qy', 'qz', 'qw'])
            for stamp, pose in zip(stamps, poses):
                writer.writerow([int(stamp), *pose[:3, 3], *Rotation.from_matrix(pose[:3, :3]).as_quat()])

    def fixture(self, root):
        selection = root / 'sequences.yaml'
        selection.write_text("botanicgarden: ['1018_00', '1018_13']\n")
        calib_transform = np.eye(4)
        calib_transform[:3, :3] = Rotation.from_euler('xyz', [.3, -.2, .1]).as_matrix()
        calib_transform[:3, 3] = [.4, -.2, .1]
        global_transform = np.eye(4)
        global_transform[:3, :3] = Rotation.from_euler('xyz', [.2, .1, -.6]).as_matrix()
        global_transform[:3, 3] = [4, -2, 3]
        t = np.arange(30)
        body = np.tile(np.eye(4), (30, 1, 1))
        body[:, :3, 3] = np.column_stack([t*.2, np.sin(t*.2), np.cos(t*.1)])
        body[:, :3, :3] = Rotation.from_euler('z', (t*.05)[:, None]).as_matrix()
        stamps = 1_730_000_000_000_000_003 + t.astype(np.int64)*100_000_000
        recipes = {}
        for frame in ['camera', 'body']:
            recipes[frame] = dict(Config=str(selection), Module='orbslam3', NumRuns=2,
                                  Parameters={'mode': 'stereo-vi'}, Evaluation=validate_protocol({
                                      'estimate_frame': frame, 'rpe_delta_m': .4}))
            for seq in ['1018_00', '1018_13']:
                folder = root / 'results' / frame / 'BOTANICGARDEN' / seq
                folder.mkdir(parents=True)
                self.write_poses(folder/'groundtruth.csv', body, stamps)
                (folder/'calibration_exp.yaml').write_text(yaml.safe_dump({'cameras': [dict(
                    cam_name='rgb_0', T_BS=calib_transform.tolist())]}))
                estimate = global_transform @ (body @ calib_transform if frame == 'camera' else body)
                for iteration in range(2):
                    self.write_poses(folder/f'{iteration:05d}_KeyFrameTrajectory.csv', estimate, stamps)
                    (folder/f'system_output_{iteration:05d}.txt').write_text('Creation of new map with id: 0\n')
        exp = root / 'experiment.yaml'
        exp.write_text(yaml.safe_dump(recipes))
        with patch.object(native, 'VSLAMLAB_EVALUATION', root/'results'):
            native.update_experiment_csv_logs(exp)
        for variant in ['camera', 'body']:
            path = root/'results'/variant/'vslamlab_exp_log.csv'
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                row.update(STATUS='completed', SUCCESS='True')
            with path.open('w') as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
        return exp

    def test_matrix_body_camera_and_repeats_match_without_double_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = self.fixture(root)
            with patch.object(native, 'VSLAMLAB_EVALUATION', root / 'results'):
                native.update_experiment_csv_logs(exp)
                native.evaluate_exp(exp, protocol_override={'max_time_difference_s': .02})
                native.compare_exp(exp)
                records = list(csv.DictReader((root/'comparison.csv').open()))
            self.assertEqual(len(records), 8)
            self.assertTrue(all(r['status'] == 'evaluated' for r in records))
            for record in records:
                self.assertLess(float(record['ape_position_m_rmse']), 1e-10)
                self.assertLess(float(record['ape_orientation_deg_rmse']), 1e-10)
                self.assertEqual(float(record['matched_fraction_of_saved_poses']), 1)
                self.assertEqual(int(record['matched_pairs']), 30)
                self.assertEqual(int(record['unique_matched_estimate_poses']), 30)
                self.assertEqual(int(record['unique_matched_gt_poses']), 30)
                self.assertEqual(float(record['max_matched_time_difference_s']), 0)
                self.assertEqual(record['correct_scale'], 'False')
                directory = Path(record['evaluation_directory'])
                self.assertTrue((directory/'rpe_position_m.zip').is_file())
                summary = json.loads((directory/'summary.json').read_text())
                self.assertEqual(summary['estimate_input_frame'], record['experiment'])
                self.assertEqual(summary['protocol']['max_time_difference_s'], .02)
                self.assertEqual(summary['compared_pose_frame'], 'body')

    def test_failures_remain_in_table_and_do_not_stop_other_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = self.fixture(root)
            (root/'results/camera/BOTANICGARDEN/1018_13/00001_KeyFrameTrajectory.csv').write_text('invalid\n')
            with patch.object(native, 'VSLAMLAB_EVALUATION', root/'results'):
                native.update_experiment_csv_logs(exp)
                log = root/'results/body/vslamlab_exp_log.csv'
                rows = list(csv.DictReader(log.open()))
                # Native logs initially have no finished runs; mark all complete except one.
                for variant in ['camera', 'body']:
                    path = root/'results'/variant/'vslamlab_exp_log.csv'
                    rows = list(csv.DictReader(path.open()))
                    for row in rows: row.update(STATUS='completed', SUCCESS='True')
                    if variant == 'body': rows[-1]['SUCCESS'] = 'False'
                    with path.open('w') as stream:
                        writer=csv.DictWriter(stream, fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
                with self.assertRaisesRegex(RuntimeError, '2 runs'):
                    native.evaluate_exp(exp)
                records = list(csv.DictReader((root/'comparison.csv').open()))
            self.assertEqual(len(records), 8)
            self.assertEqual(sum(r['status']=='evaluated' for r in records), 6)
            self.assertEqual(sum(r['status']=='run_failed' for r in records), 1)
            self.assertEqual(sum(r['status']=='evaluation_failed' for r in records), 1)
            rows=list(csv.DictReader((root/'results/camera/vslamlab_exp_log.csv').open()))
            self.assertEqual(rows[-1]['EVALUATION'], 'failed')
            self.assertIn('ValueError', rows[-1]['evaluation_error'])


    def test_missing_native_log_does_not_hide_requested_repetitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = self.fixture(root)
            (root/'results/body/vslamlab_exp_log.csv').unlink()
            with patch.object(native, 'VSLAMLAB_EVALUATION', root/'results'):
                with self.assertRaisesRegex(RuntimeError, '4 runs'):
                    native.evaluate_exp(exp)
            records = list(csv.DictReader((root/'comparison.csv').open()))
            self.assertEqual(len(records), 8)
            self.assertEqual(sum(r['status']=='evaluated' for r in records), 4)
            self.assertEqual(sum(r['error']=='Native execution log row missing' for r in records), 4)

    def test_parallel_log_updates_preserve_other_repetitions(self):
        from concurrent.futures import ThreadPoolExecutor
        from Evaluate.protocol import update_evaluation_log
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            path = root/'results/body/vslamlab_exp_log.csv'
            def update(iteration):
                update_evaluation_log(path, 'botanicgarden', '1018_00', iteration,
                                      root/f'published_{iteration}', {'unique_matched_estimate_poses': 40+iteration})
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(update, [0, 1]))
            rows = list(csv.DictReader(path.open()))
            changed = {int(r['exp_it']): r for r in rows if r['sequence_name']=='1018_00'}
            self.assertEqual(changed[0]['num_evaluated_frames'], '40')
            self.assertEqual(changed[1]['num_evaluated_frames'], '41')
            self.assertTrue(all(r['EVALUATION']=='none' for r in rows if r['sequence_name']=='1018_13'))

    def test_native_without_protocol_keeps_benchmark_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = self.fixture(root)
            recipes = yaml.safe_load(exp.read_text())
            for recipe in recipes.values():
                recipe.pop('Evaluation')
            exp.write_text(yaml.safe_dump(recipes))
            with patch.object(native, 'VSLAMLAB_EVALUATION', root/'results'), \
                 patch.object(native, 'evaluate_sequence', return_value=None) as benchmark:
                native.evaluate_exp(exp)
            self.assertEqual(benchmark.call_count, 4)
            self.assertTrue(all(call.args[0].evaluation is None for call in benchmark.call_args_list))
            self.assertFalse((root/'comparison.csv').exists())
