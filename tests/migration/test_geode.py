"""GEODE source interpretation and actual ROS1 compressed stereo extraction."""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import yaml
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / 'external/VSLAM-LAB'
sys.path[:0] = [str(ROOT / 'scripts'), str(LAB)]
from Datasets.dataset_files.dataset_geode import GeodeGammaDataset, reference_rows, reference_orientations
from Datasets.dataset_files.geode_calibration import geometry, read_calibration, matrix
from Datasets.dataset_files.geode_radtan_fit import fit_camera, project, source_parameters
from Datasets.get_dataset import get_dataset
from prepare_datasets import preparation_estimate

CALIBRATION = Path(__file__).parent / 'fixtures/geode/gamma_config.yaml'


class GeodeTests(unittest.TestCase):
    def test_radtan4_approximation_error_is_checked_on_every_pixel(self):
        for camera in read_calibration(CALIBRATION)['cameras']:
            fitted = fit_camera(camera)
            self.assertEqual(fitted['validation_pixel_count'], 1224 * 1024)
            selected = fitted['candidates'][fitted['selected']]
            self.assertEqual(len(selected['D']), 4)
            self.assertLess(selected['error']['rms_px'], .07)
            self.assertLess(selected['error']['max_px'], .9)
            self.assertLess(selected['error']['rms_px'], fitted['candidates']['fixed_intrinsics']['error']['rms_px'])
            self.assertGreater(fitted['candidates']['drop_k3']['error']['max_px'], 5.)

    def test_radtan_projection_matches_opencv(self):
        K, D = source_parameters(read_calibration(CALIBRATION)['cameras'][0])
        xy = np.array([[-.5, -.4], [0., 0.], [.45, .3]])
        xyz = np.column_stack((xy, np.ones(len(xy))))
        for distortion in (D, D[:4]):
            expected = cv2.projectPoints(xyz, np.zeros(3), np.zeros(3), K, distortion)[0].reshape(-1, 2)
            np.testing.assert_allclose(project(xy, K, distortion), expected, atol=1e-10)

    def test_concatenated_camera_sections_and_duplicate_gyro_key(self):
        c = read_calibration(CALIBRATION)
        self.assertEqual(len(c['cameras']), 2)
        self.assertAlmostEqual(c['cameras'][0]['projection_parameters']['fx'], 1174.433772943354)
        self.assertAlmostEqual(c['cameras'][1]['projection_parameters']['fx'], 1176.913615863912)
        self.assertEqual(c['noise']['sigma_g_c'], 5.1441059541810427e-3)
        self.assertEqual(c['noise']['sigma_gw_c'], 1.0881627554710405e-4)

    def test_rectified_extrinsics_and_projection_agree(self):
        c = read_calibration(CALIBRATION)
        size, maps, projections, transforms, T_BI, metadata = geometry(c)
        self.assertEqual(size, (1224, 1024))
        self.assertEqual(maps[0][0].shape, (1024, 1224))
        T_01 = np.linalg.inv(transforms[0]) @ transforms[1]
        np.testing.assert_allclose(T_01[:3, :3], np.eye(3), atol=1e-7)
        np.testing.assert_allclose(T_01[1:3, 3], [0, 0], atol=1e-7)
        relative = np.linalg.inv(matrix(c['transforms']['T_IMU_CamR'])) @ matrix(c['transforms']['T_IMU_CamL'])
        baseline = np.linalg.norm(relative[:3, 3])
        self.assertAlmostEqual(T_01[0, 3], baseline, places=7)
        self.assertAlmostEqual(-projections[1][0, 3] / projections[1][0, 0], baseline, places=7)
        self.assertGreater(metadata['unused_stereo_translation_difference_m'], .005)
        self.assertGreater(np.linalg.norm(T_BI[:3, 3]), .5)
        # The publisher postmultiplies a gamma trajectory by inverse(T) to
        # obtain beta, so the numeric T itself is beta<-gamma, not its inverse.
        T_BG = np.array(metadata['T_beta_gamma_lidar'])
        np.testing.assert_allclose(T_BG[:3, 3], [.0305, -.5959, .0902])
        np.testing.assert_allclose(T_BI @ matrix(c['transforms']['T_IMU_LiDAR']), T_BG, atol=1e-8)
        world_beta = np.eye(4); world_beta[:3, 3] = [10, 20, 30]
        world_gamma = world_beta @ T_BI @ matrix(c['transforms']['T_IMU_LiDAR'])
        np.testing.assert_allclose(world_gamma @ np.linalg.inv(T_BG), world_beta, atol=1e-8)
        # Camera->IMU->published body chains must represent the same optical rig.
        rect = np.linalg.inv(T_BI @ matrix(c['transforms']['T_IMU_CamL'])) @ transforms[0]
        np.testing.assert_allclose(rect[:3, 3], [0, 0, 0], atol=1e-8)

    def test_real_stereo_pair_has_subpixel_median_vertical_residual(self):
        # Real simultaneous images from the pinned Offroad1 gamma bag. This
        # catches the ~16 px error that synthetic transform consistency misses.
        _, maps, _, _, _, _ = geometry(read_calibration(CALIBRATION))
        detector = cv2.SIFT_create(nfeatures=3000)
        keys, descriptors = [], []
        for i, name in enumerate(('left.jpg', 'right.jpg')):
            image = cv2.imread(str(CALIBRATION.parent / name), cv2.IMREAD_GRAYSCALE)
            rectified = cv2.remap(image, *maps[i], cv2.INTER_LINEAR)
            key, desc = detector.detectAndCompute(rectified, None)
            keys.append(key); descriptors.append(desc)
        matches = [a for a, b in cv2.BFMatcher().knnMatch(*descriptors, k=2) if a.distance < .7 * b.distance]
        a = np.float32([keys[0][m.queryIdx].pt for m in matches])
        b = np.float32([keys[1][m.trainIdx].pt for m in matches])
        _, mask = cv2.findFundamentalMat(a, b, cv2.FM_RANSAC, 1.5, .999)
        keep = mask.ravel().astype(bool)
        self.assertGreater(int(keep.sum()), 100)
        residual = np.abs(a[keep, 1] - b[keep, 1])
        self.assertLess(float(np.median(residual)), 1.)
        self.assertLess(float(np.quantile(residual, .9)), 2.)

    def test_reference_sort_is_explicit_and_nanoseconds_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'gt.txt'
            text = '\n'.join(f'1709436642.{ns} 1 2 3 0 0 0 1'
                             for ns in ('000000003', '000000001', '000000002'))
            p.write_text(text)
            rows, metadata = reference_rows(p)
            self.assertEqual([r[0] for r in rows], [1709436642000000001, 1709436642000000002, 1709436642000000003])
            self.assertEqual(metadata['source_adjacent_time_inversions'], 1)
            self.assertEqual(p.read_text(), text)
            self.assertIn('no pose removal', metadata['timestamp_policy'])

    def test_duplicate_or_invalid_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'gt.txt'
            for rows in ('1 0 0 0 0 0 0 1\n1 1 0 0 0 0 0 1\n2 2 0 0 0 0 0 1\n',
                         '1 nan 0 0 0 0 0 1\n2 1 0 0 0 0 0 1\n3 2 0 0 0 0 0 1\n'):
                p.write_text(rows)
                with self.assertRaises(ValueError):
                    reference_rows(p)

    def test_reference_orientation_convention_preserves_proper_rotations(self):
        angles = np.array([[0, 0, 0], [20, -30, 150], [-15, 89.9999, -170], [5, -90, 40]])
        source = Rotation.from_euler('xyz', angles, degrees=True)
        converted = Rotation.from_quat(reference_orientations(source.as_quat()))
        expected = angles.copy(); expected[:, 1] *= -1; expected[:, 2] = 90 - expected[:, 2]
        np.testing.assert_allclose(converted.as_matrix(),
                                   Rotation.from_euler('xyz', expected, degrees=True).as_matrix(), atol=1e-12)
        np.testing.assert_allclose(np.linalg.det(converted.as_matrix()), 1, atol=1e-12)
        # Opposite quaternion signs and small source norm errors encode the same rotation.
        np.testing.assert_allclose(Rotation.from_quat(reference_orientations(-source.as_quat()*1.001)).as_matrix(),
                                   converted.as_matrix(), atol=1e-12)

    def test_local_gt_preserves_motion_and_cached_prepare_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = GeodeGammaDataset(); dataset.dataset_path = Path(tmp)
            folder = dataset.sequence_path('offroad1'); folder.mkdir()
            raw = Path(tmp) / 'raw'; raw.mkdir()
            source = raw / dataset.cfg['assets']['reference']['name']
            # The first file row is NOT the earliest timestamp. Also preserve
            # non-identity orientations to exercise the explicit convention.
            source.write_text('3 792083 2565262 1 0 0 0.6 0.8\n'
                              '1 792079 2565259 -1 0 0 0 1\n'
                              '2 792080 2565261 0 0 0 0.6 0.8\n')
            original_bytes = source.read_bytes()
            source_rows, _ = reference_rows(source)
            with patch.dict(os.environ, {'GEODE_SOURCE_DIR': str(raw)}):
                dataset.create_groundtruth_csv('offroad1')
                first = dataset.groundtruth_csv_path('offroad1').read_bytes()
                with dataset.groundtruth_csv_path('offroad1').open() as stream:
                    rows = list(csv.reader(stream))[1:]
                self.assertEqual([int(r[0]) for r in rows], [r[0] for r in source_rows])
                values = np.array([r[1:] for r in rows], dtype=float)
                original = np.array([r[1:] for r in source_rows])
                np.testing.assert_array_equal(values[0, :3], [0, 0, 0])
                np.testing.assert_array_equal(np.diff(values[:, :3], axis=0), np.diff(original[:, :3], axis=0))
                np.testing.assert_allclose(Rotation.from_quat(values[:, 3:]).as_matrix(),
                    Rotation.from_quat(reference_orientations(original[:, 3:])).as_matrix(), atol=1e-12)
                metadata = json.loads((folder / 'reference_metadata.json').read_text())
                self.assertEqual(metadata['origin_xyz_m'], [792079, 2565259, -1])
                self.assertEqual(metadata['origin_timestamp_ns'], 1_000_000_000)
                self.assertEqual(metadata['orientation_convention_version'], 1)
                self.assertFalse(metadata['fitted_orientation_bias_applied'])
                # Exercise migration of GT already translated by the previous
                # adapter but not yet using the new orientation convention.
                (folder / 'reference_metadata.json').write_text('{"local_origin_version": 1}')
                (folder / 'calibration.yaml').write_text('cameras: []\n')
                with patch.object(dataset, 'check_sequence_availability', return_value='available'), \
                        patch.object(dataset, 'create_groundtruth_csv', wraps=dataset.create_groundtruth_csv) as regenerate, \
                        patch.object(dataset, 'download_process', side_effect=AssertionError('Must reuse prepared data')):
                    dataset.download_sequence('offroad1')
                    dataset.download_sequence('offroad1')
                    regenerate.assert_called_once_with('offroad1')
                self.assertEqual(dataset.groundtruth_csv_path('offroad1').read_bytes(), first)
                dataset.sequence_path('offroad1_raw_radtan4').mkdir()
                dataset.create_groundtruth_csv('offroad1_raw_radtan4')
                self.assertEqual(dataset.groundtruth_csv_path('offroad1_raw_radtan4').read_bytes(), first)
            self.assertEqual(source.read_bytes(), original_bytes)

    def test_registered_catalog_and_storage_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = get_dataset('geode-gamma')
            dataset.dataset_path = Path(tmp)
            self.assertEqual(dataset.sequence_names,
                             ['offroad1', 'offroad1_raw_radtan4', 'offroad7', 'offroad1_raw_radtan5'])
            self.assertIn('stereo-vi', dataset.modes)
            with patch.dict(os.environ, {'GEODE_SOURCE_DIR': str(Path(tmp) / 'raw')}):
                estimate = preparation_estimate(dataset, 'offroad1')
            self.assertGreater(estimate, 3_204_605_460)
            self.assertLess(estimate, 30_000_000_000)

    def test_offroad7_assets_are_isolated_and_calibration_shared(self):
        dataset = GeodeGammaDataset()
        first = dataset.assets_for('offroad1')
        seventh = dataset.assets_for('offroad7')
        self.assertEqual(seventh['bag']['name'], 'Offroad7_gamma.bag')
        self.assertEqual(seventh['reference']['name'], 'Offroad7.txt')
        self.assertEqual(seventh['calibration'], first['calibration'])
        self.assertEqual(dataset.assets_for('offroad1_raw_radtan4'), first)
        self.assertEqual(dataset.cfg['assets']['bag']['name'], 'Offroad1_gamma.bag')
        self.assertEqual(dataset._asset('reference', 'offroad7').name, 'Offroad7.txt')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'GEODE_SOURCE_DIR': tmp}):
            estimate = preparation_estimate(dataset, 'offroad7')
            self.assertLess(estimate, 8_000_000_000)
            # Resuming Offroad7 must select only its own bag/GT, never Offroad1.
            with patch('Datasets.dataset_files.dataset_geode.verified', return_value=False), \
                    patch('Datasets.dataset_files.dataset_geode.downloadFile') as download:
                dataset.dataset_path = Path(tmp)
                dataset.download_sequence_data('offroad7')
                self.assertEqual([c.kwargs['filename'] for c in download.call_args_list],
                                 ['Offroad7_gamma.bag', 'gamma_config.yaml', 'Offroad7.txt'])

    def test_original_radtan5_preserves_published_calibration_and_reuses_native_pixels(self):
        from Datasets.dataset_files.geode_calibration import body_transforms
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = GeodeGammaDataset(); dataset.dataset_path = root
            raw = root / 'raw'; raw.mkdir()
            (raw / 'gamma_config.yaml').write_bytes(CALIBRATION.read_bytes())
            checksum = hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()
            dataset.cfg['assets']['calibration']['sha256'] = checksum
            source = dataset.sequence_path('offroad1_raw_radtan4'); source.mkdir()
            target = dataset.sequence_path('offroad1_raw_radtan5'); target.mkdir()
            for i in (0, 1):
                (source / f'rgb_{i}').mkdir()
                cv2.imwrite(str(source / f'rgb_{i}/123.png'), np.full((10, 12), 20+i, dtype=np.uint8))
                (source / f'rgb_{i}.csv').write_text(f'ts,path\n123,rgb_{i}/123.png\n')
            (source / 'image_geometry.json').write_text(json.dumps(dict(
                source_calibration_sha256=checksum, image_processing='BGR to grayscale PNG; no warp, crop or resize')))
            with patch.object(dataset, 'check_sequence_availability', return_value='available'), \
                    patch.dict(os.environ, {'GEODE_SOURCE_DIR': str(raw)}):
                dataset.create_rgb_folder('offroad1_raw_radtan5')
                dataset.create_rgb_folder('offroad1_raw_radtan5')  # Idempotent hard-link reuse.
                dataset.create_calibration_yaml('offroad1_raw_radtan5')
            saved = yaml.safe_load((target / 'calibration.yaml').read_text())
            published = read_calibration(CALIBRATION)
            _, T_BI = body_transforms(published)
            for i, (camera, original) in enumerate(zip(saved['cameras'], published['cameras'])):
                self.assertTrue(os.path.samefile(source / f'rgb_{i}/123.png', target / f'rgb_{i}/123.png'))
                self.assertEqual(camera['distortion_type'], 'radtan5')
                self.assertEqual(camera['distortion_coefficients'],
                    [original['distortion_parameters'][k] for k in ('k1', 'k2', 'p1', 'p2', 'k3')])
                self.assertEqual(camera['focal_length'], [original['projection_parameters'][k] for k in ('fx', 'fy')])
                self.assertEqual(camera['principal_point'], [original['projection_parameters'][k] for k in ('cx', 'cy')])
                T_IC = matrix(published['transforms']['T_IMU_CamL' if i == 0 else 'T_IMU_CamR'])
                np.testing.assert_allclose(np.linalg.inv(T_BI) @ np.array(camera['T_BS']).reshape(4, 4), T_IC, atol=1e-12)
            self.assertFalse((target / 'radtan4_fit.json').exists())
            self.assertFalse((target / 'rectification.json').exists())
            # exFAT does not support hard links. Copy exact bytes and allow resume.
            target.rename(root / 'linked_output')
            target.mkdir()
            with patch.object(dataset, 'check_sequence_availability', return_value='available'), \
                    patch('Datasets.dataset_files.dataset_geode.os.link',
                          side_effect=PermissionError(1, 'Operation not permitted')):
                dataset.create_rgb_folder('offroad1_raw_radtan5')
                dataset.create_rgb_folder('offroad1_raw_radtan5')
            for i in (0, 1):
                a, b = source / f'rgb_{i}/123.png', target / f'rgb_{i}/123.png'
                self.assertFalse(os.path.samefile(a, b))
                self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(json.loads((target / 'image_geometry.json').read_text())['image_reuse']['copied_images'], 2)

    def test_interrupted_import_reuses_owned_layout_and_pinned_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = GeodeGammaDataset()
            dataset.dataset_path = Path(tmp)
            with patch.dict(os.environ, {'GEODE_SOURCE_DIR': str(Path(tmp) / 'raw')}), \
                    patch('Datasets.dataset_files.dataset_geode.downloadFile', side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):
                    dataset.download_sequence_data('offroad1')
            folder = dataset.sequence_path('offroad1')
            (folder / 'rgb_0').mkdir()
            self.assertEqual(dataset.check_sequence_availability('offroad1', False), 'non-available')
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                dataset.download_sequence_data('offroad2')

    def test_outdated_rectification_is_preserved_before_reimport(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = GeodeGammaDataset(); dataset.dataset_path = Path(tmp)
            folder = dataset.sequence_path('offroad1'); folder.mkdir()
            (folder / 'import_complete.json').write_text('{}')
            (folder / 'rectification.json').write_text(json.dumps({'metadata': {}}))
            (folder / 'old.png').write_bytes(b'old pixels')
            self.assertEqual(dataset.check_sequence_availability('offroad1', False), 'non-available')
            with patch.object(dataset, 'download_process') as process:
                dataset.download_sequence('offroad1')
                process.assert_called_once_with('offroad1')
            self.assertEqual((Path(tmp) / 'offroad1.rectification-v1/old.png').read_bytes(), b'old pixels')

    def test_pairing_uses_timestamps_instead_of_row_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = GeodeGammaDataset()
            dataset.dataset_path = Path(tmp)
            folder = dataset.sequence_path('offroad1'); folder.mkdir()
            for i, stamps in enumerate(([10_000_000, 110_000_000, 210_000_000], [10_050_000, 210_050_000])):
                with (folder / f'rgb_{i}.csv').open('w') as stream:
                    writer = csv.writer(stream); writer.writerow(['ts', 'path'])
                    writer.writerows([stamp, f'rgb_{i}/{stamp}.png'] for stamp in stamps)
            dataset.create_rgb_csv('offroad1')
            with dataset.rgb_csv_path('offroad1').open() as stream:
                rows = list(csv.reader(stream))[1:]
            self.assertEqual([int(row[0]) for row in rows], [10_000_000, 210_000_000])
            report = json.loads((folder / 'stereo_report.json').read_text())
            self.assertEqual(report['unpaired_counts'], [1, 0])

    @unittest.skipUnless((LAB / '.pixi/envs/ros1/bin/python').is_file(), 'ROS1 Pixi environment unavailable')
    def test_actual_ros1_compressed_bag_extraction_and_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calib = root / 'gamma_config.yaml'
            # Smaller image fixture; preserve the same physical extrinsics.
            import re
            text = CALIBRATION.read_text()
            text = re.sub(r'(?m)^image_width:.*$', 'image_width: 64', text)
            text = re.sub(r'(?m)^image_height:.*$', 'image_height: 48', text)
            for k, v in dict(fx=60., fy=60., cx=32., cy=24.).items():
                text = re.sub(r'(?m)^(\s*' + k + r':)\s*[^\n]+', r'\g<1> ' + str(v), text)
            calib.write_text(text)
            bag = root / 'fixture.bag'
            generator = '''import sys, rosbag, cv2, numpy as np
from pathlib import Path
from sensor_msgs.msg import CompressedImage
from genpy import Time
with rosbag.Bag(sys.argv[1], 'w') as bag:
    for frame in range(3):
        for side in ('left', 'right'):
            m = CompressedImage()
            m.header.stamp = Time(1709436642, frame * 100000000 + (100000 if side == 'right' else 0))
            m.header.frame_id = side
            m.format = 'bgr8; jpeg compressed bgr8'
            yy, xx = np.indices((48, 64))
            image = np.stack((xx*3, yy*5, (xx+yy+frame)*2), axis=2).astype(np.uint8)
            m.data = cv2.imencode('.jpg', image)[1].tobytes()
            Path(sys.argv[1]).with_name(f'source_{side}_{frame}.jpg').write_bytes(m.data)
            bag.write('/' + side + '_camera/image/compressed', m, Time(1709436643, frame * 100000000))
'''
            env = os.environ.copy(); env.pop('PYTHONPATH', None)
            python = LAB / '.pixi/envs/ros1/bin/python'
            subprocess.run([str(python), '-c', generator, str(bag)], check=True, env=env)
            output = root / 'offroad1'
            subprocess.run([str(python), str(LAB / 'Datasets/extra-files/extract_geode_stereo.py'),
                            '--bag', str(bag), '--calibration', str(calib), '--output', str(output)],
                           check=True, env=env, capture_output=True, text=True)
            for cam in (0, 1):
                with (output / f'rgb_{cam}.csv').open() as stream:
                    rows = list(csv.reader(stream))[1:]
                self.assertEqual(len(rows), 3)
                self.assertEqual(int(rows[0][0]), 1709436642000000000 + cam * 100000)
                image = cv2.imread(str(output / rows[0][1]), cv2.IMREAD_UNCHANGED)
                self.assertEqual(image.shape, (48, 64))
                self.assertEqual(image.dtype, np.uint8)
            # Materialize calibration from the ROS1 extractor's recorded geometry,
            # rather than recomputing maps/projections in this OpenCV environment.
            dataset = GeodeGammaDataset(); dataset.dataset_path = root
            dataset.cfg['assets']['calibration']['sha256'] = hashlib.sha256(calib.read_bytes()).hexdigest()
            with patch.dict(os.environ, {'GEODE_SOURCE_DIR': str(root)}):
                dataset.create_calibration_yaml('offroad1')
            saved = yaml.safe_load((output / 'calibration.yaml').read_text())
            actual = json.loads((output / 'rectification.json').read_text())
            for i, camera in enumerate(saved['cameras']):
                self.assertEqual(camera['image_dimension'], [64, 48])
                self.assertEqual(camera['cam_model'], 'pinhole')
                self.assertEqual(camera['distortion_type'], 'radtan4')
                self.assertEqual(camera['distortion_coefficients'], [0., 0., 0., 0.])
                np.testing.assert_allclose(np.array(camera['T_BS']).reshape(4, 4), actual['camera_T_BS'][i], atol=1e-12)
                self.assertEqual(camera['focal_length'][0], actual['projections'][i][0][0])
            np.testing.assert_allclose(np.array(saved['imus'][0]['T_BS']).reshape(4, 4), actual['imu_T_BS'], atol=1e-12)
            # Existing prepared datasets must be upgraded by ordinary prepare,
            # while the existing rectified images and their geometry stay intact.
            original_image = (output / rows[0][1]).read_bytes()
            legacy = yaml.safe_load((output / 'calibration.yaml').read_text())
            for camera in legacy['cameras']:
                camera.update(distortion_type='pinhole', distortion_coefficients=[])
            (output / 'calibration.yaml').write_text(yaml.safe_dump(legacy))
            with patch.dict(os.environ, {'GEODE_SOURCE_DIR': str(root)}), \
                    patch.object(dataset, 'check_sequence_availability', return_value='available'), \
                    patch.object(dataset, 'create_rgb_folder', side_effect=AssertionError('Must reuse images')), \
                    patch.object(dataset, 'download_sequence_data', side_effect=AssertionError('Must reuse sources')):
                dataset.download_sequence('offroad1')
            self.assertEqual((output / rows[0][1]).read_bytes(), original_image)
            upgraded = yaml.safe_load((output / 'calibration.yaml').read_text())
            self.assertEqual(upgraded, saved)
            native = root / 'offroad1_raw_radtan4'
            subprocess.run([str(python), str(LAB / 'Datasets/extra-files/extract_geode_stereo.py'),
                            '--bag', str(bag), '--calibration', str(calib), '--output', str(native), '--unrectified'],
                           check=True, env=env, capture_output=True, text=True)
            self.assertFalse((native / 'rectification.json').exists())
            for cam, side in enumerate(('left', 'right')):
                with (native / f'rgb_{cam}.csv').open() as stream:
                    rows = list(csv.reader(stream))[1:]
                for frame, row in enumerate(rows):
                    original = cv2.cvtColor(cv2.imread(str(root / f'source_{side}_{frame}.jpg')), cv2.COLOR_BGR2GRAY)
                    stored = cv2.imread(str(native / row[1]), cv2.IMREAD_GRAYSCALE)
                    np.testing.assert_array_equal(stored, original)
            with patch.dict(os.environ, {'GEODE_SOURCE_DIR': str(root)}):
                dataset.create_calibration_yaml('offroad1_raw_radtan4')
            fit = json.loads((native / 'radtan4_fit.json').read_text())
            calibration = yaml.safe_load((native / 'calibration.yaml').read_text())
            T_BI = np.array(calibration['imus'][0]['T_BS']).reshape(4, 4)
            source = read_calibration(calib)
            for i, camera in enumerate(calibration['cameras']):
                self.assertEqual(camera['distortion_type'], 'radtan4')
                self.assertEqual(len(camera['distortion_coefficients']), 4)
                self.assertGreater(np.linalg.norm(camera['distortion_coefficients']), .01)
                selected = fit['cameras'][i]['candidates']['refit_intrinsics']
                self.assertEqual(camera['distortion_coefficients'], selected['D'])
                original_T = matrix(source['transforms']['T_IMU_CamL' if i == 0 else 'T_IMU_CamR'])
                np.testing.assert_allclose(np.linalg.inv(T_BI) @ np.array(camera['T_BS']).reshape(4, 4), original_T, atol=1e-12)
            dataset.cfg['assets']['calibration']['sha256'] = 'wrong calibration'
            with patch.dict(os.environ, {'GEODE_SOURCE_DIR': str(root)}), self.assertRaisesRegex(ValueError, 'different source calibration'):
                dataset.create_calibration_yaml('offroad1')


if __name__ == '__main__':
    unittest.main()
