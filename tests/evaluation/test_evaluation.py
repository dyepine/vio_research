import copy
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
from evo.tools import file_interface

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from evaluate_result import calculate, evaluate_run, validate_protocol
from trajectory_inputs import read_pose_csv, to_evo, camera_to_body
from run_results import select_run

class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ns = np.arange(20, dtype=np.int64) * 100_000_000 + 1_731_667_080_000_000_001
        t = np.arange(20, dtype=float)
        self.values = np.column_stack([t * 0.2, np.sin(t / 3), t * 0.01,
                                       np.tile([0, 0, 0, 1], (20, 1))])
        self.protocol = validate_protocol({'estimate_frame': 'body', 'evaluate_orientation': False,
                                           'rpe_delta_m': 0.5})

    def write_csv(self, path, stamps, values):
        with path.open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(['ts (ns)', 'tx (m)', 'ty (m)', 'tz (m)', 'qx', 'qy', 'qz', 'qw'])
            writer.writerows([[int(t), *v] for t, v in zip(stamps, values)])

    def run_fixture(self):
        output = self.root / 'output'
        output.mkdir()
        self.write_csv(output / '00000_KeyFrameTrajectory.csv', self.ns, self.values)
        self.write_csv(output / 'groundtruth.csv', self.ns, self.values)
        (output / 'system_output_00000.txt').write_text('Creation of new map with id: 0\n')
        (self.root / 'run_provenance.json').write_text(json.dumps({
            'output_directory': str(output), 'input_directory': str(output),
            'evaluation_protocol': self.protocol}))
        return output

    def test_integer_origin_and_quaternion_order(self):
        path = self.root / 'poses.csv'
        stamps = self.ns[0] + np.arange(3)
        self.write_csv(path, stamps, self.values[:3])
        loaded, values = read_pose_csv(path)
        traj = to_evo(loaded, values, int(stamps[0]))
        np.testing.assert_array_equal(loaded, stamps)
        np.testing.assert_allclose(traj.timestamps, [0, 1e-9, 2e-9], atol=1e-18)
        np.testing.assert_array_equal(traj.orientations_quat_wxyz, np.tile([1, 0, 0, 0], (3, 1)))

    def test_rigid_transform_and_scale_error(self):
        estimate = to_evo(self.ns, self.values, int(self.ns[0]))
        reference = copy.deepcopy(estimate)
        transform = np.eye(4)
        transform[:3, :3] = Rotation.from_euler('xyz', [20, 30, 40], degrees=True).as_matrix()
        transform[:3, 3] = [3, 5, 7]
        reference.transform(transform)
        protocol = dict(self.protocol, evaluate_orientation=True)
        results, summary = calculate(estimate, reference, protocol)
        self.assertLess(results['ape_position_m'].stats['rmse'], 1e-12)
        self.assertLess(results['ape_orientation_deg'].stats['rmse'], 1e-10)
        self.assertLess(results['rpe_position_m'].stats['rmse'], 1e-12)
        self.assertLess(results['rpe_orientation_deg'].stats['rmse'], 1e-10)
        reference.scale(2)
        results, _ = calculate(estimate, reference, protocol)
        self.assertGreater(results['ape_position_m'].stats['rmse'], 0.1)

        # Verify actual serialized scalar series, not just that an rrd file exists.

    def test_origin_alignment_matches_first_pose_and_preserves_drift(self):
        estimate = to_evo(self.ns, self.values, int(self.ns[0]))
        reference = copy.deepcopy(estimate)
        transform = np.eye(4)
        transform[:3, :3] = Rotation.from_euler('xyz', [.2, -.3, .4]).as_matrix()
        transform[:3, 3] = [3, -2, 1]
        estimate.transform(transform)
        # Later position errors must survive alignment at the start.
        estimate.positions_xyz[1:] += np.arange(1, 20)[:, None] * [.01, .02, 0]
        results, summary = calculate(estimate, reference,
                                     dict(self.protocol, align='origin', evaluate_orientation=True))
        aligned = results['ape_position_m'].trajectories['estimate']
        np.testing.assert_allclose(aligned.poses_se3[0], reference.poses_se3[0], atol=1e-12)
        self.assertLess(results['ape_position_m'].np_arrays['error_array'][0], 1e-12)
        self.assertGreater(results['ape_position_m'].np_arrays['error_array'][-1], .1)
        # A rigid global alignment cannot change relative motion errors.
        unaligned, _ = calculate(estimate, reference, dict(self.protocol, align='none'))
        np.testing.assert_allclose(results['rpe_position_m'].np_arrays['error_array'],
                                   unaligned['rpe_position_m'].np_arrays['error_array'], atol=1e-12)
        np.testing.assert_allclose(np.asarray(summary['alignment_transform_gt_from_estimate']) @
                                   transform, np.eye(4), atol=1e-12)

    def test_camera_extrinsic_is_right_multiplication(self):
        body = to_evo(self.ns, self.values, int(self.ns[0]))
        body_transform = np.eye(4)
        body_transform[:3, :3] = Rotation.from_euler('xyz', [10, 20, 30], degrees=True).as_matrix()
        body.transform(body_transform)
        extrinsic = np.eye(4)
        extrinsic[:3, :3] = Rotation.from_euler('z', 90, degrees=True).as_matrix()
        extrinsic[:3, 3] = [1, 0, 0]
        camera = copy.deepcopy(body)
        camera.transform(extrinsic, right_mul=True)
        calibration = self.root / 'calibration.yaml'
        calibration.write_text(yaml.safe_dump({'cameras': [{'cam_name': 'rgb_0', 'T_BS': extrinsic.ravel().tolist()}]}))
        converted = camera_to_body(camera, calibration)
        np.testing.assert_allclose(converted.poses_se3, body.poses_se3, atol=1e-12)

    def test_no_boundary_extrapolation(self):
        est = to_evo(self.ns, self.values, int(self.ns[0]))
        ref = copy.deepcopy(est)
        ref.reduce_to_ids(np.arange(1, 19))
        _, summary = calculate(est, ref, self.protocol)
        self.assertEqual(summary['matched_poses'], 18)
        ref.timestamps += 100
        with self.assertRaises(Exception):
            calculate(est, ref, self.protocol)

    def test_shorter_gt_uses_standard_evo_association(self):
        trajectory_type = type(to_evo(self.ns, self.values, int(self.ns[0])))
        est_times = np.array([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
        ref_times = np.array([0, 0.105, 0.108, 0.6])

        def trajectory(times):
            return trajectory_type(np.column_stack([times, times ** 2, np.zeros(len(times))]),
                                   np.tile([1, 0, 0, 0], (len(times), 1)), times)

        results, summary = calculate(trajectory(est_times), trajectory(ref_times),
                                     dict(self.protocol, align='none'))
        ape = results['ape_position_m']
        np.testing.assert_allclose(ape.trajectories['estimate'].timestamps, [0, 0.1, 0.1, 0.6])
        np.testing.assert_allclose(ape.trajectories['reference'].timestamps, ref_times)
        expected_errors = np.array([0, np.hypot(0.005, 0.105 ** 2 - 0.1 ** 2),
                                    np.hypot(0.008, 0.108 ** 2 - 0.1 ** 2), 0])
        np.testing.assert_allclose(ape.np_arrays['error_array'], expected_errors, atol=1e-15)
        self.assertEqual(summary['matched_pairs'], 4)
        self.assertEqual(summary['matched_poses'], 4)
        self.assertEqual(summary['unique_matched_estimate_poses'], 3)
        self.assertEqual(summary['unique_matched_gt_poses'], 4)

    def test_coverage_counts_unique_estimate_poses(self):
        output = self.run_fixture()
        gt_stamps = self.ns[0] + np.array([0, 105_000_000, 108_000_000, 1_900_000_000])
        self.write_csv(output / 'groundtruth.csv', gt_stamps, self.values[[0, 1, 1, 19]])
        evaluation = evaluate_run(self.root)
        summary = json.loads((evaluation / 'summary.json').read_text())
        self.assertEqual(summary['matched_pairs'], 4)
        self.assertEqual(summary['unique_matched_estimate_poses'], 3)
        self.assertEqual(summary['matched_fraction_of_saved_poses'], 3 / 20)

    def test_multiple_estimates_can_reuse_gt_pose(self):
        estimate = to_evo(self.ns[:6], self.values[:6], int(self.ns[0]))
        estimate.timestamps = np.array([0, 0.095, 0.1, 0.105, 0.3, 0.6])
        ref_times = np.array([0, 0.1, 0.2, 0.25, 0.4, 0.45, 0.5, 0.6])
        reference = type(estimate)(np.column_stack([ref_times, ref_times ** 2, np.zeros(len(ref_times))]),
                                   np.tile([1, 0, 0, 0], (len(ref_times), 1)), ref_times)
        results, summary = calculate(estimate, reference, dict(self.protocol, align='none'))
        ape = results['ape_position_m']
        np.testing.assert_allclose(ape.trajectories['estimate'].timestamps, [0, 0.095, 0.1, 0.105, 0.6])
        np.testing.assert_allclose(ape.trajectories['reference'].timestamps, [0, 0.1, 0.1, 0.1, 0.6])
        self.assertEqual(summary['matched_poses'], 5)

    def test_gap_segments_and_unavailable_rpe(self):
        est = to_evo(self.ns, self.values, int(self.ns[0]))
        est.timestamps[10:] += 20
        results, summary = calculate(est, copy.deepcopy(est), dict(self.protocol, rpe_delta_m=100))
        self.assertEqual(len(summary['matched_segments']), 2)
        self.assertNotIn('rpe_position_m', results)
        self.assertIn('rpe_position_m', summary['unavailable_metrics'])

    def test_protocol_rejects_scale_and_unknown_options(self):
        for settings in [{'correct_scale': True}, {'max_time_difference_s': 0}, {'align': 'Sim3'},
                         {'typo': 1}, {'evaluate_rpe': 'false'}]:
            with self.assertRaises(ValueError):
                validate_protocol(settings)

    def test_position_only_reference_uses_se3_without_pose_rpe(self):
        output = self.run_fixture()
        protocol = dict(self.protocol, align='SE3', evaluate_rpe=False)
        (self.root / 'protocol.yaml').write_text(yaml.safe_dump(protocol))
        evaluation = evaluate_run(self.root, self.root / 'protocol.yaml')
        summary = json.loads((evaluation / 'summary.json').read_text())
        self.assertEqual(set(summary['metrics']), {'ape_position_m'})
        self.assertLess(summary['metrics']['ape_position_m']['rmse'], 1e-10)
        self.assertIn('rpe_position_m', summary['unavailable_metrics'])
        self.assertFalse((evaluation / 'rpe_position_m.zip').exists())

    def test_reference_point_offset_uses_estimated_orientation(self):
        output = self.run_fixture()
        estimate = self.values.copy()
        rotations = Rotation.from_euler('z', np.linspace(0, 1.5, len(estimate))[:, None])
        estimate[:, 3:] = rotations.as_quat()
        offset = np.array([.6, -.3, .8])
        reference = self.values.copy()
        reference[:, :3] = estimate[:, :3] + rotations.apply(np.tile(offset, (len(estimate), 1)))
        self.write_csv(output / '00000_KeyFrameTrajectory.csv', self.ns, estimate)
        self.write_csv(output / 'groundtruth.csv', self.ns, reference)
        transform = np.eye(4); transform[:3, 3] = offset
        protocol = dict(self.protocol, evaluate_rpe=False, T_body_reference=transform.tolist())
        (self.root / 'protocol.yaml').write_text(yaml.safe_dump(protocol))
        evaluation = evaluate_run(self.root, self.root / 'protocol.yaml')
        summary = json.loads((evaluation / 'summary.json').read_text())
        self.assertLess(summary['metrics']['ape_position_m']['rmse'], 1e-10)
        self.assertEqual(summary['compared_pose_frame'], 'reference')
        from Evaluate.protocol_plots import full_paths
        plotted, reference_path = full_paths(summary)
        np.testing.assert_allclose(plotted.positions_xyz, reference_path.positions_xyz, atol=1e-10)

    def test_saved_evaluations_are_versioned_and_readable(self):
        self.run_fixture()
        first = evaluate_run(self.root)
        second = evaluate_run(self.root)
        self.assertNotEqual(first, second)
        result = file_interface.load_res_file(first / 'ape_position_m.zip', load_trajectories=True)
        self.assertLess(result.stats['rmse'], 1e-12)
        self.assertEqual(len(result.np_arrays['timestamps']), 20)
        summary = json.loads((first / 'summary.json').read_text())
        self.assertIn('partial', ' '.join(summary['warnings']))

    def test_failed_export_removes_reservation_and_preserves_previous_evaluation(self):
        self.run_fixture()
        completed = evaluate_run(self.root)
        original_summary = (completed / 'summary.json').read_bytes()
        with patch('Evaluate.protocol.file_interface.save_res_file', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                evaluate_run(self.root)
        self.assertEqual(list((self.root / 'evaluations').iterdir()), [completed])
        self.assertEqual((completed / 'summary.json').read_bytes(), original_summary)
        self.assertEqual(select_run(None, self.root / 'evaluations'), completed)

    def test_selection_skips_incomplete_evaluations_after_interruption(self):
        self.run_fixture()
        completed = evaluate_run(self.root)
        interrupted = self.root / 'evaluations' / '9999-12-31_23-59-59'
        interrupted.mkdir()
        incomplete = interrupted.with_name(interrupted.name + '-02')
        incomplete.mkdir()
        (incomplete / 'summary.json').write_text('{}')
        selected = select_run(None, self.root / 'evaluations',
                              required_files=('summary.json', 'protocol.yaml', 'ape_position_m.zip'))
        self.assertEqual(selected, completed)

    def test_legacy_run_needs_explicit_protocol_and_maps_rejected(self):
        output = self.run_fixture()
        provenance = json.loads((self.root / 'run_provenance.json').read_text())
        del provenance['evaluation_protocol']
        (self.root / 'run_provenance.json').write_text(json.dumps(provenance))
        with self.assertRaisesRegex(ValueError, 'Legacy'):
            evaluate_run(self.root)
        protocol = self.root / 'protocol.yaml'
        protocol.write_text(yaml.safe_dump(self.protocol))
        evaluate_run(self.root, protocol)
        (output / 'system_output_00000.txt').write_text('Creation of new map with id: 0\nCreation of new map with id: 1\n')
        with self.assertRaisesRegex(ValueError, 'Multiple independent'):
            evaluate_run(self.root, protocol)

    def test_gt_quality_intervals_and_journal(self):
        output = self.run_fixture()
        # Recreate the nested VSLAM-LAB output layout and its native journal.
        nested = self.root / 'experiment' / 'DATASET' / 'sequence'
        nested.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.rename(nested)
        provenance_path = self.root / 'run_provenance.json'
        provenance = json.loads(provenance_path.read_text())
        provenance.update(output_directory=str(nested), input_directory=str(nested),
                          dataset_name='dataset', sequence_name='sequence')
        provenance['evaluation_protocol']['gt_valid_intervals_ns'] = [
            [int(self.ns[0]), int(self.ns[5])], [int(self.ns[10]), int(self.ns[-1])]]
        provenance_path.write_text(json.dumps(provenance))
        log = nested.parent.parent / 'vslamlab_exp_log.csv'
        log.write_text('dataset_name,sequence_name,exp_it,EVALUATION\ndataset,sequence,0,none\n')
        evaluation = evaluate_run(self.root)
        summary = json.loads((evaluation / 'summary.json').read_text())
        self.assertEqual(summary['matched_poses'], 16)
        self.assertEqual(len(summary['matched_segments']), 2)
        with log.open() as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row['EVALUATION'], 'evo')
        self.assertEqual(row['evaluation_directory'], str(evaluation))

    def test_invalid_csv_not_silently_repaired(self):
        path = self.root / 'bad.csv'
        for stamps, values in [(self.ns[::-1], self.values), (self.ns, self.values * np.nan),
                               (self.ns, np.column_stack([self.values[:, :3], self.values[:, 3:] * 2]))]:
            self.write_csv(path, stamps, values)
            with self.assertRaises(ValueError):
                read_pose_csv(path)
