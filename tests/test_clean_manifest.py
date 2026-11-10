"""`clean` refuses to run without a manifest that lists games (entry 0.5.55). The manifest is read from the current folder; a missing one
(without a backup) reads as an empty one, and then every folder of the library is 'not in the manifest' and would be moved to !orphaned."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_clean_target import game


class ManifestProblemTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)

    def test_a_manifest_with_games_is_fine(self):
        self.assertIsNone(g.clean_manifest_problem('lib', [game('alpha')]))

    def test_a_missing_manifest_is_named_with_its_place_and_the_way_out(self):
        problem = g.clean_manifest_problem('lib', [])
        self.assertIn(os.path.abspath(g.MANIFEST_FILENAME), problem)
        self.assertIn(os.getcwd(), problem)
        self.assertIn('does not exist', problem)
        self.assertIn('read from the current folder', problem)
        self.assertIn('Nothing was changed', problem)
        self.assertIn('run update first', problem)
        self.assertIn(g.ORPHAN_DIR_NAME, problem)
        self.assertIn(os.path.abspath('lib'), problem)

    def test_a_manifest_without_games_is_told_apart_from_a_missing_one(self):
        g.save_manifest([])
        problem = g.clean_manifest_problem('lib', [])
        self.assertIn('lists no games', problem)
        self.assertNotIn('does not exist', problem)


class CleanWithoutManifestTests(unittest.TestCase):
    """Through main(): the library stays exactly as it was."""
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset()
        self.lib = os.path.join(self.dir, 'lib')
        self.home = os.path.join(self.dir, 'home')              # where the manifest lives
        self.elsewhere = os.path.join(self.dir, 'elsewhere')    # a folder without a manifest
        os.makedirs(self.home)
        os.makedirs(self.elsewhere)
        for parts in (('alpha', 'setup.exe'), ('alpha', 'extras', 'manual.pdf'), ('beta', 'beta_setup.exe'),
                      (g.DOWNLOADING_DIR_NAME, 'part_game', 'x.part')):
            path = os.path.join(self.lib, *parts)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'w').close()
        os.chdir(self.home)
        g.save_manifest([game('alpha'), game('beta', installers=('beta_setup.exe',), extras=())])

    def tree(self):
        return sorted(os.path.join(r, n) for r, ds, fs in os.walk(self.lib) for n in ds + fs)

    def run_clean(self, *argv):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            status = g.main(g.process_argv(['gogrepo_delta.py', 'clean', self.lib] + list(argv) + ['-nolog']))
        return status, [(r.levelname, r.getMessage()) for r in logs.records]

    def test_the_normal_case_still_works_with_the_manifest_in_the_current_folder(self):
        status, log = self.run_clean()
        self.assertEqual(status, 0, log)
        self.assertEqual(os.listdir(self.lib).count('alpha'), 1)
        self.assertEqual(os.listdir(self.lib).count('beta'), 1)

    def test_run_from_another_folder_nothing_is_moved(self):
        # the mistake: the manifest is in `home`, clean is started in `elsewhere`
        os.chdir(self.elsewhere)
        before = self.tree()
        status, log = self.run_clean()
        self.assertEqual(status, 1)
        errors = [m for level, m in log if level == 'ERROR' and 'needs the manifest' in m]
        self.assertEqual(len(errors), 1)
        self.assertIn('does not exist', errors[0])
        self.assertEqual(self.tree(), before)
        self.assertFalse(os.path.exists(os.path.join(self.lib, g.ORPHAN_DIR_NAME)))
        self.assertIn('   FAILED: 1', [m for _, m in log])

    def test_a_dry_run_is_refused_too(self):
        os.chdir(self.elsewhere)
        before = self.tree()
        status, log = self.run_clean('-dryrun')
        self.assertEqual(status, 1)
        self.assertTrue(any('needs the manifest' in m for _, m in log))
        self.assertEqual(self.tree(), before)

    def test_a_manifest_that_lists_no_games_is_refused(self):
        g.save_manifest([])
        before = self.tree()
        status, log = self.run_clean()
        self.assertEqual(status, 1)
        self.assertTrue(any('lists no games' in m for level, m in log if level == 'ERROR'))
        self.assertEqual(self.tree(), before)

    def test_other_stages_of_the_same_run_do_not_start_either(self):
        os.chdir(self.elsewhere)
        before = self.tree()
        status, log = self.run_clean('-partials', '-provisional', '-orphans')
        self.assertEqual(status, 1)
        self.assertEqual(self.tree(), before)

    def test_stages_that_need_no_manifest_are_not_affected(self):
        os.chdir(self.elsewhere)
        status, log = self.run_clean('-partials')
        self.assertEqual(status, 0, log)
        self.assertFalse(os.path.exists(os.path.join(self.lib, g.DOWNLOADING_DIR_NAME, 'part_game')))      # really done
        self.assertFalse(any('needs the manifest' in m for _, m in log))

    def test_the_check_comes_before_the_one_for_a_game_folder(self):
        os.chdir(self.elsewhere)
        status, log = self.run_clean()
        self.assertFalse(any('looks like the folder of one game' in m for _, m in log))


if __name__ == '__main__':
    unittest.main()
