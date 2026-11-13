"""Cleanup must not mistake missing manifest metadata for proof that files are obsolete."""
import os
import shutil
import tempfile
import unittest

import _bootstrap  # noqa: F401
import gogrepo_delta as g


class IncompleteMetadataCleanupTests(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tempdir = tempfile.mkdtemp(prefix='cleanup_incomplete_')
        os.chdir(self.tempdir)
        self.addCleanup(os.chdir, self.cwd)
        self.addCleanup(shutil.rmtree, self.tempdir, ignore_errors=True)
        g.run_report.reset()

    @staticmethod
    def item(name, **overrides):
        values = dict(name=name, force_change=False, updated=None, old_updated=None)
        values.update(overrides)
        return g.AttrDict(**values)

    def game(self, filename=None):
        return g.AttrDict(
            title='Game', folder_name='Game',
            downloads=[self.item(filename)], galaxyDownloads=[],
            sharedDownloads=[], extras=[],
        )

    def test_clean_preserves_unrecognized_game_files_when_any_filename_is_unknown(self):
        library = os.path.join(self.tempdir, 'library')
        game_dir = os.path.join(library, 'Game')
        os.makedirs(game_dir)
        unknown_file = os.path.join(game_dir, 'setup-from-previous-manifest.exe')
        known_file = os.path.join(game_dir, 'known.exe')
        with open(unknown_file, 'wb') as f:
            f.write(b'valuable installer')
        with open(known_file, 'wb') as f:
            f.write(b'known')
        game = self.game(None)
        game.downloads.append(self.item('known.exe'))

        g.cmd_clean(library, False, [game])

        with open(unknown_file, 'rb') as f:
            self.assertEqual(f.read(), b'valuable installer')
        self.assertTrue(os.path.isfile(known_file))
        self.assertFalse(os.path.exists(os.path.join(library, g.ORPHAN_DIR_NAME, 'Game', os.path.basename(unknown_file))))

    def test_clean_preserves_files_when_a_released_extra_has_no_filename(self):
        library = os.path.join(self.tempdir, 'library')
        game_dir = os.path.join(library, 'Game')
        os.makedirs(game_dir)
        local_extra = os.path.join(game_dir, 'manual.pdf')
        with open(local_extra, 'wb') as f:
            f.write(b'valuable manual')
        game = self.game('setup.exe')
        game.extras = [self.item(None, unreleased=False)]

        g.cmd_clean(library, False, [game])

        with open(local_extra, 'rb') as f:
            self.assertEqual(f.read(), b'valuable manual')

    def test_unreleased_extra_without_a_filename_does_not_disable_normal_cleanup(self):
        library = os.path.join(self.tempdir, 'library')
        game_dir = os.path.join(library, 'Game')
        os.makedirs(game_dir)
        obsolete = os.path.join(game_dir, 'obsolete.exe')
        with open(obsolete, 'wb') as f:
            f.write(b'obsolete')
        game = self.game('current.exe')
        game.extras = [self.item(None, unreleased=True)]

        g.cmd_clean(library, False, [game])

        self.assertFalse(os.path.exists(obsolete))
        self.assertTrue(os.path.isfile(os.path.join(library, g.ORPHAN_DIR_NAME, 'Game', 'obsolete.exe')))

    def test_clean_still_orphans_obsolete_files_when_all_filenames_are_known(self):
        library = os.path.join(self.tempdir, 'library')
        game_dir = os.path.join(library, 'Game')
        os.makedirs(game_dir)
        obsolete = os.path.join(game_dir, 'obsolete.exe')
        with open(obsolete, 'wb') as f:
            f.write(b'obsolete')
        g.cmd_clean(library, False, [self.game('current.exe')])
        self.assertFalse(os.path.exists(obsolete))
        orphaned = os.path.join(library, g.ORPHAN_DIR_NAME, 'Game', 'obsolete.exe')
        self.assertTrue(os.path.isfile(orphaned))
        with open(orphaned, 'rb') as f:
            self.assertEqual(f.read(), b'obsolete')

    def test_work_dir_cleanup_preserves_unknown_files_when_filename_is_missing(self):
        work = os.path.join(self.tempdir, 'work')
        game_dir = os.path.join(work, 'Game')
        os.makedirs(game_dir)
        unknown_file = os.path.join(game_dir, 'partial-setup.bin')
        with open(unknown_file, 'wb') as f:
            f.write(b'partial data')
        game = self.game(None)

        g._clean_work_dir(work, {'Game': game}, False)

        with open(unknown_file, 'rb') as f:
            self.assertEqual(f.read(), b'partial data')

    def test_work_dir_cleanup_preserves_subdirectories_when_filename_is_unknown(self):
        work = os.path.join(self.tempdir, 'work')
        nested = os.path.join(work, 'Game', 'nested')
        os.makedirs(nested)
        nested_file = os.path.join(nested, 'recoverable.part')
        with open(nested_file, 'wb') as f:
            f.write(b'recoverable')

        g._clean_work_dir(work, {'Game': self.game(None)}, False)

        with open(nested_file, 'rb') as f:
            self.assertEqual(f.read(), b'recoverable')

    def test_work_dir_cleanup_still_removes_obsolete_files_with_complete_metadata(self):
        work = os.path.join(self.tempdir, 'work')
        game_dir = os.path.join(work, 'Game')
        os.makedirs(game_dir)
        obsolete = os.path.join(game_dir, 'obsolete.bin')
        with open(obsolete, 'wb') as f:
            f.write(b'obsolete')

        g._clean_work_dir(work, {'Game': self.game('current.exe')}, False)

        self.assertFalse(os.path.exists(obsolete))


if __name__ == '__main__':
    unittest.main()
