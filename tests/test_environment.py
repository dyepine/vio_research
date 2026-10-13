import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from config_paths import config_path


class EnvironmentTests(unittest.TestCase):
    def test_explicit_environment_path(self):
        with patch.dict(os.environ, {'VIO_DATA_DIR': '/tmp/data with spaces'}):
            self.assertEqual(config_path('${VIO_DATA_DIR}/recording', ROOT),
                             Path('/tmp/data with spaces/recording'))

    def test_missing_environment_is_an_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'VIO_DATA_DIR is unset'):
                config_path('${VIO_DATA_DIR}', ROOT)

    def test_literal_relative_path(self):
        self.assertEqual(config_path('recordings', ROOT), ROOT / 'recordings')

    def test_make_creates_and_preserves_envrc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copy(ROOT / 'Makefile', root / 'Makefile')
            shutil.copy(ROOT / 'scripts/env.sh', root / 'scripts/env.sh')
            subprocess.run(['make', 'configure'], cwd=root, check=True, capture_output=True)
            envrc = root / '.envrc'
            self.assertEqual(envrc.read_bytes(), (ROOT / 'scripts/env.sh').read_bytes())
            local = envrc.read_text() + '\n# Local custom settings\n'
            envrc.write_text(local)
            subprocess.run(['make', '-B', 'configure'], cwd=root, check=True, capture_output=True)
            self.assertEqual(envrc.read_text(), local)

    def test_make_run_sources_environment_without_direnv(self):
        with tempfile.TemporaryDirectory(prefix='vio-env-') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'scripts/bootstrap.sh').write_text('#!/bin/bash\nexit 0\n')
            (root / 'external/VSLAM-LAB').mkdir(parents=True)
            shutil.copy(ROOT / 'Makefile', root / 'Makefile')
            pixi = root / 'fake pixi'
            pixi.write_text('#!/bin/bash\nprintf "%s\\n" "$VIO_DATA_DIR" "$VIO_RESULTS_DIR" "$VIO_EXPERIMENT_CONFIG" "$@"\n')
            pixi.chmod(0o755)
            (root / '.envrc').write_text(
                f'export PIXI_BIN="{pixi}"\n'
                'export VIO_DATA_DIR="/tmp/custom data"\n'
                'export VIO_RESULTS_DIR="/tmp/custom results"\n'
                'export VIO_EXPERIMENT_CONFIG="/tmp/custom experiment.yaml"\n')
            result = subprocess.run(['make', 'run'], cwd=root, check=True,
                                    capture_output=True, text=True)
            self.assertIn('/tmp/custom data\n/tmp/custom results\n/tmp/custom experiment.yaml\nrun\n--frozen\n-e\nvslamlab\npython\n',
                          result.stdout)

    def test_bootstrap_interpreter_from_envrc_and_make_override(self):
        with tempfile.TemporaryDirectory(prefix='vio-env-') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copy(ROOT / 'Makefile', root / 'Makefile')
            (root / 'requirements.txt').write_text('')
            interpreter = root / 'custom python'
            interpreter.write_text(
                '#!/bin/bash\nset -e\n'
                'mkdir -p "$3/bin"\n'
                'printf "#!/bin/bash\\nexit 0\\n" > "$3/bin/python"\n'
                'chmod +x "$3/bin/python"\n'
                'printf "%s" "$0" > "$(dirname "$3")/bootstrap-used"\n')
            interpreter.chmod(0o755)
            (root / 'scripts/env.sh').write_text(f'export PYTHON="${{PYTHON:-{interpreter}}}"\n')
            environment = {key: value for key, value in os.environ.items() if key != 'PYTHON'}
            subprocess.run(['make', '-j2', 'env'], cwd=root, env=environment,
                           check=True, capture_output=True)
            self.assertEqual((root / 'bootstrap-used').read_text(), str(interpreter))
            self.assertTrue((root / '.venv/.installed').exists())
            override = root / 'override python'
            shutil.copy(interpreter, override)
            shutil.rmtree(root / '.venv')
            subprocess.run(['make', 'env', f'PYTHON={override}'], cwd=root,
                           env=environment, check=True, capture_output=True)
            self.assertEqual((root / 'bootstrap-used').read_text(), str(override))

    def test_make_config_override_reaches_both_prepare_and_run(self):
        with tempfile.TemporaryDirectory(prefix='vio-env-') as directory:
            root=Path(directory)
            (root/'scripts').mkdir()
            (root/'scripts/bootstrap.sh').write_text('#!/bin/bash\nexit 0\n')
            (root/'external/VSLAM-LAB').mkdir(parents=True)
            shutil.copy(ROOT/'Makefile',root/'Makefile')
            pixi=root/'fake pixi'
            pixi.write_text('#!/bin/bash\nprintf "%s\n" "$@"\n')
            pixi.chmod(0o755)
            (root/'.envrc').write_text(f'export PIXI_BIN="{pixi}"\n')
            config=root/'chosen experiment.yaml'
            for target in ['prepare','run']:
                result=subprocess.run(['make',target,f'CONFIG={config}'],cwd=root,
                                      check=True,capture_output=True,text=True)
                self.assertIn('--config\n'+str(config)+'\n',result.stdout)
