"""Geometry and effective-input contracts for the pinned sqrtVINS adapter."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import cv2
import numpy as np
from scipy.spatial.transform import Rotation
import yaml

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT/'external/VSLAM-LAB'
sys.path.insert(0, str(LAB))
spec = importlib.util.spec_from_file_location('sqrtvins_adapter', LAB/'Baselines/extra-files/sqrtvins/run.py')
adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)


class SqrtVinsTests(unittest.TestCase):
    def fixture(self):
        T_BI = np.eye(4); T_BI[:3,:3] = Rotation.from_euler('xyz',[.2,-.1,.3]).as_matrix()
        T_BI[:3,3] = [.4,.1,-.2]
        cameras = []
        for i in (0,1):
            T_IC = np.eye(4); T_IC[:3,3] = [.02,.1*i,.03]
            cameras.append(dict(cam_name=f'rgb_{i}',cam_model='pinhole',distortion_type='radtan4',
                distortion_coefficients=[.1,-.01,.001,.002],focal_length=[500.,501.],
                principal_point=[320.,240.],image_dimension=[640,480],T_BS=(T_BI@T_IC).ravel().tolist()))
        imu=dict(imu_name='imu_0',T_BS=T_BI.ravel().tolist(),fps=100.,g=9.80665,
                 sigma_g_c=.005,sigma_gw_c=.0001,sigma_a_c=.006,sigma_aw_c=.0002)
        settings=yaml.safe_load((LAB/'Baselines/extra-files/sqrtvins/vslamlab_sqrtvins_settings.yaml').read_text())
        return dict(cameras=cameras,imus=[imu]),settings,T_BI

    def test_published_intrinsics_noise_and_nonidentity_imu_frame_reach_native(self):
        calibration,settings,T_BI=self.fixture()
        result,cameras,imu,transform=adapter.native_settings(calibration,settings)
        for i in (0,1):
            expected=np.eye(4);expected[:3,3]=[.02,.1*i,.03]
            np.testing.assert_allclose(cameras[f'cam{i}']['T_imu_cam'],expected,atol=1e-12)
            self.assertEqual(cameras[f'cam{i}']['distortion_coeffs'],[.1,-.01,.001,.002])
        self.assertEqual(imu['imu0']['gyroscope_noise_density'],.005)
        self.assertEqual(result['gravity_mag'],9.80665)
        self.assertEqual(settings['init_dyn_bias_g'],[0,0,0])
        self.assertFalse(result['calib_cam_intrinsics'])

    def test_output_pose_recovers_body_with_rotated_imu_and_lever_arm(self):
        _,_,T_BI=self.fixture()
        body=np.eye(4);body[:3,:3]=Rotation.from_euler('xyz',[.4,.2,-.5]).as_matrix();body[:3,3]=[2,3,4]
        imu=body@T_BI
        values=np.array([[*imu[:3,3],*Rotation.from_matrix(imu[:3,:3]).as_quat()]])
        result=adapter.imu_to_body(values,T_BI)
        np.testing.assert_allclose(result[0,:3],body[:3,3],atol=1e-12)
        np.testing.assert_allclose(Rotation.from_quat(result[0,3:]).as_matrix(),body[:3,:3],atol=1e-12)

    def test_unsupported_distortion_and_online_calibration_are_rejected(self):
        c,s,_=self.fixture()
        c['cameras'][0]['distortion_type']='radtan5'
        with self.assertRaises(ValueError):adapter.native_settings(c,s)
        c,_,_=self.fixture();s['calib_cam_timeoffset']=True
        with self.assertRaises(ValueError):adapter.native_settings(c,s)

    def test_generated_yaml_is_readable_by_native_opencv_filestorage(self):
        c,s,_=self.fixture();_,cameras,_,_=adapter.native_settings(c,s)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'camera.yaml';adapter.write_opencv_yaml(path,cameras)
            f=cv2.FileStorage(str(path),cv2.FILE_STORAGE_READ)
            self.assertTrue(f.isOpened())
            cam=f.getNode('cam0');self.assertEqual(cam.getNode('distortion_model').string(),'radtan')
            self.assertEqual(cam.getNode('resolution').at(0).real(),640)
            self.assertAlmostEqual(cam.getNode('T_imu_cam').at(0).at(3).real(),.02)
            f.release()


if __name__=='__main__':unittest.main()
