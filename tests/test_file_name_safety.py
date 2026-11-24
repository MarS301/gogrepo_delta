"""Entry 0.5.89: unsafe_file_name_reason says whether a name is a file name on Linux, Windows and macOS alike, and _queue_item_downloads
refuses the others (one warning and one entry in the run summary per file) and goes on with the rest.

A file name is the last part of the download address after unquote(), so '%2F' arrives as '/' and '..%2F..%2Fx.exe' as '../../x.exe'."""
import logging
import os
import shutil
import tempfile
import threading
import unittest
from types import SimpleNamespace

import _bootstrap  # noqa: F401
import gogrepo_delta as g

SAFE = ['setup_alpha.exe', 'the.art.of.playing.(2014).1080p.mp4', 'setup_game_(12345).exe', 'Name with spaces.zip', 'n\u00e4me_\u00fc\u4e2d\u6587.pdf',
        'a-b_c+d,e;f=g&h%i#j@k!l~m$n[o]p{q}r\'s^t`u.bin', 'console.exe', 'COM0', 'COM10.txt', 'x.con', 'aux_1.zip', ' leading.zip', '.hidden', 'a..b', 'archive.tar.gz']


class UnsafeNameReasonTests(unittest.TestCase):
    def test_names_that_are_fine_are_accepted(self):
        for name in SAFE:
            with self.subTest(name=name):
                self.assertIsNone(g.unsafe_file_name_reason(name))

    def test_empty_and_dot_names(self):
        for name in ('', '.', '..'):
            with self.subTest(name=name):
                self.assertIn('the name is', g.unsafe_file_name_reason(name))

    def test_path_separators_and_traversal(self):
        for name in ('../x.exe', '..\\x.exe', 'sub/a.exe', 'sub\\a.exe', '/abs.exe', '\\abs.exe', 'C:\\x.exe', '../../x.exe'):
            with self.subTest(name=name):
                self.assertIn(g.unsafe_file_name_reason(name), ('the name contains a path separator',))

    def test_every_character_that_one_of_the_three_systems_refuses(self):
        # Linux: / and NUL. Windows: < > : " / \ | ? * and 0-31. macOS: : and /. Plus DEL, which is a control character.
        for c in list(g.UNSAFE_NAME_CHARS) + [chr(i) for i in range(32)] + [chr(127)]:
            with self.subTest(char=repr(c)):
                self.assertIsNotNone(g.unsafe_file_name_reason('a%sb.exe' % c))
                self.assertIsNotNone(g.unsafe_file_name_reason('%sab.exe' % c))
                self.assertIsNotNone(g.unsafe_file_name_reason('ab.ex%s' % c))

    def test_the_character_set_is_exactly_the_documented_one(self):
        self.assertEqual(sorted(g.UNSAFE_NAME_CHARS), sorted('<>:"/\\|?*'))

    def test_trailing_space_or_dot_is_refused_because_windows_drops_it(self):
        for name in ('a.', 'a ', 'a.exe.', 'a.exe ', 'a. .'):
            with self.subTest(name=name):
                self.assertIn('ends with a space or a dot', g.unsafe_file_name_reason(name))

    def test_windows_device_names_with_or_without_extension_in_any_case(self):
        names = ['CON', 'con', 'Prn', 'AUX', 'nul', 'COM1', 'com9', 'LPT1', 'lpt9', 'COM\u00b9', 'LPT\u00b3', 'CONIN$', 'conout$']
        names += ['CON.txt', 'nul.tar.gz', 'aux.', 'Com3.exe', 'CON .txt']      # a trailing space before the dot does not help
        for name in names:
            with self.subTest(name=name):
                self.assertIsNotNone(g.unsafe_file_name_reason(name))

    def test_control_characters_are_shown_escaped(self):
        reason = g.unsafe_file_name_reason('a\x00b\nc')
        self.assertIn('\\x00', reason)
        self.assertIn('\\x0a', reason)
        self.assertNotIn('\x00', reason)
        self.assertNotIn('\n', reason)
        self.assertEqual(g._printable_name('a\x1bb'), 'a\\x1bb')

    def test_the_reason_lists_each_bad_character_once(self):
        self.assertEqual(g.unsafe_file_name_reason('a:b:c?.exe'), 'the name contains a character that is not allowed in file names: : ?')


class Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.home = os.path.join(self.dir, 'lib', 'alpha')
        os.makedirs(self.home)
        self.handler = Capture()
        g.rootLogger.addHandler(self.handler)
        self.addCleanup(g.rootLogger.removeHandler, self.handler)
        g.run_report.reset('download')
        self.addCleanup(g.run_report.reset)

    def queue(self, names, skipfiles=()):
        items = [g.AttrDict(name=n, size=100, href='http://x/%d' % i, md5=None) for i, n in enumerate(names)]
        job = SimpleNamespace(work_dict={}, provisional_dict={}, sizes={}, lock=threading.Lock(), downloadLimit=None, dryrun=True,
                              skippreallocation=True, queue=None)
        game = g.AttrDict(id=1, title='alpha', folder_name='alpha')
        downloaddir, provisionaldir = os.path.join(self.dir, 'lib', '!downloading', 'alpha'), os.path.join(self.dir, 'lib', '!downloading', '!provisional', 'alpha')
        g._queue_item_downloads(job, game, items, self.home, downloaddir, provisionaldir, list(skipfiles), [game])
        return job

    def warnings(self):
        return [r.getMessage() for r in self.handler.records if r.levelname == 'WARNING' and 'refused' in r.getMessage()]

    def test_refused_files_get_one_warning_and_one_failure_each_and_the_rest_is_queued(self):
        job = self.queue(['good.exe', '../evil.exe', 'a:b.exe', 'also_good.zip', 'CON.txt'])
        queued = sorted(os.path.basename(p) for p in list(job.work_dict) + list(job.provisional_dict))
        self.assertEqual(queued, ['also_good.zip', 'good.exe'])
        self.assertEqual(len(self.warnings()), 3, self.warnings())
        self.assertEqual(sorted(what for what, why in g.run_report.failures), ['alpha/../evil.exe', 'alpha/CON.txt', 'alpha/a:b.exe'])
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_a_refused_name_never_reaches_a_path(self):
        job = self.queue(['../../outside.exe', 'sub/inner.exe', '..'])
        self.assertEqual((job.work_dict, job.provisional_dict, job.sizes), ({}, {}, {}))
        self.assertEqual(os.listdir(self.dir), ['lib'])
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, 'lib'))), ['alpha'])
        self.assertEqual(os.listdir(self.home), [])

    def test_good_names_only_give_no_warning_and_no_failure(self):
        self.queue(['setup_a.exe', 'the.art.of.playing.(2014).1080p.mp4'])
        self.assertEqual(self.warnings(), [])
        self.assertEqual(g.run_report.failures, [])

    def test_a_file_that_skipfiles_excludes_is_skipped_not_refused(self):
        self.queue(['../evil.exe'], skipfiles=['*.exe'])
        self.assertEqual(self.warnings(), [])
        self.assertEqual(g.run_report.failures, [])

    def test_a_file_that_is_already_in_the_library_is_refused_too_and_left_alone(self):
        path = os.path.join(self.home, 'setup:2.exe')
        try:
            with open(path, 'wb') as f:
                f.write(b'x' * 100)
        except OSError:
            self.skipTest('this file system does not allow a colon in a file name')
        job = self.queue(['setup:2.exe'])
        self.assertEqual((job.work_dict, job.provisional_dict), ({}, {}))
        self.assertEqual(len(self.warnings()), 1)
        self.assertEqual(len(g.run_report.failures), 1)
        self.assertTrue(os.path.isfile(path))               # not renamed, not deleted

    def test_the_summary_names_the_game_folder_and_the_escaped_name(self):
        self.queue(['a\x00b.exe'])
        self.assertEqual(len(g.run_report.failures), 1)
        what, why = g.run_report.failures[0]
        self.assertEqual(what, 'alpha/a\\x00b.exe')
        self.assertTrue(why.startswith('refused, '))
        self.assertNotIn('\x00', self.warnings()[0])


if __name__ == '__main__':
    unittest.main()
