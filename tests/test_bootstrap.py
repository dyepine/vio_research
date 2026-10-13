"""Bootstrap checks against the pinned fork checkout, without network downloads."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def checkout(self, root):
        (root / 'scripts').mkdir()
        (root / 'external').mkdir()
        shutil.copy(ROOT / 'scripts/bootstrap.sh', root / 'scripts/bootstrap.sh')
        subprocess.run(['git', 'init', '--quiet', str(root)], check=True, capture_output=True)
        revision = subprocess.check_output(['git', 'rev-parse', ':external/VSLAM-LAB'],
                                           cwd=ROOT, text=True).strip()
        subprocess.run(['git', 'update-index', '--add', '--cacheinfo',
                        f'160000,{revision},external/VSLAM-LAB'], cwd=root, check=True)
        subprocess.run(['git', 'clone', '--shared', '--quiet', str(ROOT / 'external/VSLAM-LAB'),
                        str(root / 'external/VSLAM-LAB')], check=True, capture_output=True)
        pixi = root / 'fake pixi'
        pixi.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$(dirname "$0")/pixi-args"\n')
        pixi.chmod(0o755)
        (root / '.envrc').write_text(f'export PIXI_BIN="{pixi}"\n')

    def run_bootstrap(self, root):
        return subprocess.run(['bash', str(root / 'scripts/bootstrap.sh')],
                              cwd=root, capture_output=True, text=True)

    def test_clean_checkout_and_second_invocation_deliver_same_adapter(self):
        with tempfile.TemporaryDirectory(prefix='vio clean checkout ') as tmp:
            root = Path(tmp)
            self.checkout(root)
            for _ in range(2):
                result = self.run_bootstrap(root)
                self.assertEqual(result.returncode, 0, result.stderr)
            lab = root / 'external/VSLAM-LAB'
            for path in ['Datasets/dataset_files/dataset_botanicgarden.py',
                         'Datasets/dataset_files/dataset_botanicgarden.yaml',
                         'Datasets/dataset_files/dataset_grandtour.py',
                         'Datasets/extra-files/extract_rosbag_poses.py', 'path_constants.py']:
                self.assertEqual((lab / path).read_bytes(), (ROOT / 'external/VSLAM-LAB' / path).read_bytes())
            self.assertEqual((root / 'pixi-args').read_text().splitlines(),
                             ['install', '--frozen', '-e', 'vslamlab', '-e', 'ros1'])

    def test_wrong_revision_is_preserved_and_fails(self):
        with tempfile.TemporaryDirectory(prefix='vio conflicting checkout ') as tmp:
            root = Path(tmp)
            self.checkout(root)
            lab = root / 'external/VSLAM-LAB'
            subprocess.run(['git', 'checkout', '--quiet', '--detach', 'HEAD~1'], cwd=lab, check=True)
            path = root / 'external/VSLAM-LAB/path_constants.py'
            content = path.read_text().replace('VSLAMLAB_BENCHMARK =', 'OTHER_BENCHMARK =')
            path.write_text(content)
            result = self.run_bootstrap(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Unexpected VSLAM-LAB revision', result.stderr)
            self.assertEqual(path.read_text(), content)
            self.assertFalse((root / 'pixi-args').exists())
