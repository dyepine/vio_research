"""Voxel-SVIO calibration/frame export checks independent of the native build."""
import copy
import importlib.util
from pathlib import Path
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('voxel_adapter', ROOT /
    'external/VSLAM-LAB/Baselines/extra-files/voxel_svio/run.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class VoxelCalibrationTests(unittest.TestCase):
    def inputs(self):
        imu_pose = np.eye(4)
        imu_pose[:3, :3] = Rotation.from_euler('z', .4).as_matrix()
        imu_pose[:3, 3] = [1., 2., 3.]
        cameras = []
        for name, x in [('rgb_0', 0.), ('rgb_1', .25)]:
            pose = np.eye(4)
            pose[0, 3] = x
            cameras.append(dict(cam_name=name, cam_model='pinhole', distortion_type='equid4',
                distortion_coefficients=[0.] * 4, focal_length=[300., 301.], principal_point=[320., 240.],
                image_dimension=[640, 480], T_BS=pose.ravel().tolist()))
        imu = dict(imu_name='imu_0', T_BS=imu_pose.ravel().tolist(), g=9.80665,
                   sigma_g_c=.001, sigma_a_c=.01, sigma_gw_c=.00001, sigma_aw_c=.0001)
        settings = adapter.read_yaml(adapter.ADAPTER / 'vslamlab_voxel_svio_settings.yaml')
        return dict(cameras=cameras, imus=[imu]), settings

    def test_native_camera_extrinsics_are_relative_to_imu_and_noise_is_not_squared(self):
        calibration, settings = self.inputs()
        before = copy.deepcopy(calibration)
        native, T_BI = adapter.native_settings(calibration, settings, Path('/tmp/output'))
        for camera, side in zip(calibration['cameras'], ['left', 'right']):
            T_IC = np.array(native['camera_parameter'][f'T_imu_cam_{side}']).reshape(4, 4)
            np.testing.assert_allclose(T_BI @ T_IC, np.array(camera['T_BS']).reshape(4, 4), atol=1e-14)
            self.assertEqual(native['camera_parameter'][f'distortion_model_{side}'], 'equidistant')
        self.assertEqual(native['imu_parameter']['gyroscope_noise_density'], .001)
        self.assertEqual(native['imu_parameter']['accelerometer_random_walk'], .0001)
        self.assertEqual(calibration, before)

    def test_body_pose_is_reconstructed_with_rotated_and_translated_imu(self):
        calibration, settings = self.inputs()
        _, T_BI = adapter.native_settings(calibration, settings, Path('/tmp/output'))
        T_WB = np.eye(4)
        T_WB[:3, :3] = Rotation.from_euler('xyz', [.1, .2, .3]).as_matrix()
        T_WB[:3, 3] = [4., 5., 6.]
        T_WI = T_WB @ T_BI
        values = np.array([[*T_WI[:3, 3], *Rotation.from_matrix(T_WI[:3, :3]).as_quat()]])
        result = adapter.imu_to_body(values, T_BI)
        np.testing.assert_allclose(result[0, :3], T_WB[:3, 3], atol=1e-14)
        np.testing.assert_allclose(Rotation.from_quat(result[0, 3:]).as_matrix(), T_WB[:3, :3], atol=1e-14)

    def test_unsupported_distortion_is_rejected_instead_of_dropping_coefficients(self):
        calibration, settings = self.inputs()
        calibration['cameras'][0]['distortion_type'] = 'radtan5'
        with self.assertRaisesRegex(ValueError, 'requires'):
            adapter.native_settings(calibration, settings, Path('/tmp/output'))
