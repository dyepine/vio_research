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
    def test_fomo_preflight_includes_retained_raw_and_resized_stereo(self):
        import prepare_datasets as preparation
        from Datasets.dataset_files.dataset_fomo import FomoDataset
        with tempfile.TemporaryDirectory() as tmp:
            dataset = FomoDataset(); dataset.dataset_path = Path(tmp)
            sequence = 'green_2025-06-26-11-20'
            prefix = dataset._recording_prefix(sequence)
            objects = {prefix: [(prefix + 'gt.txt', 100)],
                       prefix + 'zedx_left/': [(prefix + 'zedx_left/1.png', 5000)],
                       prefix + 'zedx_right/': [(prefix + 'zedx_right/1.png', 6000)],
                       prefix + 'calib/': [(prefix + 'calib/imu.json', 200)]}
            with patch.object(dataset, '_s3_list', side_effect=lambda key, **kw: objects[key]):
                estimate = preparation.preparation_estimate(dataset, sequence)
                expected_outputs = 2 * 640 * 480 * 3 * 1.05
                self.assertEqual(estimate, int(11300 + expected_outputs + 100_000_000))
                cached = dataset._raw_path(sequence) / 'zedx_left/1.png'
                cached.parent.mkdir(parents=True); cached.write_bytes(bytes(5000))
                self.assertEqual(preparation.preparation_estimate(dataset, sequence), estimate - 5000)


    def test_catalog_contains_all_public_sources_but_project_selects_two(self):
        d = BotanicgardenDataset()
        expected = {'1005_00', '1005_01', '1005_05', '1005_07', '1006_01',
                    '1006_03', '1008_01', '1008_03', '1018_00', '1018_13'}
        self.assertEqual(set(d.sequence_names), expected)
        for kind in ['bags', 'groundtruth_bags', 'durations_s']:
            self.assertEqual(set(d.cfg[kind]), expected)
        selection = yaml.safe_load((ROOT/'configs/datasets/selected.yaml').read_text())
        self.assertEqual(selection['botanicgarden'], ['1018_00', '1018_13'])

    def test_new_public_sequence_uses_sha256_and_only_its_own_assets(self):
        import hashlib
        from Datasets.dataset_files.dataset_botanicgarden import verified
        import prepare_datasets as preparation
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=BotanicgardenDataset();d.dataset_path=root/'data'
            d.cfg['calibration_files']={}
            with patch.dict(os.environ, {'BOTANICGARDEN_SOURCE_DIR':str(root/'local')}), \
                 patch('Datasets.dataset_files.dataset_botanicgarden.download_onedrive_file') as download:
                d.download_sequence_data('1005_05')
            self.assertEqual(download.call_count,2)
            self.assertEqual([c.kwargs['filename'] for c in download.call_args_list],
                             ['1005_05_VLIO.bag','gt_1005_05_qnew.bag'])
            self.assertEqual(download.call_args_list[0].kwargs['checksum'],
                             'sha256:'+d.cfg['bags']['1005_05']['sha256'])
            self.assertGreater(preparation.preparation_estimate(d,'1005_05'),d.cfg['bags']['1005_05']['size'])
            candidate=root/'small.bag';candidate.write_bytes(b'fixture')
            self.assertTrue(verified(candidate,{'size':7,'sha256':hashlib.sha256(b'fixture').hexdigest()}))

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
                 patch('Datasets.dataset_files.dataset_botanicgarden.download_onedrive_file', side_effect=OSError('connection lost')):
                with self.assertRaises(OSError):
                    d.download_sequence_data('1018_13')
            self.assertEqual(d.check_sequence_availability('1018_13', False), 'non-available')
            def complete(url, destination, size, *, filename, checksum, **kwargs):
                path = Path(destination) / filename
                path.write_bytes(b'complete')
                path.with_name(path.name + '.part').unlink(missing_ok=True)
                return str(path)
            with patch.dict(os.environ, {'BOTANICGARDEN_SOURCE_DIR': str(local)}), \
                 patch('Datasets.dataset_files.dataset_botanicgarden.download_onedrive_file', side_effect=complete):
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

    def test_native_settings_are_opencv_readable_and_variants_stay_separate(self):
        import cv2
        import vslamlab_utilities as native
        from dataset_inputs import write_method_settings
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stock = root / 'stock.yaml'
            stock.write_text('%YAML 1.2\n---\ncam_stereo: [rgb_0, rgb_1]\nFile.version: "1.0"\n')
            class Baseline:
                settings_yaml = stock
                def ensure_installed(self): pass
                def download_vslamlab_settings(self): return True
            changed = write_method_settings(Baseline(), {'loopClosing': 0}, root / 'changed.yaml')
            reader = cv2.FileStorage(str(changed), cv2.FILE_STORAGE_READ)
            try:
                self.assertEqual(reader.getNode('cam_stereo').at(1).string(), 'rgb_1')
                self.assertEqual(reader.getNode('File.version').string(), '1.0')
                self.assertEqual(reader.getNode('loopClosing').real(), 0)
            finally:
                reader.release()
            selection = root / 'sequences.yaml'
            selection.write_text('grandtour-alphasense: [kaeb_1]\n')
            recipe = {'Config': str(selection), 'Module': 'orbslam3', 'NumRuns': 2,
                      'Parameters': {'mode': 'stereo-vi'}}
            exp = root / 'experiment.yaml'
            exp.write_text(yaml.safe_dump({'stock': recipe,
                'changed': dict(recipe, MethodSettings=str(changed))}))
            seen = []
            def execute(it, experiment, baseline, dataset, sequence):
                seen.append((experiment.name, baseline.settings_yaml))
                return dict(duration_time=.001, success=True, comments='', ram=0, swap=0, gpu=0)
            with patch.object(native, 'VSLAMLAB_EVALUATION', root / 'results'), \
                 patch.object(native, 'get_baseline', side_effect=lambda _: Baseline()), \
                 patch.object(native, 'run_sequence', side_effect=execute):
                native.update_experiment_csv_logs(exp)
                native.run_exp(exp)
            self.assertCountEqual(seen, [('stock', stock), ('changed', changed)] * 2)
            self.assertNotIn('loopClosing', stock.read_text())

    def test_prepare_and_runner_share_selection_and_machine_path(self):
        with patch.dict(os.environ, {'VIO_DATA_DIR':'/tmp/custom data'}):
            _,_,_,pairs=experiment_inputs(ROOT/'configs/experiments/comparison.yaml')
            self.assertEqual(pairs,[('grandtour-alphasense','kaeb_1'), ('botanicgarden','1018_00')])
            d=dataset_at_root(pairs[1][0])
            self.assertEqual(d.sequence_path(pairs[1][1]),Path('/tmp/custom data/VSLAM-LAB-Benchmark/BOTANICGARDEN/1018_00'))

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
            config=root/'experiment.yaml';config.write_text(yaml.safe_dump({
                'Datasets': {'grandtour-alphasense': ['kaeb_1']},
                'Preparation': {'max_data_gb':.001,'reserve_gb':0}}))
            from Datasets.dataset_files.dataset_grandtour import GrandtourAlphasenseDataset
            with patch.dict(os.environ,{'VIO_DATA_DIR':str(root/'data')}), \
                 patch.object(sys,'argv',['prepare_datasets.py','prepare','--config',str(config)]), \
                 patch.object(preparation,'preparation_estimate',return_value=2_000_000_000), \
                 patch.object(GrandtourAlphasenseDataset,'download_sequence') as download:
                with self.assertRaisesRegex(RuntimeError,'Storage preflight failed'):
                    preparation.main()
                download.assert_not_called()

    def test_interrupted_transfer_resumes_every_saved_byte(self):
        import hashlib, threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from utilities import downloadFile
        payload = b'abcdefgh' * 40000
        offsets = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                offset = int(self.headers.get('Range', 'bytes=0-').split('=')[1].split('-')[0])
                offsets.append(offset)
                self.send_response(206 if offset else 200)
                if offset:
                    self.send_header('Content-Range', f'bytes {offset}-{len(payload)-1}/{len(payload)}')
                self.send_header('Content-Length', str(len(payload)-offset))
                self.end_headers()
                end = min(len(payload), offset + 12345)
                self.wfile.write(payload[offset:end])
                self.wfile.flush()
                self.close_connection = True
            def log_message(self, *args): pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch('utilities._DOWNLOAD_RETRY_DELAY_S', 0):
                path = downloadFile(f'http://127.0.0.1:{server.server_port}/file', tmp, len(payload),
                                    filename='bag', checksum='md5:'+hashlib.md5(payload).hexdigest(),
                                    resume_required=True, attempts=2)
                self.assertEqual(Path(path).read_bytes(), payload)
                self.assertEqual(offsets, list(range(0, len(payload), 12345)))
        finally:
            server.shutdown(); worker.join(); server.server_close()

    def test_range_ignored_preserves_partial_instead_of_restarting(self):
        import io
        from utilities import downloadFile, ResumeNotSupportedError
        class Response(io.BytesIO):
            status = 200
            headers = {}
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / 'bag.part'; part.write_bytes(b'saved bytes')
            with patch('utilities._open_download', return_value=Response(b'new bytes')):
                with self.assertRaises(ResumeNotSupportedError):
                    downloadFile('http://mirror/file', tmp, 1000, filename='bag',
                                 checksum='md5:'+'0'*32, resume_required=True)
            self.assertEqual(part.read_bytes(), b'saved bytes')

    def test_onedrive_refreshes_url_and_checks_file_identity(self):
        import io, json
        from utilities import download_onedrive_file
        requests = []
        def open_json(request, timeout):
            requests.append(request)
            result = {'token': 'ephemeral'} if request.full_url.endswith('/token') else {
                'name': 'bag', 'size': 1000, '@content.downloadUrl': 'https://download/file'}
            return io.BytesIO(json.dumps(result).encode())
        def download(resolver, directory, size, **kwargs):
            self.assertTrue(kwargs['resume_required'])
            self.assertEqual(resolver(), 'https://download/file')
            self.assertEqual(resolver(), 'https://download/file')
        with patch('utilities.urllib.request.urlopen', side_effect=open_json), \
             patch('utilities.downloadFile', side_effect=download):
            download_onedrive_file('https://1drv.ms/u/test', '/tmp', 1000,
                                   filename='bag', checksum='md5:'+'0'*32)
        self.assertEqual(len(requests), 4)
        with patch('utilities.urllib.request.urlopen', side_effect=open_json), \
             patch('utilities.downloadFile', side_effect=lambda resolver,*a,**k: resolver()):
            with self.assertRaisesRegex(ValueError, 'metadata differs'):
                download_onedrive_file('https://1drv.ms/u/test', '/tmp', 999,
                                       filename='bag', checksum='md5:'+'0'*32)

    def test_adapter_uses_onedrive_directly_for_bag_and_corrected_gt(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = BotanicgardenDataset(); d.dataset_path = Path(tmp)
            d.cfg['calibration_files'] = {}
            with patch.dict(os.environ, {'BOTANICGARDEN_SOURCE_DIR': tmp}), \
                 patch('Datasets.dataset_files.dataset_botanicgarden.downloadFile') as mirror, \
                 patch('Datasets.dataset_files.dataset_botanicgarden.download_onedrive_file') as source:
                d.download_sequence_data('1018_13')
                mirror.assert_not_called()
                self.assertEqual(source.call_count, 2)
                self.assertEqual(source.call_args_list[0].kwargs['filename'], '1018_13_VLIO.bag')
                self.assertEqual(source.call_args_list[0].kwargs['checksum'], 'md5:50ad55dc11d80c519f964a80dbeedf82')
                self.assertEqual(source.call_args_list[1].kwargs['filename'], 'gt_1018_13_qnew.bag')

    def test_resume_prefers_larger_partial_on_dataset_disk(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); local = root / 'downloads'; local.mkdir()
            d = BotanicgardenDataset(); d.dataset_path = root / 'dataset'
            d.cfg['calibration_files'] = {}
            d._raw().mkdir(parents=True)
            name = '1018_13_VLIO.bag'
            (local / (name+'.part')).write_bytes(b'old')
            (d._raw() / (name+'.part')).write_bytes(b'more progress')
            with patch.dict(os.environ, {'BOTANICGARDEN_SOURCE_DIR': str(local)}), \
                 patch('Datasets.dataset_files.dataset_botanicgarden.download_onedrive_file'):
                d.download_sequence_data('1018_13')
            sources = json.loads((d.sequence_path('1018_13') / 'sources.json').read_text())
            self.assertEqual(sources['files'][name], str(d._raw() / name))
            self.assertEqual((local / (name+'.part')).read_bytes(), b'old')
