"""Effective geometry, noise and output-frame contracts for SchurVINS."""
import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parents[2]
A=ROOT/'external/VSLAM-LAB/Baselines/extra-files/schurvins'
spec=importlib.util.spec_from_file_location('schurvins_adapter',A/'run.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
class SchurVinsTests(unittest.TestCase):
    def fixture(self):
        TBI=np.eye(4);TBI[:3,:3]=Rotation.from_euler('xyz',[.2,-.1,.3]).as_matrix();TBI[:3,3]=[.4,.1,-.2]
        cameras=[]
        for i in [0,1]:
            TIC=np.eye(4);TIC[:3,3]=[.02,.1*i,.03]
            cameras.append(dict(cam_name=f'rgb_{i}',cam_model='pinhole',distortion_type='radtan4',distortion_coefficients=[.1,-.01,.001,.002],focal_length=[500.,501.],principal_point=[320.,240.],image_dimension=[640,480],T_BS=(TBI@TIC).ravel().tolist()))
        imu=dict(imu_name='imu_0',T_BS=TBI.ravel().tolist(),fps=100.,g=9.80665,sigma_g_c=.005,sigma_gw_c=.0001,sigma_a_c=.006,sigma_aw_c=.0002)
        return dict(cameras=cameras,imus=[imu]),adapter.read_yaml(A/'vslamlab_schurvins_settings.yaml'),TBI
    def test_camera_imu_chain_noise_and_gravity_reach_native(self):
        c,s,TBI=self.fixture();before=copy.deepcopy((c,s));n,settings,_=adapter.native_settings(c,s,Path('/tmp/out'))
        for i,cam in enumerate(n['cameras']):
            TIC=np.array(cam['T_B_C']['data']).reshape(4,4)
            np.testing.assert_allclose(TBI@TIC,np.array(c['cameras'][i]['T_BS']).reshape(4,4),atol=1e-12)
            self.assertEqual(cam['camera']['intrinsics']['data'],[500.,501.,320.,240.])
            self.assertEqual(cam['camera']['distortion']['parameters']['data'],[.1,-.01,.001,.002])
        self.assertEqual(n['imu_params']['sigma_omega_c'],.005);self.assertEqual(n['imu_params']['sigma_acc_bias_c'],.0002)
        self.assertEqual(n['imu_params']['g'],9.80665);self.assertEqual(n['imu_params']['imu_rate'],100.)
        self.assertEqual((c,s),before);self.assertFalse(settings['use_ceres_backend'])
    def test_output_body_pose_with_rotated_imu_and_lever_arm(self):
        _,_,TBI=self.fixture();TWB=np.eye(4);TWB[:3,:3]=Rotation.from_euler('xyz',[.4,.2,-.5]).as_matrix();TWB[:3,3]=[2,3,4]
        TWI=TWB@TBI;v=np.array([[*TWI[:3,3],*Rotation.from_matrix(TWI[:3,:3]).as_quat()]])
        out=adapter.imu_to_body(v,TBI)
        np.testing.assert_allclose(out[0,:3],TWB[:3,3],atol=1e-12)
        np.testing.assert_allclose(Rotation.from_quat(out[0,3:]).as_matrix(),TWB[:3,:3],atol=1e-12)
    def test_radtan5_is_rejected(self):
        c,s,_=self.fixture();c['cameras'][0]['distortion_type']='radtan5'
        with self.assertRaises(ValueError):adapter.native_settings(c,s,Path('/tmp/out'))
    def test_ceres_backend_or_loop_closure_cannot_replace_schur_filter(self):
        for key in ['use_ceres_backend','runlc']:
            c,s,_=self.fixture();s[key]=True
            with self.assertRaises(ValueError):adapter.native_settings(c,s,Path('/tmp/out'))
