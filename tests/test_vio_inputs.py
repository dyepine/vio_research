import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_vio_inputs import camera_imu_window


class VioInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.images = [[i, f'rgb_0/{i}.png', i, f'rgb_1/{i}.png'] for i in range(102)]
        self.imu = [[i, 0, 0, 0, 0, 0, 9.8] for i in range(102)]
        self.save()

    def save(self):
        for name, rows in [('rgb.csv', self.images), ('imu_0.csv', self.imu)]:
            with (self.folder / name).open('w') as stream:
                writer = csv.writer(stream)
                writer.writerow(['timestamp', 'values'])
                writer.writerows(rows)

    def test_boundary_window_without_reference(self):
        selected, audit = camera_imu_window(self.folder)
        self.assertEqual(len(selected), 100)
        self.assertEqual(audit['framework_rgb_idx_inclusive'], [1, 100])
        self.assertEqual(audit['frame_interval'], [1, 101])
        self.assertFalse((self.folder / 'groundtruth.csv').exists())

    def test_nonmonotonic(self):
        self.imu[5][0] = self.imu[4][0]
        self.save()
        with self.assertRaisesRegex(ValueError, 'Non-monotonic'):
            camera_imu_window(self.folder)

    def test_nonfinite(self):
        self.imu[5][1] = 'nan'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            camera_imu_window(self.folder)

    def test_short_interval(self):
        self.images = self.images[:50]
        self.save()
        with self.assertRaisesRegex(ValueError, 'too short'):
            camera_imu_window(self.folder)

    def test_empty_stream(self):
        self.images = []
        self.save()
        with self.assertRaisesRegex(ValueError, 'Empty'):
            camera_imu_window(self.folder)
