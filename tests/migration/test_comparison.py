from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from dataset_inputs import load_comparison, experiment_inputs
from run_catalog import materialize, partition_methods


class ComparisonTests(unittest.TestCase):
    def test_parallel_workers_own_disjoint_experiments_and_keep_sequences_together(self):
        recipes = {f'{method}_{sequence}': {'Module': module, 'NumRuns': 2}
                   for method, module in [('orb_default', 'orbslam3'), ('orb_no_loop', 'orbslam3'),
                                          ('voxel_svio', 'voxel-svio')]
                   for sequence in range(2)}
        groups = partition_methods(recipes)
        self.assertEqual(set(groups), {'orb_default', 'orb_no_loop', 'voxel_svio'})
        owned = [name for group in groups.values() for name in group]
        self.assertEqual(len(owned), len(set(owned)))
        self.assertEqual(set(owned), set(recipes))
        for variant, group in groups.items():
            self.assertEqual(set(group), {f'{variant}_0', f'{variant}_1'})
            self.assertTrue(all(recipe['NumRuns'] == 2 for recipe in group.values()))

    def test_default_preparation_matches_report_experiment(self):
        _, _, _, downloaded = experiment_inputs(ROOT / 'configs/datasets/selected.yaml')
        _, _, _, used = load_comparison(ROOT / 'configs/experiments/report.yaml')
        self.assertEqual(set(used), set(downloaded))
        self.assertEqual(len(downloaded), 3)

    def test_selection_is_independent_of_experiment(self):
        with tempfile.TemporaryDirectory() as tmp:
            selection = Path(tmp) / 'selected.yaml'
            selection.write_text("grandtour-alphasense: [kaeb_1, alb_1]\nbotanicgarden: ['1018_00', '1018_13']\n")
            _, _, _, downloaded = experiment_inputs(selection)
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
                'FrameStart': {'d': {'s2': 20}},
                'Methods': {'stock': {'Module': 'm', 'Parameters': {'mode': 'stereo-vi',
                                          'imu_noise_by_dataset': {'d': {'sigma_gw_c': .001}}}},
                            'no_loop': {'Module': 'm', 'Settings': {'loopClosing': 0},
                                        'Parameters': {'imu_noise_by_dataset': {'d': {'sigma_gw_c': .001}}}}},
                'Evaluation': {'align': 'SE3', 'correct_scale': False, 'estimate_frame': 'body'}}))
            def audit(folder, start_frame=0):
                self.assertEqual(start_frame, 0 if folder.name == 's1' else 20)
                return [], {'framework_rgb_idx_inclusive': [max(start_frame, 1 if folder.name == 's1' else 2), 300]}
            with patch('run_catalog.dataset_at_root', return_value=Dataset()), \
                 patch('run_catalog.camera_imu_window', side_effect=audit):
                exp = materialize(cfg, root / 'run/inputs', lambda _: Baseline(), 200)
            data = yaml.safe_load(exp.read_text())
            self.assertEqual(exp, root / 'run/experiment.yaml')
            self.assertEqual(set(data), {'stock_0', 'stock_1', 'no_loop_0', 'no_loop_1'})
            self.assertEqual(len(data), 4)
            for entry in data.values():
                self.assertEqual(entry['NumRuns'], 2)
                self.assertEqual(entry['Parameters']['rgb_max'], 200)
                self.assertEqual(entry['Parameters']['verbose'], 0)
                self.assertEqual(entry['Parameters']['imu_noise'], {'sigma_gw_c': .001})
                self.assertNotIn('imu_noise_by_dataset', entry['Parameters'])
                selection = yaml.safe_load(Path(entry['Config']).read_text())
                expected_start = 1 if selection['d'] == ['s1'] else 20
                self.assertEqual(entry['Parameters']['rgb_idx'], [expected_start, 300])
            changed = [e for e in data.values() if 'no_loop' in Path(e['MethodSettings']).name]
            self.assertEqual(len(changed), 2)
            effective = yaml.safe_load(Path(changed[0]['MethodSettings']).read_text())
            self.assertEqual(effective['loopClosing'], 0)
            self.assertEqual(effective['ORBextractor.nFeatures'], 1000)
            self.assertNotIn('loopClosing', yaml.safe_load(stock.read_text()))
            self.assertEqual((exp.parent / 'inputs/stock_settings.yaml').read_bytes(), stock.read_bytes())
            self.assertEqual(yaml.safe_load((exp.parent/'inputs/evaluation.yaml').read_text())['align'], 'SE3')

    def test_invalid_comparisons_fail_before_execution(self):
        base = {'Datasets': {'d': ['s']}, 'Methods': {'m': {'Module': 'm'}}}
        for change in [{'NumRuns': True}, {'Methods': {}}, {'Methods': {'../bad': {'Module': 'm'}}},
                       {'Datasets': {'d': ['s', 's']}}, {'Unknown': 1},
                       {'FrameStart': []}, {'FrameStart': {'d': {'other': 20}}},
                       {'FrameStart': {'d': {'s': True}}}, {'FrameStart': {'d': {'s': -1}}},
                       {'Methods': {'m': {'Module': 'm', 'Settings': []}}}]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'c.yaml'
                p.write_text(yaml.safe_dump(dict(base, **change)))
                with self.assertRaises(ValueError): load_comparison(p)

    def test_current_evaluation_changes_metrics_but_preserves_saved_frame(self):
        from evaluate_result import current_evaluation_overrides
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)/'comparison.yaml'
            config.write_text(yaml.safe_dump(dict(Datasets={'d':['s']},
                Methods={'method':dict(Module='orbslam3', Evaluation=dict(estimate_frame='body', align='origin'))},
                Evaluation=dict(max_time_difference_s=.1))))
            recipes = {'method_0':dict(Module='orbslam3', Evaluation=dict(estimate_frame='camera', camera='rgb_0'))}
            _, overrides = current_evaluation_overrides(recipes, config)
            self.assertEqual(overrides['method_0']['align'], 'origin')
            self.assertEqual(overrides['method_0']['max_time_difference_s'], .1)
            self.assertNotIn('estimate_frame', overrides['method_0'])
            self.assertNotIn('camera', overrides['method_0'])
            with self.assertRaisesRegex(ValueError, 'variant absent'):
                current_evaluation_overrides({'other_0':recipes['method_0']}, config)

    def test_latest_comparison_uses_nested_logs_and_ignores_plans(self):
        from evaluate_result import latest_comparison
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / 'comparison_run'
            run.mkdir()
            (run / 'experiment.yaml').write_text('method_0: {Module: orbslam3}\n')
            (run / 'method_0').mkdir()
            (run / 'method_0/vslamlab_exp_log.csv').write_text('native log')
            plan = root / 'comparison_plan'
            plan.mkdir()
            (plan / 'experiment.yaml').write_text('method_0: {Module: orbslam3}\n')
            self.assertEqual(latest_comparison(root), run / 'experiment.yaml')
