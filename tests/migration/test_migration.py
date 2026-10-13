import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'external/VSLAM-LAB')]
from dataset_inputs import experiment_inputs, dataset_at_root
from Datasets.dataset_files.dataset_botanicgarden import stereo_pairs, matrix, BotanicgardenDataset
from Datasets.DatasetVSLAMLAB_calibration import _get_imu_yaml_section


def read_rows(path):
    import csv
    with path.open() as stream:
        return list(csv.reader(stream))[1:]


class MigrationTests(unittest.TestCase):
    def test_grandtour_interrupted_image_folder_is_rebuilt(self):
        from PIL import Image
        from Datasets.dataset_files.dataset_grandtour import GrandtourAlphasenseDataset
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = GrandtourAlphasenseDataset(); d.dataset_path = root / 'data'
            d.target_resolution = [4, 2]
            source = root / 'source'; source.mkdir()
            for i in range(2):
                Image.new('L', (8, 4), i).save(source / f'{i:06d}.png')
            folder = d.sequence_path('kaeb_1'); (folder / 'rgb_0').mkdir(parents=True)
            (folder / 'rgb_0/000000.png').write_bytes(b'interrupted PNG')
            (folder / '.import_pending').touch()
            self.assertEqual(d.check_sequence_availability('kaeb_1', False), 'non-available')
            with patch.object(d, '_image_dir', return_value=source):
                d.create_rgb_folder('kaeb_1')
            for cam in range(2):
                self.assertTrue((folder / f'.rgb_complete_{cam}').exists())
                for i in range(2):
                    with Image.open(folder / f'rgb_{cam}/{i:06d}.png') as image:
                        self.assertEqual(image.size, (4, 2))

    def test_botanic_failed_download_can_be_retried_without_manual_work(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / 'downloads'; local.mkdir()
            (local / '1018_13_VLIO.bag.part').write_bytes(b'partial')
            d = BotanicgardenDataset(); d.dataset_path = root / 'data'
            d.cfg['calibration_files'] = {}
            with patch.dict(os.environ, {'BOTANICGARDEN_SOURCE_DIR': str(local)}), \
                 patch('Datasets.dataset_files.dataset_botanicgarden.downloadFile', side_effect=OSError('connection lost')):
                with self.assertRaises(OSError):
                    d.download_sequence_data('1018_13')
            self.assertEqual(d.check_sequence_availability('1018_13', False), 'non-available')
            def complete(url, destination, size, *, filename, checksum):
                path = Path(destination) / filename
                path.write_bytes(b'complete')
                path.with_name(path.name + '.part').unlink(missing_ok=True)
                return str(path)
            with patch.dict(os.environ, {'BOTANICGARDEN_SOURCE_DIR': str(local)}), \
                 patch('Datasets.dataset_files.dataset_botanicgarden.downloadFile', side_effect=complete):
                d.download_sequence_data('1018_13')
            files = json.loads((d.sequence_path('1018_13') / 'sources.json').read_text())['files']
            self.assertEqual(files['1018_13_VLIO.bag'], str(local / '1018_13_VLIO.bag'))
            self.assertFalse((d._raw() / '1018_13_VLIO.bag').exists())

    def test_dropped_right_frame_does_not_shift_stereo(self):
        left = [[100,'l0'], [200,'l1'], [300,'l2']]
        right = [[100,'r0'], [300,'r2']]
        self.assertEqual(stereo_pairs(left,right,0), [[100,'l0',100,'r0'],[300,'l2',300,'r2']])
        with self.assertRaises(ValueError):
            stereo_pairs(left,[[100,'r'],[100,'r']],0)

    def test_calibration_rejects_nonrigid(self):
        T=np.eye(4);T[0,0]=2
        with self.assertRaises(ValueError):
            matrix({'rows':4,'cols':4,'data':T.ravel()})

    def test_gt_body_transform_and_explicit_nonfinite_mask(self):
        import csv, json
        with tempfile.TemporaryDirectory() as tmp:
            d=BotanicgardenDataset();d.dataset_path=Path(tmp)
            raw=d._raw();(raw/'calib/extrinsics').mkdir(parents=True)
            folder=d.sequence_path('1018_00');folder.mkdir()
            (raw/'gt_1018_00_qnew.bag').touch()
            T=np.eye(4);T[:3,3]=[1,0,0]
            (raw/'calib/extrinsics/calib_chain.yaml').write_text(yaml.safe_dump({
                'T_xsens_vlp16':{'rows':4,'cols':4,'data':T.ravel().tolist()}}))
            q=[0,0,2**-.5,2**-.5]
            with (folder/'groundtruth_vlp16.csv').open('w') as f:
                w=csv.writer(f);w.writerow(['ts','x','y','z','qx','qy','qz','qw'])
                for i in range(4):w.writerow([i+1,10,20,30,*([float('nan')]*4 if i==1 else q)])
            with patch.object(d,'_ros'):
                d.create_groundtruth_csv('1018_00')
            rows=read_rows(folder/'groundtruth.csv')
            self.assertEqual([int(r[0]) for r in rows],[1,3,4])
            np.testing.assert_allclose([float(x) for x in rows[0][1:4]],[10,19,30])
            meta=json.loads((folder/'reference_metadata.json').read_text())
            self.assertEqual(meta['rejected_nonfinite_pose_timestamps_ns'],[2])
            self.assertTrue((folder/'groundtruth_vlp16.csv').exists())

    def test_missing_imu_priors_remain_absent(self):
        text='\n'.join(_get_imu_yaml_section({'imu_name':'imu_0','sigma_g_c':.0002,'T_BS':np.eye(4)}))
        self.assertIn('sigma_g_c',text)
        self.assertNotIn('sigma_bg',text)
        self.assertNotIn('g_max',text)

    def test_prepare_and_runner_share_selection_and_machine_path(self):
        with patch.dict(os.environ, {'VIO_DATA_DIR':'/tmp/custom data'}):
            _,_,_,pairs=experiment_inputs(ROOT/'configs/experiments/botanicgarden_1018_00_orbslam3.yaml')
            self.assertEqual(pairs,[('botanicgarden','1018_00')])
            d=dataset_at_root(pairs[0][0])
            self.assertEqual(d.sequence_path(pairs[0][1]),Path('/tmp/custom data/VSLAM-LAB-Benchmark/BOTANICGARDEN/1018_00'))

    def test_only_owned_incomplete_import_can_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=BotanicgardenDataset();d.dataset_path=Path(tmp)
            folder=d.sequence_path('1018_00');folder.mkdir();(folder/'rgb_0').mkdir()
            self.assertEqual(d.check_sequence_availability('1018_00',False),'corrupted')
            (folder/'sources.json').write_text('{}')
            self.assertEqual(d.check_sequence_availability('1018_00',False),'non-available')

    def test_real_ros1_helpers_preserve_header_stamps_and_dropped_frame(self):
        import csv, subprocess
        from utilities import run_rosbag_frame_extraction
        with tempfile.TemporaryDirectory(prefix='vio bag fixture ') as tmp:
            folder=Path(tmp);bag=folder/'fixture.bag'
            d=BotanicgardenDataset();d.dataset_path=folder
            seq=d.sequence_path('1018_00');seq.mkdir()
            env=os.environ.copy();env.pop('PYTHONPATH',None)
            subprocess.run(['pixi','run','--frozen','-e','ros1','python',
                            str(ROOT/'tests/migration/fixtures/write_ros1_bag.py'),str(bag)],
                           cwd=ROOT/'external/VSLAM-LAB',env=env,check=True,capture_output=True)
            for cam,side in enumerate(['left','right']):
                run_rosbag_frame_extraction('ros1',bag,seq,f'/dalsa_gray/{side}/image_raw',cam,
                                           header_stamp=True,strict=True,separate_csv=True)
            d.create_rgb_csv('1018_00')
            rows=read_rows(seq/'rgb.csv')
            self.assertEqual([int(r[0]) for r in rows],[1000000000,1200000000])
            self.assertEqual([int(r[2]) for r in rows],[1000000000,1200000000])
            d._ros('extract_rosbag_imu.py','--rosbag_path',bag,'--sequence_path',seq,
                   '--imu_topic','/imu/data','--strict')
            imu=read_rows(seq/'imu_0.csv')
            self.assertEqual(int(imu[0][0]),900000000)
            # A completed extractor does not rerun or duplicate timestamps.
            self.assertFalse(run_rosbag_frame_extraction('ros1',bag,seq,'/unused',0,
                            header_stamp=True,strict=True,separate_csv=True))

    def test_named_download_resume_and_range_ignored(self):
        import hashlib, threading
        from http.server import HTTPServer,BaseHTTPRequestHandler
        from utilities import downloadFile
        payload=b'0123456789'*100
        for ignore in [False,True]:
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    start=0 if ignore else int(self.headers.get('Range','bytes=0-').split('=')[1].split('-')[0])
                    self.send_response(206 if start else 200)
                    if start:self.send_header('Content-Range',f'bytes {start}-{len(payload)-1}/{len(payload)}')
                    self.send_header('Content-Length',str(len(payload)-start));self.end_headers()
                    self.wfile.write(payload[start:])
                def log_message(self,*args):pass
            server=HTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    folder=Path(tmp);(folder/'bag.part').write_bytes(payload[:300])
                    result=downloadFile(f'http://127.0.0.1:{server.server_port}/content',tmp,len(payload),
                                        filename='bag',checksum='md5:'+hashlib.md5(payload).hexdigest())
                    self.assertEqual(Path(result).read_bytes(),payload)
                    self.assertFalse((folder/'bag.part').exists())
                    with self.assertRaises(ValueError):
                        downloadFile(f'http://127.0.0.1:{server.server_port}/content',tmp,len(payload),
                                     filename='wrong',checksum='md5:'+'0'*32)
                    self.assertFalse((folder/'wrong').exists())
                    self.assertTrue((folder/'wrong.part').exists())
            finally:
                server.shutdown();thread.join();server.server_close()

    def test_storage_preflight_blocks_framework_download(self):
        import prepare_datasets as preparation
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            selection=root/'sequences.yaml';selection.write_text('grandtour-alphasense:\n  - kaeb_1\n')
            config=root/'experiment.yaml';config.write_text(yaml.safe_dump({'experiment':{
                'Config':str(selection),'Preparation':{'max_data_gb':.001,'reserve_gb':0}}}))
            from Datasets.dataset_files.dataset_grandtour import GrandtourAlphasenseDataset
            with patch.dict(os.environ,{'VIO_DATA_DIR':str(root/'data')}), \
                 patch.object(sys,'argv',['prepare_datasets.py','prepare','--config',str(config)]), \
                 patch.object(preparation,'preparation_estimate',return_value=2_000_000_000), \
                 patch.object(GrandtourAlphasenseDataset,'download_sequence') as download:
                with self.assertRaisesRegex(RuntimeError,'Storage preflight failed'):
                    preparation.main()
                download.assert_not_called()
