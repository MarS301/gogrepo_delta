"""`clean` refuses a folder that looks like the folder of ONE game instead of the library folder (entry 0.5.54). Giving clean the game
folder made its subfolders (extras, ...) count as games that are not in the manifest, while the files of the game were never looked at."""
import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g


def download(name, data=b'x'):
    return g.AttrDict(name=name, desc=name, lang='English', os_type='windows', size=len(data), md5=hashlib.md5(data).hexdigest(),
                      href='http://x/' + name, version='1', updated='2020', old_updated='2020', prev_verified=False, force_change=False,
                      unreleased=False, md5_exempt=False, old_name=None, gog_data=g.AttrDict())


def game(folder, installers=('setup.exe',), extras=('manual.pdf',)):
    return g.AttrDict(id=abs(hash(folder)) % 100000, title=folder, folder_name=folder, long_title=folder, genre='', store_url='/g', rating=0,
                      release_timestamp=0, changelog='', has_updates=False, serial='', bg_url='', image_url='',
                      downloads=[download(n) for n in installers], galaxyDownloads=[], sharedDownloads=[], extras=[download(n) for n in extras])


class TargetTests(unittest.TestCase):
    """clean_target_problem on its own, with the manifest items given directly."""
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.items = [game('alpha'), game('beta', installers=('beta_setup.exe',), extras=())]

    def make(self, *parts, file=False):
        path = os.path.join(self.dir, *parts)
        if file:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'w').close()
        else:
            os.makedirs(path, exist_ok=True)
        return path

    def test_a_library_folder_with_game_folders_is_accepted(self):
        lib = self.make('lib')
        self.make('lib', 'alpha')
        self.make('lib', 'beta')
        self.assertIsNone(g.clean_target_problem(lib, self.items))

    def test_one_known_game_folder_is_enough_and_unknown_folders_next_to_it_are_fine(self):
        lib = self.make('lib')
        self.make('lib', 'alpha')
        self.make('lib', 'old stuff')
        self.make('lib', '!orphaned')
        self.assertIsNone(g.clean_target_problem(lib, self.items))

    def test_the_folder_of_one_game_is_refused_by_its_name(self):
        # the mistake of the report: the game folder itself, with an extras folder and a stray file in it
        game_dir = self.make('lib', 'alpha')
        self.make('lib', 'alpha', 'extras')
        self.make('lib', 'alpha', 'random.txt', file=True)
        problem = g.clean_target_problem(game_dir, self.items)
        self.assertIn("looks like the folder of one game ('alpha': its name is the folder name of that game)", problem)
        self.assertIn('Nothing was changed', problem)
        self.assertIn(os.path.abspath(game_dir), problem)
        self.assertTrue(problem.endswith("instead: '%s'" % os.path.dirname(os.path.abspath(game_dir))), problem)
        self.assertIn(g.ORPHAN_DIR_NAME, problem)

    def test_a_game_folder_with_another_name_is_recognised_by_its_files(self):
        game_dir = self.make('my games', 'Alpha (copy)')
        self.make('my games', 'Alpha (copy)', 'setup.exe', file=True)
        problem = g.clean_target_problem(game_dir, self.items)
        self.assertIn("it contains the file 'setup.exe' of that game", problem)
        self.assertIn("'alpha'", problem)

    def test_an_extra_of_the_game_counts_as_well(self):
        game_dir = self.make('somewhere')
        self.make('somewhere', 'manual.pdf', file=True)
        self.assertIn("contains the file 'manual.pdf'", g.clean_target_problem(game_dir, self.items))

    def test_a_library_wins_over_a_stray_installer_in_it(self):
        lib = self.make('lib')
        self.make('lib', 'alpha')
        self.make('lib', 'setup.exe', file=True)
        self.assertIsNone(g.clean_target_problem(lib, self.items))

    def test_a_library_folder_that_is_named_like_a_game_is_accepted_when_it_holds_games(self):
        lib = self.make('alpha')            # unlikely, but this folder holds game folders, so it is a library
        self.make('alpha', 'beta')
        self.assertIsNone(g.clean_target_problem(lib, self.items))

    def test_folders_that_look_like_nothing_known_are_accepted(self):
        empty = self.make('empty')
        other = self.make('other')
        self.make('other', 'notes.txt', file=True)
        self.make('other', 'some folder')
        self.assertIsNone(g.clean_target_problem(empty, self.items))
        self.assertIsNone(g.clean_target_problem(other, self.items))
        self.assertIsNone(g.clean_target_problem(empty, []))

    def test_the_special_folders_do_not_make_a_library(self):
        # a folder named like a game but inside a game's !images: not a game folder of a library
        game_dir = self.make('lib', 'alpha')
        self.make('lib', 'alpha', g.IMAGES_DIR_NAME)
        items = self.items + [game(g.IMAGES_DIR_NAME)]
        self.assertIn('looks like the folder of one game', g.clean_target_problem(game_dir, items))

    def test_a_path_that_is_not_a_folder_is_reported_in_words(self):
        self.assertIn('is not a folder', g.clean_target_problem(os.path.join(self.dir, 'missing'), self.items))
        self.make('afile', file=True)
        self.assertIn('is not a folder', g.clean_target_problem(os.path.join(self.dir, 'afile'), self.items))

    def test_case_does_not_matter_where_the_file_system_ignores_it(self):
        game_dir = self.make('lib', 'ALPHA')
        mixed = self.make('lib2', 'gamma')
        items = self.items + [game('Gamma')]
        # Both behaviours are set explicitly, so the test gives the same result on Windows (where the real normcase lowercases) and on Linux.
        with mock.patch.object(g.os.path, 'normcase', lambda p: p.lower()):     # like Windows
            self.assertIn("'alpha'", g.clean_target_problem(game_dir, items))
            self.assertIn("'Gamma'", g.clean_target_problem(mixed, items))      # the manifest says Gamma, the folder is called gamma
        with mock.patch.object(g.os.path, 'normcase', lambda p: p):             # like Linux: ALPHA is not the game folder alpha
            self.assertIsNone(g.clean_target_problem(game_dir, items))
            self.assertIsNone(g.clean_target_problem(mixed, items))

    def test_items_of_old_manifests_without_a_folder_name_or_download_lists_do_not_crash(self):
        old = g.AttrDict(title='alpha', downloads=[download('setup.exe')])
        game_dir = self.make('lib', 'alpha')
        self.assertIn("'alpha'", g.clean_target_problem(game_dir, [old]))
        self.assertIsNone(g.clean_target_problem(self.make('lib2'), [old]))


