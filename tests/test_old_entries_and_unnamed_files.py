"""Entry 0.5.92: two small robustness fixes, each found by a test that failed first.

Open item 2: `_clean_work_dir` read galaxyDownloads and sharedDownloads of every game directly, but only the games chosen by -ids / -skipids get those fields from an old manifest.
Finding F: `clean_target_problem` called os.path.normcase(None) for a file of the manifest whose name is not known (an unreleased extra) and stopped with a TypeError,
in the very case it is there for (clean started on the folder of one game)."""
import hashlib
import os
import shutil
import tempfile
import unittest

import _bootstrap  # noqa: F401
import gogrepo_delta as g
import test_run_summary as trs


def old_format_game(title='alpha', **files):
    """An entry from before galaxyDownloads, sharedDownloads and folder_name existed: {name: bytes}."""
    entries = [g.AttrDict(name=n, desc=n, lang='English', os_type='windows', size=len(d), md5=hashlib.md5(d).hexdigest(), href='http://x/' + n, version='1', updated='2020',
                          old_updated='2020', prev_verified=False, force_change=False, unreleased=False, md5_exempt=False, old_name=None, gog_data=g.AttrDict())
               for n, d in files.items()]
    return g.AttrDict(id=1, title=title, long_title=title, genre='', store_url='/g', rating=0, release_timestamp=0, changelog='', has_updates=False, serial='', bg_url='',
                      image_url='', downloads=entries, extras=[])


class CleanWorkDirOldEntryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        os.makedirs(os.path.join(self.dir, 'beta'))
        for name in ('keep.exe', 'stale.bin'):
            with open(os.path.join(self.dir, 'beta', name), 'wb') as f:
                f.write(b'x')

    def test_an_entry_without_the_lists_is_read_with_defaults(self):
        game = old_format_game('beta', **{'keep.exe': b'x'})
        self.assertNotIn('galaxyDownloads', game)
        g._clean_work_dir(self.dir, {'beta': game}, False)                     # was an AttributeError
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, 'beta'))), ['keep.exe'])        # the stale file is removed as before

    def test_an_entry_without_extras_either_and_a_file_that_belongs_to_an_extra(self):
        game = old_format_game('beta', **{'keep.exe': b'x'})
        del game['extras']
        g._clean_work_dir(self.dir, {'beta': game}, False)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, 'beta'))), ['keep.exe'])
        with open(os.path.join(self.dir, 'beta', 'bonus.pdf'), 'wb') as f:
            f.write(b'x')
        game = old_format_game('beta', **{'keep.exe': b'x'})
        game.extras = [g.AttrDict(name='bonus.pdf')]                        # the extras are read as well
        g._clean_work_dir(self.dir, {'beta': game}, False)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, 'beta'))), ['bonus.pdf', 'keep.exe'])

    def test_a_dry_run_removes_nothing(self):
        g._clean_work_dir(self.dir, {'beta': old_format_game('beta', **{'keep.exe': b'x'})}, True)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, 'beta'))), ['keep.exe', 'stale.bin'])

    def test_entries_with_all_the_lists_work_as_before(self):
        game = old_format_game('beta', **{'keep.exe': b'x'})
        game.galaxyDownloads, game.sharedDownloads = [], []
        g._clean_work_dir(self.dir, {'beta': game}, False)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, 'beta'))), ['keep.exe'])


class OldFormatCommandsTests(trs.TempDirTests):
    """Every command that reads the manifest copes with entries from before the fields existed (checked one by one; only the case above failed)."""
    def setUp(self):
        super().setUp()
        g.save_manifest([old_format_game('alpha', **{'a.exe': b'a' * 50})])
        for folder in ('lib', 'src'):
            os.makedirs(os.path.join(self.dir, folder, 'alpha'))
            with open(os.path.join(self.dir, folder, 'alpha', 'a.exe'), 'wb') as f:
                f.write(b'a' * 50)

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def test_verify(self):
        g.cmd_verify(self.path('lib'), False, [], True, True, False, False, False, [], ['windows'], ['en'], False, False, False, [], False, False, False, 0)
        self.assertEqual(g.run_report.failures, [])

    def test_backup(self):
        g.cmd_backup(self.path('lib'), self.path('bk'), False, ['windows'], ['en'], [], [], False, False, False)
        self.assertTrue(os.path.isfile(self.path('bk', 'alpha', 'a.exe')))

    def test_import(self):
        g.cmd_import(self.path('src'), self.path('imp'), ['windows'], ['en'], False, [], [], False, False, False, False)
        self.assertTrue(os.path.isfile(self.path('imp', 'alpha', 'a.exe')))

    def test_clean(self):
        g.cmd_clean(self.path('lib'), True, g.load_manifest())
        self.assertTrue(os.path.isfile(self.path('lib', 'alpha', 'a.exe')))

    def test_list(self):
        g.cmd_list([], ['windows'], [], ['en'], [])

    def test_export(self):
        g.cmd_export(self.path('o.csv'), self.path('lib'))
        with open(self.path('o.csv'), encoding='utf-8-sig') as f:
            self.assertIn('alpha', f.read())

    def test_trash(self):
        g.cmd_trash(self.path('lib'), True, True, True, False, True)
        self.assertTrue(os.path.isfile(self.path('lib', 'alpha', 'a.exe')))


class CleanTargetUnnamedFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        with open(os.path.join(self.dir, 'loose.exe'), 'wb') as f:                 # a file in the folder and no game folder in it: the lists of the games are searched
            f.write(b'x')

    @staticmethod
    def game(*names, **lists):
        entry = g.AttrDict(id=1, title='alpha', folder_name='alpha', downloads=[g.AttrDict(name=n) for n in names], galaxyDownloads=[], sharedDownloads=[], extras=[])
        entry.update(lists)
        return entry

    def test_a_file_whose_name_is_not_known_is_skipped(self):
        game = self.game(None, 'a.exe', extras=[g.AttrDict(name=None)])
        self.assertIsNone(g.clean_target_problem(self.dir, [game]))                # was a TypeError

    def test_an_entry_without_a_name_attribute_is_skipped_too(self):
        self.assertIsNone(g.clean_target_problem(self.dir, [self.game(None, extras=[g.AttrDict(desc='no name at all')])]))

    def test_the_check_still_finds_the_folder_of_one_game_next_to_unnamed_files(self):
        problem = g.clean_target_problem(self.dir, [self.game(None, 'loose.exe')])
        self.assertIn("looks like the folder of one game ('alpha'", problem)
        self.assertIn("'loose.exe'", problem)


if __name__ == '__main__':
    unittest.main()
