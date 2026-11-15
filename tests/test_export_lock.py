"""Entry 0.5.64: `export` checks that the CSV file can be written before it reads anything and says so in words when it cannot (a file that is
open in Excel is locked), instead of ending with a PermissionError and a traceback."""
import builtins
import csv
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_clean_target import game


class Base(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset('export')
        g.save_manifest([game('alpha')])

    def export(self, *args):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_export(*args)
        return [(r.levelname, r.getMessage()) for r in logs.records]

    def read_rows(self, path='out.csv'):
        with open(path, encoding='utf-8-sig', newline='') as f:
            return list(csv.reader(f))


class RefusedTests(Base):
    def locked(self):
        """An output file that cannot be written, as a file that Excel has open."""
        return mock.patch.object(g, 'file_write_problem', return_value=PermissionError(13, 'Permission denied'))

    def test_a_locked_file_is_refused_in_words_before_anything_is_read(self):
        with self.locked(), mock.patch.object(g, 'load_manifest', side_effect=AssertionError('the manifest must not be read')):
            log = self.export('out.csv', None, ',')
        errors = [m for level, m in log if level == 'ERROR']
        self.assertEqual(len(errors), 1)
        self.assertIn('cannot write out.csv (Permission denied)', errors[0])
        self.assertIn('open in another program, for example Excel', errors[0])
        self.assertIn('close it and run the command again', errors[0])
        self.assertEqual(g.run_report.failures, [('csv', 'file cannot be written')])
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_the_existing_file_is_left_exactly_as_it_was(self):
        with open('out.csv', 'w', encoding='utf-8') as f:
            f.write('precious,data\n')
        with self.locked():
            self.export('out.csv', None, ',')
        with open('out.csv', encoding='utf-8') as f:
            self.assertEqual(f.read(), 'precious,data\n')

    def test_a_refused_file_that_did_not_exist_is_not_created(self):
        with self.locked():
            self.export('new.csv', None, ',')
        self.assertFalse(os.path.exists('new.csv'))

    def test_a_real_problem_with_the_file_is_found_by_the_check(self):
        os.mkdir('out.csv')                                  # a folder in the place of the file: cannot be opened for writing anywhere
        log = self.export('out.csv', None, ',')
        self.assertTrue(any(level == 'ERROR' and 'cannot write out.csv' in m for level, m in log))
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertTrue(os.path.isdir('out.csv'))

    def test_a_folder_that_does_not_exist_is_reported_the_same_way(self):
        log = self.export(os.path.join('missing', 'out.csv'), None, ',')
        self.assertTrue(any(level == 'ERROR' and 'cannot write' in m and 'missing' in m for level, m in log))
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_the_check_can_pass_and_the_opening_still_fail(self):
        # the file was opened by Excel between the check and the writing, or a drive says no only now
        real_open = builtins.open
        def refusing(path, mode='r', *args, **kwargs):
            if str(path) == 'out.csv' and 'w' in mode:
                raise PermissionError(13, 'Permission denied')
            return real_open(path, mode, *args, **kwargs)
        with mock.patch.object(g, 'file_write_problem', return_value=None), mock.patch('builtins.open', refusing):
            log = self.export('out.csv', None, ',')
        errors = [m for level, m in log if level == 'ERROR']
        self.assertEqual(len(errors), 1)
        self.assertIn('cannot write out.csv (Permission denied)', errors[0])
        self.assertEqual(g.run_report.failures, [('csv', 'file cannot be written')])
        self.assertFalse(os.path.exists('out.csv'))

    def test_no_traceback_reaches_the_user_through_main(self):
        with self.locked(), self.assertLogs('gogrepoc', level='INFO') as logs:
            status = g.main(g.process_argv(['gogrepo_delta.py', 'export', '--output', 'out.csv', '-nolog']))
        self.assertEqual(status, 1)
        self.assertTrue(any('cannot write out.csv' in r.getMessage() for r in logs.records))
        self.assertFalse(any('Traceback' in r.getMessage() for r in logs.records))
        self.assertIn('   FAILED: 1', [r.getMessage() for r in logs.records])


class UnchangedTests(Base):
    def test_a_free_file_is_written_as_before(self):
        log = self.export('out.csv', None, ',')
        self.assertEqual(g.run_report.exit_status(), 0)
        self.assertTrue(any('wrote' in m and 'out.csv' in m for level, m in log))
        rows = self.read_rows()
        self.assertEqual(rows[0][:3], ['game id', 'title', 'media'])
        self.assertGreater(len(rows), 1)

    def test_an_existing_free_file_is_replaced(self):
        with open('out.csv', 'w', encoding='utf-8') as f:
            f.write('old\n')
        self.export('out.csv', None, ',')
        self.assertEqual(self.read_rows()[0][0], 'game id')

    def test_the_check_leaves_nothing_behind(self):
        self.export('out.csv', None, ',')
        self.assertEqual(sorted(n for n in os.listdir('.') if n.endswith('.csv')), ['out.csv'])


if __name__ == '__main__':
    unittest.main()
