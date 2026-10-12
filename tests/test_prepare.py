import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import subprocess
import sys
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
from PIL import Image
from rosbags.rosbag1 import Writer
from rosbags.typesys import Stores, get_typestore
import yaml
import zarr

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/prepare.py'
spec = importlib.util.spec_from_file_location('prepare', SCRIPT)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def tar_folder(folder, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, 'w') as t:
        t.add(folder, arcname=folder.name)


def matrix(m):
    return {'rows': 4, 'cols': 4, 'data': np.asarray(m).ravel().tolist()}


def record(parent, child, xyz=(0, 0, 0)):
    return {'base_frame_id': parent, 'child_frame_id': child,
            'translation': dict(zip(['x', 'y', 'z'], xyz)),
            'rotation': {'x': 0, 'y': 0, 'z': 0, 'w': 1}}


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_timestamps_and_checksums(self):
        self.assertEqual(p.timestamps_ns([1.1, 1.2]).tolist(), [1100000000, 1200000000])
        for times in [[1, 1], [2, 1], [float('nan'), 2]]:
            with self.assertRaises(ValueError):
                p.timestamps_ns(times)
        path = self.root / 'file'
        path.write_bytes(b'abc')
        p.checksum(path, 'md5:' + hashlib.md5(b'abc').hexdigest())
        p.checksum(path, 'git-sha1:' + hashlib.sha1(b'blob 3\0abc').hexdigest())
        with self.assertRaises(ValueError):
            p.checksum(path, 'sha256:' + '0'*64)

    def test_unsafe_tar_rejected(self):
        archive = self.root / 'bad.tar'
        with tarfile.open(archive, 'w') as t:
            m = tarfile.TarInfo('../escaped')
            m.size = 1
            t.addfile(m, io.BytesIO(b'x'))
        with self.assertRaises(ValueError):
            p.extract_tar(archive, self.root / 'extract')
        self.assertFalse((self.root / 'escaped').exists())

    def test_metadata_transforms_are_inverted(self):
        records = {'cam': record('body', 'cam', (-.2, 0, 0)),
                   'imu': record('body', 'imu', (-.1, 0, 0))}
        result = p.relative_transform(records, 'imu', 'cam')
        self.assertAlmostEqual(result[0, 3], .1)
        np.testing.assert_allclose(result @ p.relative_transform(records, 'cam', 'imu'), np.eye(4))
        with self.assertRaises(ValueError):
            p.relative_transform(records, 'unknown', 'cam')

    def test_download_resume_and_range_ignored(self):
        payload = b'0123456789'*100
        for ignore_range in [False, True]:
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    offset = 0 if ignore_range else int(self.headers.get('Range', 'bytes=0-').split('=')[1].split('-')[0])
                    self.send_response(206 if offset else 200)
                    if offset:
                        self.send_header('Content-Range', f'bytes {offset}-{len(payload)-1}/{len(payload)}')
                    self.send_header('Content-Length', str(len(payload)-offset))
                    self.end_headers()
                    self.wfile.write(payload[offset:])
                def log_message(self, *args):
                    pass
            server = HTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                path = self.root / f'download-{ignore_range}'
                path.with_name(path.name+'.part').write_bytes(payload[:100])
                asset = {'url': f'http://127.0.0.1:{server.server_port}/data',
                         'size': len(payload), 'checksum': 'sha256:'+hashlib.sha256(payload).hexdigest()}
                p.download(asset, path, 0)
                self.assertEqual(path.read_bytes(), payload)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_grandtour_export(self):
        raw, out, store = self.root / 'raw', self.root / 'out', self.root / 'zarr'
        out.mkdir()
        attrs = {
            'adis_imu': {'frame_id': 'imu'},
            'cpt7_ie_tc_odometry': {'frame_id': 'enu_origin'},
            'cpt7_ie_tc_tf': {'transform': record('body', 'ref')},
            'tf': {'tf': {'imu': record('body', 'imu'), 'left': record('body', 'left', (-.1, 0, 0)),
                          'right': record('body', 'right', (-.2, 0, 0)), 'ref': record('body', 'ref')}},
            'prism_position': {'description': 'position only'},
        }
        arrays = {
            'adis_imu': {'timestamp': [1000., 1000.1, 1000.2, 1000.3],
                         'ang_vel': np.zeros((4, 3)), 'lin_acc': np.tile([0, 0, 9.81], (4, 1))},
            'cpt7_ie_tc_odometry': {'timestamp': [1000., 1000.3], 'pose_pos': [[0, 0, 0], [1, 0, 0]],
                                   'pose_orien': [[0, 0, 0, 1]]*2, 'pose_cov': np.zeros((2, 6, 6))},
            'prism_position': {'timestamp': [1000., 1000.3], 'position': [[0, 0, 0], [1, 0, 0]]},
            'cpt7_ie_tc_tf': {}, 'tf': {},
        }
        for cam, key in enumerate(['zed2i_left_images', 'zed2i_right_images']):
            attrs[key] = {'camera_info': {'K': [2, 0, 2, 0, 2, 1, 0, 0, 1], 'D': [0]*4,
                                          'distortion_model': 'radtan', 'width': 4, 'height': 3,
                                          'frame_id': 'left' if cam == 0 else 'right'}}
            arrays[key] = {'timestamp': [1000.05+cam*.001, 1000.25+cam*.001], 'sequence_id': [41, 43]}
            image_dir = self.root / 'images' / key
            image_dir.mkdir(parents=True)
            for i in range(2):
                Image.new('RGB', (4, 3), (i*20, 10, 30)).save(image_dir / f'{i:06d}.jpeg')
            tar_folder(image_dir, raw / f'images/{key}.tar')
        files = []
        for key, values in arrays.items():
            group = zarr.open_group(str(store/key), mode='w')
            group.attrs.update(attrs[key])
            for k, value in values.items():
                group.create_dataset(k, data=np.asarray(value))
            dest = raw / f'data/{key}.tar'
            tar_folder(store/key, dest)
            files.append({'path': f'data/{key}.tar'})
        p.grandtour({'files': files, 'resolution': [4, 3], 'duration_bound_s': 1, 'image_rate_bound': 15}, raw, out)
        summary = p.validate(out)
        self.assertEqual(summary['cam0']['count'], 2)
        self.assertEqual(summary['imu']['count'], 4)
        self.assertAlmostEqual(summary['stereo_nearest_timestamp_difference_ms']['median'], 1)
        self.assertEqual(json.loads((out/'reference/metadata.json').read_text())['world_frame'], 'enu_origin')
        cam = yaml.safe_load((out/'mav0/cam0/sensor.yaml').read_text())
        self.assertAlmostEqual(cam['T_BS']['data'][3], .1)
        self.assertFalse((out/'_zarr').exists())
        # Boundary frames retained, not hidden or extrapolated; common window reported.
        rows = p.load_csv(out/'mav0/imu0/data.csv')
        p.csv_write(out/'mav0/imu0/data.csv', ['#timestamp', 'wx', 'wy', 'wz', 'ax', 'ay', 'az'], rows[:3])
        summary = p.validate(out)
        self.assertEqual(summary['imu']['camera_frames_without_IMU_bracketing'], [1, 1])

    def test_botanicgarden_export(self):
        raw, out = self.root/'raw', self.root/'out'
        raw.mkdir()
        out.mkdir()
        ts = get_typestore(Stores.ROS1_NOETIC)
        types = ts.types
        def header(t):
            return types['std_msgs/msg/Header'](0, types['builtin_interfaces/msg/Time'](t//10**9, t%10**9), 'xsens')
        def v(x, y, z):
            return types['geometry_msgs/msg/Vector3'](float(x), float(y), float(z))
        def q():
            return types['geometry_msgs/msg/Quaternion'](0., 0., 0., 1.)
        with Writer(raw/'fixture_VLIO.bag') as writer:
            connections = [writer.add_connection(topic, 'sensor_msgs/msg/Image', typestore=ts) for topic in p.CAM_TOPICS]
            ic = writer.add_connection('/imu/data', 'sensor_msgs/msg/Imu', typestore=ts)
            for t in [10**9, 1100000000, 1200000000, 1300000000]:
                msg = types['sensor_msgs/msg/Imu'](header(t), q(), np.zeros(9), v(0, 0, 0), np.zeros(9), v(0, 0, 9.81), np.zeros(9))
                writer.write(ic, t, ts.serialize_ros1(msg, ic.msgtype))
            for t in [1050000000, 1250000000]:
                for connection in connections:
                    msg = types['sensor_msgs/msg/Image'](header(t), 3, 4, 'mono8', 0, 6,
                                                         np.arange(18, dtype=np.uint8))
                    writer.write(connection, t, ts.serialize_ros1(msg, connection.msgtype))
        gt = self.root/'gt.bag'
        with Writer(gt) as writer:
            c = writer.add_connection('/gt_poses', 'geometry_msgs/msg/PoseStamped', typestore=ts)
            for t in [10**9, 1300000000]:
                pose = types['geometry_msgs/msg/Pose'](types['geometry_msgs/msg/Point'](0., 0., 0.), q())
                msg = types['geometry_msgs/msg/PoseStamped'](header(t), pose)
                writer.write(c, t, ts.serialize_ros1(msg, c.msgtype))
        with zipfile.ZipFile(raw/'GT_pose_qnew.zip', 'w') as z:
            z.write(gt, 'GT_pose_qnew/gt_fixture_qnew.bag')
        for folder in ['camera_intrinsics', 'extrinsics', 'imu_intrinsics']:
            (raw/'calib'/folder).mkdir(parents=True)
        for cam in range(2):
            calib = {'image_width': 4, 'image_height': 3,
                     'projection_parameters': {'fx': 2, 'fy': 2, 'cx': 2, 'cy': 1},
                     'distortion_parameters': {'k1': 0, 'k2': 0, 'p1': 0, 'p2': 0}}
            (raw/f'calib/camera_intrinsics/dalsa_gray{cam}_down.yaml').write_text(yaml.safe_dump(calib))
        stereo = np.eye(4)
        stereo[0, 3] = .25
        chain = {'T_xsens_gray0': matrix(np.eye(4)), 'T_gray0_gray1': matrix(stereo),
                 'T_xsens_vlp16': matrix(np.eye(4))}
        (raw/'calib/extrinsics/calib_chain.yaml').write_text(yaml.safe_dump(chain))
        (raw/'calib/imu_intrinsics/xsens_imu_param.yaml').write_text('noise: 0.01\n')
        p.botanicgarden({'sequence': 'fixture', 'resolution': [4, 3], 'duration_bound_s': 1, 'image_rate_bound': 10}, raw, out)
        summary = p.validate(out)
        self.assertEqual(summary['cam0']['count'], 2)
        image = Image.open(out/'mav0/cam0/data/1050000000.png')
        np.testing.assert_array_equal(np.array(image), np.arange(18).reshape(3, 6)[:, :4])
        image.close()
        meta = json.loads((out/'reference/metadata.json').read_text())
        self.assertFalse(meta['independent_of_visual_frontend'])
        self.assertFalse((out/'_reference.bag').exists())

    def test_config_selection_and_paths(self):
        config = self.root / 'prepare.yaml'
        config.write_text('data_dir: relative-data\nmax_data_gb: 125\nreserve_gb: 15\n'
                          'sequences:\n  second: true\n  first: false\n  third: true\n')
        settings = p.load_config(config, ['first', 'second', 'third'])
        self.assertEqual(settings['sequences'], ['second', 'third'])
        self.assertEqual(settings['data_dir'], self.root / 'relative-data')
        self.assertEqual(settings['max_data_gb'], 125)
        config.write_text(config.read_text().replace('relative-data', '~/datasets/vio_research'))
        self.assertEqual(p.load_config(config, ['first', 'second', 'third'])['data_dir'],
                         Path.home() / 'datasets/vio_research')

    def test_invalid_configs(self):
        config = self.root / 'bad.yaml'
        base = 'data_dir: data\nmax_data_gb: 125\nreserve_gb: 15\nsequences:\n  known: true\n'
        for text in [base.replace('known: true', 'known: "false"'),
                     base.replace('known: true', 'unknown: true'),
                     base + 'max_data_gb: 200\n',
                     base.replace('known: true', 'known: true\n  known: false'),
                     base.replace('125', '.nan'), base.replace('125', 'false'),
                     base.replace('reserve_gb: 15', 'reserve_gb: -1'),
                     base.replace('data_dir: data', 'data_dir: ""'), base + 'typo: 1\n']:
            with self.subTest(text=text):
                config.write_text(text)
                with self.assertRaises(ValueError):
                    p.load_config(config, ['known'])

    def test_cli_reads_only_yaml_and_rejects_empty_selection(self):
        config = self.root / 'cli.yaml'
        data = self.root / 'selected-data'
        config.write_text('data_dir: selected-data\nmax_data_gb: .001\nreserve_gb: 0\n'
                          'sequences:\n  grandtour-alb2: false\n  grandtour-trim1: true\n')
        result = subprocess.run([sys.executable, str(SCRIPT), 'plan', '--config', str(config)],
                                capture_output=True, text=True)
        # A tiny YAML budget stops before downloading, after showing the effective selection.
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('grandtour-trim1: sources', result.stdout)
        self.assertNotIn('grandtour-alb2: sources', result.stdout)
        self.assertIn(str(data), result.stdout)
        self.assertIn('budget 0.0 GB', result.stderr)
        self.assertFalse((data / 'raw').exists())
        config.write_text(config.read_text().replace('grandtour-trim1: true', 'grandtour-trim1: false')
                         .replace('selected-data', 'unused-data'))
        result = subprocess.run([sys.executable, str(SCRIPT), 'plan', '--config', str(config)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('No active sequences', result.stderr)
        self.assertFalse((self.root / 'unused-data').exists())

    def test_removed_cli_and_make_overrides_rejected(self):
        for option, value in [('--data-dir', str(self.root / 'forbidden-data')),
                              ('--sequences', 'grandtour-trim1'),
                              ('--max-data-gb', '100'), ('--reserve-gb', '0')]:
            with self.subTest(option=option):
                result = subprocess.run([sys.executable, str(SCRIPT), 'plan', option, value],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn('unrecognized arguments', result.stderr)
        self.assertFalse((self.root / 'forbidden-data').exists())
        for option in ['DATA_DIR', 'SEQUENCES', 'MAX_DATA_GB', 'RESERVE_GB']:
            with self.subTest(option=option):
                result = subprocess.run(['make', '-n', 'plan', f'{option}=unused'],
                                        cwd=SCRIPT.parents[1], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f'{option} is no longer supported', result.stderr)

    def test_space_budget_rejects(self):
        specs = {'sequence': {'files': [], 'duration_bound_s': 100, 'image_rate_bound': 30, 'resolution': [1920, 1080]}}
        with self.assertRaises(RuntimeError):
            p.preflight(self.root, specs, 10, 0)


if __name__ == '__main__':
    unittest.main()
