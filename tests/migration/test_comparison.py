from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from dataset_inputs import load_comparison, experiment_inputs
from run_catalog import materialize


class ComparisonTests(unittest.TestCase):
    def test_selection_is_independent_of_experiment(self):
        _, _, _, downloaded = experiment_inputs(ROOT / 'configs/datasets/selected.yaml')
        _, _, _, used = load_comparison(ROOT / 'configs/experiments/comparison.yaml')
        self.assertTrue(set(used) < set(downloaded))

    def test_variants_sequences_repeats_and_settings_are_materialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stock = root / 'stock.yaml'
            stock.write_text('%YAML 1.2\n---\nFile.version: "1.0"\nORBextractor.nFeatures: 1000\ncam_stereo: [rgb_0, rgb_1]\n')
            class Baseline:
                default_parameters = {'mode': 'mono-vi', 'verbose': 1}
                modes = ['mono-vi', 'stereo-vi']
                settings_yaml = stock
                def ensure_installed(self): pass
                def download_vslamlab_settings(self): return True
            class Dataset:
                def check_sequence_availability(self, sequence, verbose=False): return 'available'
                def sequence_path(self, sequence): return root / sequence
            cfg = root / 'comparison.yaml'
            cfg.write_text(yaml.safe_dump({
                'Datasets': {'d': ['s1', 's2']}, 'NumRuns': 2,
                'Methods': {'stock': {'Module': 'm', 'Parameters': {'mode': 'stereo-vi'}},
                            'no_loop': {'Module': 'm', 'Settings': {'loopClosing': 0}}},
                'Evaluation': {'align': 'SE3', 'correct_scale': False, 'estimate_frame': 'body'}}))
            def audit(folder):
                return [], {'framework_rgb_idx_inclusive': [1 if folder.name == 's1' else 2, 300]}
            with patch('run_catalog.dataset_at_root', return_value=Dataset()), \
                 patch('run_catalog.camera_imu_window', side_effect=audit):
                exp = materialize(cfg, root / 'run/inputs', lambda _: Baseline(), 200)
            data = yaml.safe_load(exp.read_text())
            self.assertEqual(len(data), 4)
            for entry in data.values():
                self.assertEqual(entry['NumRuns'], 2)
                self.assertEqual(entry['Parameters']['rgb_max'], 200)
                self.assertEqual(entry['Parameters']['verbose'], 0)
                selection = yaml.safe_load(Path(entry['Config']).read_text())
                expected_start = 1 if selection['d'] == ['s1'] else 2
                self.assertEqual(entry['Parameters']['rgb_idx'], [expected_start, 300])
            changed = [e for e in data.values() if 'no_loop' in Path(e['MethodSettings']).name]
            self.assertEqual(len(changed), 2)
            effective = yaml.safe_load(Path(changed[0]['MethodSettings']).read_text())
            self.assertEqual(effective['loopClosing'], 0)
            self.assertEqual(effective['ORBextractor.nFeatures'], 1000)
            self.assertNotIn('loopClosing', yaml.safe_load(stock.read_text()))
            self.assertEqual((exp.parent / 'stock_settings.yaml').read_bytes(), stock.read_bytes())
            self.assertEqual(yaml.safe_load((exp.parent/'evaluation.yaml').read_text())['align'], 'SE3')

    def test_invalid_comparisons_fail_before_execution(self):
        base = {'Datasets': {'d': ['s']}, 'Methods': {'m': {'Module': 'm'}}}
        for change in [{'NumRuns': True}, {'Methods': {}}, {'Methods': {'../bad': {'Module': 'm'}}},
                       {'Datasets': {'d': ['s', 's']}}, {'Unknown': 1},
                       {'Methods': {'m': {'Module': 'm', 'Settings': []}}}]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'c.yaml'
                p.write_text(yaml.safe_dump(dict(base, **change)))
                with self.assertRaises(ValueError): load_comparison(p)
