"""Stereo adapter geometry regressions, without a GPU or model weights."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.spatial.transform import Rotation
import yaml

spec = importlib.util.spec_from_file_location(
    'droid_stereo', Path(__file__).resolve().parents[1] /
    'external/VSLAM-LAB/Baselines/extra-files/droidslam/vslamlab_droidslam_stereo.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class DroidStereoGeometryTests(unittest.TestCase):
    def test_export_restores_metric_scale_and_original_camera_axes(self):
        # A rectified camera looking along rotated axes, 2 internal units away.
        rectification = Rotation.from_euler('z', 30, degrees=True)
        poses = np.array([[2., 0., 0., *rectification.inv().as_quat()]])
        result = adapter.metric_left_camera_poses(poses, 0.25, rectification.as_matrix())
        np.testing.assert_allclose(result[0, :3], [5., 0., 0.])
        np.testing.assert_allclose(Rotation.from_quat(result[0, 3:]).as_matrix(), np.eye(3), atol=1e-12)
        self.assertEqual(poses[0, 0], 2.)

    def test_rectification_for_radtan_and_fisheye_preserves_physical_baseline(self):
        for distortion in ['radtan4', 'equid4']:
            with self.subTest(distortion=distortion), tempfile.TemporaryDirectory() as tmp:
                cameras = []
                for name, x in [('rgb_0', 0.), ('rgb_1', 0.25)]:
                    transform = np.eye(4)
                    transform[0, 3] = x
                    cameras.append(dict(cam_name=name, cam_type='gray', cam_model='pinhole',
                        distortion_type=distortion, distortion_coefficients=[0., 0., 0., 0.],
                        focal_length=[300., 300.], principal_point=[320., 240.],
                        image_dimension=[640, 480], fps=10., T_BS=transform.ravel().tolist()))
                calibration = Path(tmp) / 'calibration.yaml'
                calibration.write_text(yaml.safe_dump({'cameras': cameras}))
                with contextlib.redirect_stdout(io.StringIO()):
                    K, left, right, baseline, rectification = adapter.load_calibration(calibration, 'rgb_0', 'rgb_1')
                self.assertAlmostEqual(baseline, 0.25)
                self.assertEqual(left[0].shape, (384, 512))
                self.assertTrue(np.isfinite(left[0]).all())
                self.assertTrue(np.isfinite(right[0]).all())
                np.testing.assert_allclose(rectification, np.eye(3), atol=1e-12)
                self.assertGreater(K[0, 0], 0)


if __name__ == '__main__':
    unittest.main()
