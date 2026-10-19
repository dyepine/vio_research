"""Host Make/Compose boundary: paths, options and local settings without Docker."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DockerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vio-first-checkout-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'bin').mkdir()
        shutil.copy(ROOT / 'Makefile', self.root / 'Makefile')
        for name in ['env.sh', 'docker-compose.sh']:
            shutil.copy(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        docker = self.root / 'bin/docker'
        docker.write_text(
            '#!/usr/bin/env python3\nimport json, os, sys\n'
            'if sys.argv[1:] == ["compose", "version"]: sys.exit(0)\n'
            'print(json.dumps({"args": sys.argv[1:], "env": {k: os.environ.get(k) '
            'for k in ["VIO_DATA_DIR", "VIO_RESULTS_DIR", '
            '"VIO_CONTAINER_EXPERIMENT_CONFIG", "VIO_CONTAINER_DATASET_CONFIG"]}}))\n')
        docker.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('VIO_', 'PIXI_', 'MAKE')) and k != 'ROOT_DIR'}
        self.env.update(VIO_NATIVE='0', PATH=str(self.root / 'bin') + ':' + os.environ['PATH'])

    def make(self, *args, check=True):
        return subprocess.run(['make', *args], cwd=self.root, env=self.env,
                              text=True, capture_output=True, check=check)

    def output(self, *args):
        return json.loads(self.make(*args).stdout.splitlines()[-1])

    def test_first_use_creates_config_and_builds_without_bootstrap(self):
        output = self.output('build')
        self.assertEqual(output['args'], ['compose', 'build'])
        self.assertEqual((self.root / '.envrc').read_bytes(),
                         (self.root / 'scripts/env.sh').read_bytes())
        self.assertEqual(output['env']['VIO_CONTAINER_EXPERIMENT_CONFIG'],
                         '/workspace/configs/experiments/report.yaml')
        self.assertFalse((self.root / '.tools').exists())

    def test_envrc_storage_and_options_reach_compose_with_spaces(self):
        results = self.root / 'saved results'
        settings = ('export VIO_DATA_DIR="./existing data"\n'
                    f'export VIO_RESULTS_DIR="{results}"\n'
                    'export VIO_EXPERIMENT_CONFIG="$ROOT_DIR/configs/experiments/sqrtvins.yaml"\n')
        (self.root / '.envrc').write_text(settings)
        output = self.output('run', 'RGB_MAX=200', 'JOBS=1',
                             'CONFIG=configs/experiments/report.yaml')
        self.assertEqual(output['env']['VIO_DATA_DIR'], str(self.root / 'existing data'))
        self.assertEqual(output['env']['VIO_RESULTS_DIR'], str(results))
        self.assertEqual(output['env']['VIO_CONTAINER_EXPERIMENT_CONFIG'],
                         '/workspace/configs/experiments/sqrtvins.yaml')
        self.assertEqual(output['args'], ['compose', 'run', '--rm', 'vio', 'make', 'run',
                                         'CONFIG=/workspace/configs/experiments/report.yaml',
                                         'RGB_MAX=200', 'JOBS=1'])
        self.assertEqual((self.root / '.envrc').read_text(), settings)

    def test_saved_run_host_path_is_mapped_to_container(self):
        (self.root / '.envrc').write_text('export VIO_RESULTS_DIR="$ROOT_DIR/saved results"\n')
        for path in [str(self.root / 'saved results/comparison_123'), '/results/comparison_123']:
            output = self.output('evaluate', f'RUN_DIR={path}', 'EVAL_ARGS=--saved-protocol')
            self.assertIn('RUN_DIR=/results/comparison_123', output['args'])
            self.assertIn('EVAL_ARGS=--saved-protocol', output['args'])

    def test_all_public_targets_dispatch_to_container(self):
        for target in ['bootstrap', 'prepare', 'run', 'evaluate', 'test']:
            with self.subTest(target=target):
                self.assertEqual(self.output(target)['args'],
                                 ['compose', 'run', '--rm', 'vio', 'make', target])
        self.assertEqual(self.output('config')['args'], ['compose', 'config'])
        self.assertEqual(self.output('shell')['args'], ['compose', 'run', '--rm', 'vio', 'bash'])
        self.assertEqual(self.output('artifacts')['args'],
                         ['compose', 'run', '--rm', 'vio', 'python3',
                          'scripts/build_report_table.py', '--check'])

    def test_unmounted_config_and_result_paths_fail_before_docker(self):
        for options in [('run', 'CONFIG=/unmounted/experiment.yaml'),
                        ('evaluate', 'RUN_DIR=/unmounted/result')]:
            with self.subTest(options=options):
                result = self.make(*options, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('must be inside', result.stderr)
                self.assertNotIn('"args"', result.stdout)

    def test_broken_envrc_does_not_fall_back_to_other_data_directory(self):
        (self.root / '.envrc').write_text('exit 73\n')
        result = self.make('prepare', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"args"', result.stdout)
