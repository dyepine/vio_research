"""Source fetches must work in initially empty container cache volumes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FETCH = ROOT / 'external/VSLAM-LAB/git-clone.sh'


class SourceCacheTests(unittest.TestCase):
    def test_empty_cache_clones_and_populated_cache_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix='vio-source-cache-') as directory:
            root = Path(directory)
            source, target = root / 'source', root / 'cache'
            source.mkdir()
            target.mkdir()
            env = dict(os.environ, GIT_AUTHOR_NAME='test', GIT_COMMITTER_NAME='test',
                       GIT_AUTHOR_EMAIL='test@example.invalid',
                       GIT_COMMITTER_EMAIL='test@example.invalid')
            def git(*args):
                return subprocess.run(['git', '-C', str(source), *args], env=env,
                                      check=True, capture_output=True)
            git('init', '--quiet')
            (source / 'sample').write_text('source\n')
            git('add', 'sample')
            git('commit', '--quiet', '-m', 'fixture')
            command = ['bash', str(FETCH), str(source), str(target)]
            subprocess.run(command, check=True, capture_output=True)
            self.assertTrue((target / '.git').is_dir())
            (target / 'sample').write_text('local change\n')
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual((target / 'sample').read_text(), 'local change\n')
            (target / '.keep').write_text('retain\n')
            subprocess.run(['bash', str(FETCH), str(source), str(target)],
                           check=True, capture_output=True)
            self.assertTrue((target / '.keep').exists())
            hidden = root / 'hidden-only'
            hidden.mkdir()
            (hidden / '.keep').write_text('retain\n')
            subprocess.run(['bash', str(FETCH), str(source), str(hidden)],
                           check=True, capture_output=True)
            self.assertFalse((hidden / '.git').exists())
            self.assertEqual((hidden / '.keep').read_text(), 'retain\n')
