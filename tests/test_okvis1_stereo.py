"""OKVIS 1 frame conversion and timestamp preservation, without a native build."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.spatial.transform import Rotation
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('okvis1_adapter', ROOT /
    'external/VSLAM-LAB/Baselines/extra-files/okvis1/run.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class OKVIS1AdapterTests(unittest.TestCase):
    def inputs(self):
        settings = adapter.read_yaml(adapter.ADAPTER / 'vslamlab_okvis1_settings.yaml')
        imu_transform = np.eye(4)
        imu_transform[:3, :3] = Rotation.from_euler('z', 35, degrees=True).as_matrix()
        imu_transform[:3, 3] = [1., 2., 3.]
        cameras = []
        for name, x in [('rgb_0', 0.), ('rgb_1', 0.25)]:
            pose = np.eye(4)
            pose[0, 3] = x
            cameras.append(dict(cam_name=name, cam_model='pinhole', distortion_type='equid4',
                distortion_coefficients=[0.] * 4, focal_length=[300., 300.],
                principal_point=[320., 240.], image_dimension=[640, 480], fps=10.,
                T_BS=pose.ravel().tolist()))
        imu = dict(imu_name='imu_0', T_BS=imu_transform.ravel().tolist(), fps=200.,
                   g=9.81, sigma_g_c=0.001, sigma_a_c=0.01, sigma_gw_c=0.00001,
                   sigma_aw_c=0.0001)
        overrides = dict(a_max=176., g_max=7.8, sigma_bg=0.03, sigma_ba=0.1,
                         a0=[0., 0., 0.], tau=3600.)
        return dict(cameras=cameras, imus=[imu]), settings, overrides

    def test_camera_relative_to_imu_and_body_frame_are_preserved(self):
        calibration, settings, overrides = self.inputs()
        original = copy.deepcopy(calibration)
        native, names, imu = adapter.native_settings(calibration, settings, overrides)
        T_BI = np.array(native['imu_params']['T_BS']).reshape(4, 4)
        for camera, source in zip(native['cameras'], calibration['cameras']):
            T_IC = np.array(camera['T_SC']).reshape(4, 4)
            np.testing.assert_allclose(T_BI @ T_IC, np.array(source['T_BS']).reshape(4, 4), atol=1e-14)
        self.assertEqual(calibration, original)
        self.assertEqual(names, ['rgb_0', 'rgb_1'])
        self.assertEqual(imu, 'imu_0')
        self.assertEqual(native['cameras'][0]['distortion_type'], 'equidistant')
        self.assertEqual(native['imu_params']['sigma_g_c'], 0.001)

    def test_missing_priors_are_rejected(self):
        calibration, settings, _ = self.inputs()
        with self.assertRaises(KeyError):
            adapter.native_settings(calibration, settings, {})

    def test_native_yaml_is_readable_by_opencv_parameter_reader(self):
        import cv2
        calibration, settings, overrides = self.inputs()
        native, _, _ = adapter.native_settings(calibration, settings, overrides)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'native.yaml'
            path.write_text('%YAML:1.0\n---\n' + yaml.dump(
                native, Dumper=adapter.OpenCVDumper, sort_keys=False))
            storage = cv2.FileStorage(str(path), cv2.FILE_STORAGE_READ)
            try:
                self.assertTrue(storage.isOpened())
                self.assertEqual(storage.getNode('cameras').size(), 2)
                self.assertEqual(storage.getNode('cameras').at(0).getNode('T_SC').size(), 16)
                self.assertTrue(storage.getNode('imu_params').getNode('sigma_bg').isReal())
                self.assertTrue(storage.getNode('camera_params').getNode('camera_rate').isInt())
                self.assertTrue(storage.getNode('imu_params').getNode('imu_rate').isInt())
            finally:
                storage.release()

    def test_unsupported_distortion_is_not_truncated(self):
        calibration, settings, overrides = self.inputs()
        calibration['cameras'][0]['distortion_type'] = 'radtan5'
        calibration['cameras'][0]['distortion_coefficients'] = [0., 0., 0., 0., 0.1]
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            adapter.native_settings(calibration, settings, overrides)

    def test_manifest_keeps_exact_nanosecond_timestamps_and_rejects_desync(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'left.jpeg').touch()
            (root / 'right.jpeg').touch()
            stamps = [1731591381873021953 + n * 100000000 for n in range(3)]
            csv = root / 'rgb.csv'
            csv.write_text('ts_rgb_0 (ns),path_rgb_0,ts_rgb_1 (ns),path_rgb_1\n' +
                ''.join(f'{stamp},left.jpeg,{stamp + 1},right.jpeg\n' for stamp in stamps))
            manifest = root / 'images.tsv'
            self.assertEqual(adapter.write_manifest(root, csv, manifest, ['rgb_0', 'rgb_1'], .005), 3)
            self.assertEqual(int(manifest.read_text().split('\t')[0]), stamps[0])
            with self.assertRaisesRegex(ValueError, 'synchronization'):
                adapter.write_manifest(root, csv, manifest, ['rgb_0', 'rgb_1'], 1e-10)


if __name__ == '__main__':
    unittest.main()
