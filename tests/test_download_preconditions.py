"""Entry 0.5.88: what cmd_download relies on after its dead code was removed, and the one 'dead' spot that is not dead.

1. handle_game_renames runs first and gives every game it is handed folder_name, galaxyDownloads and sharedDownloads, so cmd_download and
   _item_download_lists no longer default them (the defaults could never run).
2. _prepare_download_file must still create the folder of the final file: a file name is the last part of the download address after unquote(), so
   a name like 'sub%2Fa.exe' reaches it as 'sub/a.exe' and its folder is not the game's folder (the makedirs for it was listed as unreachable, wrongly)."""
import os
import shutil
import tempfile
import threading
import unittest
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import _bootstrap  # noqa: F401
import gogrepo_delta as g


def old_entry(i, **extra):
    """An entry of a manifest from before galaxyDownloads, sharedDownloads and folder_name existed."""
    return g.AttrDict(id=i, title='game_%d' % i, downloads=[], extras=[], **extra)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)


class HandleGameRenamesGivesTheDefaultsTests(Base):
    def test_every_game_handed_to_it_gets_the_three_attributes(self):
        for dryrun in (False, True):
            with self.subTest(dryrun=dryrun):
                items = [old_entry(1), old_entry(2, folder_name='Two'), old_entry(3, galaxyDownloads=[], sharedDownloads=[])]
                g.handle_game_renames(self.dir, items, dryrun)
                self.assertEqual([item.folder_name for item in items], ['game_1', 'Two', 'game_3'])
                for item in items:
                    self.assertEqual((item.galaxyDownloads, item.sharedDownloads), ([], []))

    def test_games_that_are_only_in_the_directory_list_are_not_touched(self):
        # -ids: only the selected games are handed over; the rest of the manifest is given for the directory renames only
        selected, others = [old_entry(1)], [old_entry(1), old_entry(2)]
        g.handle_game_renames(self.dir, selected, True, directory_gamesdb=others)
        self.assertTrue(hasattr(selected[0], 'folder_name'))
        self.assertFalse(hasattr(others[1], 'galaxyDownloads'))         # why _index_items_by_title keeps its own folder_name default

    def test_the_download_helper_works_on_what_handle_game_renames_leaves(self):
        items = [old_entry(1)]
        g.handle_game_renames(self.dir, items, True)
        downloads, galaxy, shared, extras = g._item_download_lists(items[0], False, False, False, False, ['windows'], ['en'])
        self.assertEqual((downloads, galaxy, shared, extras), ([], [], [], []))


class PrepareDownloadFileTests(Base):
    def prepare(self, name):
        job = SimpleNamespace(lock=threading.Lock(), skippreallocation=True)
        paths = [os.path.join(self.dir, folder, 'game', name) for folder in ('home', '!downloading', '!provisional')]
        g._prepare_download_file(job, paths[0], paths[1], paths[2], 10)
        return paths

    def test_the_folders_of_a_plain_file_are_created(self):
        paths = self.prepare('setup.exe')
        for path in paths:
            self.assertTrue(os.path.isdir(os.path.dirname(path)), path)

    def test_the_folder_of_a_name_with_a_separator_is_created_too(self):
        name = unquote(urlparse('https://cdn.example/secure/sub%2Fa.exe?token=1').path.split('/')[-1])
        self.assertEqual(name, 'sub/a.exe')                              # a name from a download address can hold a separator
        paths = self.prepare(name)
        for path in paths:
            self.assertTrue(os.path.isdir(os.path.dirname(path)), path)  # so the folder of the final file differs from the game's folder
        self.assertTrue(os.path.isdir(os.path.join(self.dir, 'home', 'game', 'sub')))


if __name__ == '__main__':
    unittest.main()
