from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_results import create_run_directory, select_run, source_directory


class RunResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'results'
        self.now = datetime(2026, 10, 12, 21, 30, 0)

    def test_dated_directory(self):
        folder = create_run_directory(self.root, self.now)
        self.assertEqual(folder, self.root / '2026-10-12_21-30-00')
        self.assertTrue(folder.is_dir())

    def test_existing_results_are_preserved(self):
        first = create_run_directory(self.root, self.now)
        artifact = first / 'execution.json'
        artifact.write_text('original result')
        second = create_run_directory(self.root, self.now)
        self.assertEqual(second.name, '2026-10-12_21-30-00-02')
        self.assertEqual(artifact.read_text(), 'original result')

    def test_existing_file_is_not_overwritten(self):
        self.root.mkdir()
        artifact = self.root / '2026-10-12_21-30-00'
        artifact.write_text('keep')
        folder = create_run_directory(self.root, self.now)
        self.assertEqual(folder.name, '2026-10-12_21-30-00-02')
        self.assertEqual(artifact.read_text(), 'keep')

    def test_parallel_runs_are_unique(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            folders = list(pool.map(lambda _: create_run_directory(self.root, self.now), range(16)))
        self.assertEqual(len(set(folders)), 16)
        self.assertTrue(all(folder.is_dir() for folder in folders))

    def test_different_dates(self):
        first = create_run_directory(self.root, self.now)
        second = create_run_directory(self.root, datetime(2026, 10, 13, 21, 30, 0))
        self.assertNotEqual(first, second)
        self.assertEqual(second.name, '2026-10-13_21-30-00')

    def test_latest_suffix_is_numeric(self):
        self.root.mkdir()
        for name in ['2026-10-12_21-30-00', '2026-10-12_21-30-00-99', '2026-10-12_21-30-00-100']:
            (self.root / name).mkdir()
        self.assertEqual(select_run(None, self.root).name, '2026-10-12_21-30-00-100')

    def test_legacy_source_path_with_spaces(self):
        self.assertEqual(source_directory({'command': "pixi run sequence_path:'/tmp/data with spaces'"}),
                         Path('/tmp/data with spaces'))

    def test_incomplete_evaluations_are_not_selected(self):
        folder = create_run_directory(self.root, self.now)
        with self.assertRaisesRegex(FileNotFoundError, 'No completed evaluation'):
            select_run(None, self.root, required_files=('summary.json', 'ape_position_m.zip'))
        (folder / 'summary.json').write_text('{}')
        with self.assertRaisesRegex(FileNotFoundError, 'No completed evaluation'):
            select_run(None, self.root, required_files=('summary.json', 'ape_position_m.zip'))