class CleanThroughMainTests(unittest.TestCase):
    """The mistake of the report, through main(): everything stays exactly as it was."""
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset()
        g.save_manifest([game('alpha')])
        self.lib = os.path.join(self.dir, 'lib')
        for parts in (('alpha', 'extras', 'manual.pdf'), ('alpha', 'setup.exe'), ('alpha', 'random.txt'),
                      ('alpha', g.DOWNLOADING_DIR_NAME, 'part_game', 'x.part')):
            path = os.path.join(self.lib, *parts)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'w').close()
        self.game_dir = os.path.join(self.lib, 'alpha')

    def tree(self):
        return sorted(os.path.join(r, n) for r, ds, fs in os.walk(self.lib) for n in ds + fs)

    def run_clean(self, *argv):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            status = g.main(g.process_argv(['gogrepo_delta.py', 'clean'] + list(argv) + ['-nolog']))
        return status, [(r.levelname, r.getMessage()) for r in logs.records]

    def test_the_game_folder_is_refused_with_a_message_and_nothing_changes(self):
        before = self.tree()
        status, log = self.run_clean(self.game_dir)
        self.assertEqual(status, 1)
        errors = [m for level, m in log if level == 'ERROR' and 'looks like the folder of one game' in m]
        self.assertEqual(len(errors), 1)                             # said once (the summary then repeats only that the run stopped)
        self.assertIn("instead: '%s'" % self.lib, errors[0])
        self.assertEqual(self.tree(), before)                       # no !orphaned created, nothing moved or renamed
        self.assertFalse(os.path.exists(os.path.join(self.game_dir, g.ORPHAN_DIR_NAME)))

    def test_a_dry_run_is_refused_too(self):
        before = self.tree()
        status, log = self.run_clean(self.game_dir, '-dryrun')
        self.assertEqual(status, 1)
        self.assertTrue(any('looks like the folder of one game' in m for _, m in log))
        self.assertEqual(self.tree(), before)

    def test_the_summary_names_the_stop(self):
        status, log = self.run_clean(self.game_dir)
        self.assertIn('   FAILED: 1', [m for _, m in log])

    def test_other_stages_in_the_same_run_do_not_start_either(self):
        before = self.tree()
        status, log = self.run_clean(self.game_dir, '-partials', '-provisional', '-orphans')
        self.assertEqual(status, 1)
        self.assertEqual(self.tree(), before)

    def test_the_right_folder_still_works_and_catches_the_stray_file(self):
        status, log = self.run_clean(self.lib)
        self.assertEqual(status, 0, log)
        self.assertTrue(any("orphaning file 'alpha" in m and 'random.txt' in m for _, m in log))
        self.assertTrue(os.path.exists(os.path.join(self.lib, g.ORPHAN_DIR_NAME, 'alpha', 'random.txt')))
        self.assertFalse(os.path.exists(os.path.join(self.game_dir, 'random.txt')))
        self.assertTrue(os.path.exists(os.path.join(self.game_dir, 'extras', 'manual.pdf')))

    def test_stages_without_the_manifest_are_not_affected(self):
        # -partials works on !downloading alone, so no manifest is read and the folder is not judged
        status, log = self.run_clean(self.game_dir, '-partials')
        self.assertEqual(status, 0, log)
        self.assertFalse(os.path.exists(os.path.join(self.game_dir, g.DOWNLOADING_DIR_NAME, 'part_game')))
        self.assertFalse(any('looks like the folder of one game' in m for _, m in log))


if __name__ == '__main__':
    unittest.main()
