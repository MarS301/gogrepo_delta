"""Entry 0.5.91: the rest of the path. The game folder is made portable where `update` builds it (the slug GOG sends, plus the suffix of movies and duplicate titles), the folders of the MD5 XML tree
(game, operating system, language) are checked, and on Windows without long path support a path over 259 characters gets one combined warning (the download is tried anyway)."""
import logging
import os
import shutil
import sys
import tempfile
import threading
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
import test_run_summary as trs


class Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def warnings(self):
        return [r.getMessage() for r in self.records if r.levelname == 'WARNING']


class LogCase(unittest.TestCase):
    def setUp(self):
        self.handler = Capture()
        g.rootLogger.addHandler(self.handler)
        self.addCleanup(g.rootLogger.removeHandler, self.handler)
        g.run_report.reset()
        self.addCleanup(g.run_report.reset)
        g.flush_summarised()                    # nothing left over from another test


class GameFolderNameTests(LogCase):
    def test_a_good_slug_is_kept_without_a_warning(self):
        self.assertEqual(g._game_folder_name('wing_commander_iv_30th'), 'wing_commander_iv_30th')
        self.assertEqual(g._game_folder_name('some_movie', '_movie'), 'some_movie_movie')
        self.assertEqual([m for m in self.handler.warnings() if 'game folder' in m], [])

    def test_an_unsafe_slug_is_made_portable_and_the_suffix_is_kept(self):
        self.assertEqual(g._game_folder_name('bad:slug?x', '_1234'), 'bad_slug_x_1234')
        self.assertEqual(g._game_folder_name('con'), '_con')
        self.assertEqual(g._game_folder_name('../up'), '.._up')
        self.assertEqual(len([m for m in self.handler.warnings() if 'game folder name' in m]), 3)

    def test_a_very_long_slug_is_shortened(self):
        folder = g._game_folder_name('s' * 300, '_movie')
        self.assertLessEqual(len(folder.encode()), g.SHORTEN_FILE_NAME_TO)
        self.assertIsNone(g.unsafe_file_name_reason(folder))


class UpdateFolderTests(trs.TempDirTests):
    def api(self, slugs):
        base = trs.games_api()

        def request(session, url, args=None, **kwargs):
            response = base(session, url, args, **kwargs)
            data = response.json()
            if 'products' in data:
                data['products'] = [dict(data['products'][0], id=1000 + i, slug=slug, title=slug) for i, slug in enumerate(slugs)]
            return response
        return request

    def update(self, slugs):
        with mock.patch.object(g, 'request', self.api(slugs)), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})):
            g.cmd_update(['windows'], ['en'], False, False, False, [], [], False, 'both', 'resume', False, False, False, False, False, False, False)

    def test_update_stores_a_portable_folder_and_keeps_the_slug_as_title(self):
        self.update(['bad:slug?x', 'good_slug'])
        games = {game.id: game for game in g.load_manifest()}
        self.assertEqual((games[1000].title, games[1000].folder_name), ('bad:slug?x', 'bad_slug_x'))
        self.assertEqual((games[1001].title, games[1001].folder_name), ('good_slug', 'good_slug'))

    def test_two_games_with_the_same_unsafe_title_get_two_portable_folders(self):
        self.update(['dup:x', 'dup:x', 'other'])
        folders = sorted(game.folder_name for game in g.load_manifest())
        self.assertEqual(folders, ['dup_x_1000', 'dup_x_1001', 'other'])

    def test_a_folder_that_was_not_portable_before_gets_the_rename_marker(self):
        entry = g.AttrDict(id=1000, title='bad:slug', folder_name='bad:slug', long_title='x', genre='', store_url='/g', rating=0, release_timestamp=0, changelog='',
                           has_updates=False, serial='', bg_url='', image_url='', downloads=[], galaxyDownloads=[], sharedDownloads=[], extras=[])
        g.save_manifest([entry])
        self.update(['bad:slug'])
        game = g.load_manifest()[0]
        self.assertEqual(game.folder_name, 'bad_slug')
        self.assertEqual(game.old_folder_name, 'bad:slug')           # the next download, verify or clean moves the folder


class Md5FolderTests(trs.TempDirTests):
    def entry(self, name, os_type='windows', lang='English'):
        e = g.AttrDict(name=name, desc=name, size=1, md5=None, old_name=None, lang=lang, os_type=os_type, provisional_name=None)
        e.gog_data = g.AttrDict(md5_xml=g.AttrDict(text='<file/>'))
        return e

    def game(self, folder, *downloads):
        return g.AttrDict(id=1, title=folder, folder_name=folder, downloads=list(downloads), galaxyDownloads=[], sharedDownloads=[], extras=[])

    def setUp(self):
        super().setUp()
        self.handler = Capture()
        g.rootLogger.addHandler(self.handler)
        self.addCleanup(g.rootLogger.removeHandler, self.handler)
        g.flush_summarised()

    def test_the_tables_of_operating_systems_and_languages_are_portable(self):
        for lang_name in g.LANG_TABLE.values():
            self.assertIsNone(g.unsafe_file_name_reason(lang_name), lang_name)
        for os_name in ('windows', 'linux', 'mac'):
            self.assertIsNone(g.unsafe_file_name_reason(os_name), os_name)

    def test_an_unsafe_game_folder_gets_no_xml_tree_and_nothing_outside(self):
        g.save_manifest([self.game('../evil', self.entry('a.exe')), self.game('good', self.entry('b.exe'))], update_md5_xml=True)
        self.assertTrue(os.path.isfile(os.path.join(g.MD5_DIR_NAME, 'good', 'downloads', 'windows', 'English', 'b.exe.xml')))
        self.assertEqual(sorted(os.listdir(g.MD5_DIR_NAME)), ['good'])
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'evil')))
        g.flush_summarised()
        self.assertEqual(len([m for m in self.handler.warnings() if 'MD5 XML data of 1 folder(s) was not saved' in m and '../evil' in m]), 1)

    def test_an_unsafe_operating_system_or_language_folder_is_skipped(self):
        g.save_manifest([self.game('alpha', self.entry('a.exe', os_type='../x'), self.entry('b.exe', lang='a:b'), self.entry('c.exe'))], update_md5_xml=True)
        tree = os.path.join(g.MD5_DIR_NAME, 'alpha', 'downloads')
        self.assertEqual(os.listdir(tree), ['windows'])
        self.assertEqual(os.listdir(os.path.join(tree, 'windows')), ['English'])
        self.assertEqual(os.listdir(os.path.join(tree, 'windows', 'English')), ['c.exe.xml'])
        self.assertFalse(os.path.exists(os.path.join(g.MD5_DIR_NAME, 'alpha', 'x')))
        g.flush_summarised()
        self.assertEqual(len([m for m in self.handler.warnings() if 'MD5 XML data of 2 folder(s)' in m]), 1)


class PathLimitQueueTests(LogCase):
    PROVISIONAL_LENGTH = 200

    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        # A library path of a length that does not depend on the temporary folder (the one of a macOS runner is long, a Windows one not): one folder is filled up so that the path of the
        # provisional folder, the longest of the three places, is exactly PROVISIONAL_LENGTH characters. A name of a few characters then stays far below the limit of 259.
        tail = os.path.join(g.DOWNLOADING_DIR_NAME, g.PROVISIONAL_DIR_NAME, 'alpha')
        fill = self.PROVISIONAL_LENGTH - len(os.path.abspath(self.dir)) - 1 - len(tail) - 1               # separator, filler, separator, tail
        if not 1 <= fill <= 255:
            self.skipTest('the temporary folder has a path of an unusable length (%d characters)' % len(os.path.abspath(self.dir)))
        self.lib = os.path.join(self.dir, 'l' * fill)
        self.home = os.path.join(self.lib, 'alpha')
        self.downloaddir = os.path.join(self.lib, g.DOWNLOADING_DIR_NAME, 'alpha')
        self.provisionaldir = os.path.join(self.lib, tail)
        self.assertEqual(len(os.path.abspath(self.provisionaldir)), self.PROVISIONAL_LENGTH)

    def longest_with(self, name_length):
        return len(os.path.abspath(os.path.join(self.provisionaldir, 'n' * name_length)))

    def queue(self, names, limit_in_effect=True):
        items = [g.AttrDict(name=n, size=100, href='http://x/%d' % i, md5=None) for i, n in enumerate(names)]
        job = SimpleNamespace(work_dict={}, provisional_dict={}, sizes={}, lock=threading.Lock(), downloadLimit=None, dryrun=True, skippreallocation=True, queue=None)
        game = g.AttrDict(id=1, title='alpha', folder_name='alpha')
        with mock.patch.object(g, '_windows_path_limit_in_effect', lambda: limit_in_effect):
            g._queue_item_downloads(job, game, items, self.home, self.downloaddir, self.provisionaldir, [], [game])
        return job

    def notes(self):
        g.flush_summarised()
        return [m for m in self.handler.warnings() if 'need a path longer than' in m]

    def name_of_length_for(self, total):
        return 'n' * (total - len(os.path.abspath(self.provisionaldir)) - 1)       # minus the separator between folder and name

    def test_the_limit_is_259_characters(self):
        at_limit, over = self.name_of_length_for(259), self.name_of_length_for(260)
        self.assertEqual(self.longest_with(len(at_limit)), 259)
        job = self.queue([at_limit])
        self.assertEqual(len(job.work_dict), 1)
        self.assertEqual(self.notes(), [])
        job = self.queue([over])
        self.assertEqual(len(job.work_dict), 1)                                   # warned, but the download is tried
        self.assertEqual(len(self.notes()), 1)

    def test_one_combined_warning_with_the_count_and_the_names_and_the_fix(self):
        names = [self.name_of_length_for(262) + str(i) for i in range(3)] + ['short.exe']
        job = self.queue(names)
        self.assertEqual(len(job.work_dict), 4)
        notes = self.notes()
        self.assertEqual(len(notes), 1)
        self.assertIn('3 file(s) need a path longer than 259 characters', notes[0])
        self.assertIn('LongPathsEnabled', notes[0])
        self.assertIn('alpha/' + names[0], notes[0])
        self.assertNotIn('short.exe', notes[0])
        self.assertEqual(g.run_report.failures, [])                                 # a warning, not a failure

    def test_no_warning_when_long_paths_work_or_not_on_windows(self):
        self.queue([self.name_of_length_for(300)], limit_in_effect=False)
        self.assertEqual(self.notes(), [])

    def test_the_longest_of_the_three_places_counts(self):
        # a name whose final path is exactly 259 characters: the file is fine at its destination, but the provisional path (in !downloading\\!provisional) is longer
        name = 'n' * (259 - len(os.path.abspath(self.home)) - 1)
        self.assertEqual(len(os.path.abspath(os.path.join(self.home, name))), 259)
        self.assertGreater(self.longest_with(len(name)), 259)
        self.queue([name])
        self.assertEqual(len(self.notes()), 1)

    def test_a_file_that_is_already_up_to_date_is_not_mentioned(self):
        name = self.name_of_length_for(262)
        os.makedirs(self.home)
        with open(os.path.join(self.home, name), 'wb') as f:
            f.write(b'x' * 100)
        job = self.queue([name])
        self.assertEqual(job.work_dict, {})
        self.assertEqual(self.notes(), [])


class WindowsPathLimitDetectionTests(unittest.TestCase):
    def fake_winreg(self, value=None, open_error=None, query_error=None):
        module = types.ModuleType('winreg')
        module.HKEY_LOCAL_MACHINE = object()

        class Key(object):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def open_key(root, path):
            if open_error:
                raise open_error
            return Key()

        def query(key, name):
            if query_error:
                raise query_error
            assert name == 'LongPathsEnabled'
            return (value, 4)
        module.OpenKey, module.QueryValueEx = open_key, query
        return module

    def in_effect(self, platform='win32', module=None):
        modules = {'winreg': module} if module is not None else {}
        with mock.patch.object(g.sys, 'platform', platform), mock.patch.dict(sys.modules, modules):
            return g._windows_path_limit_in_effect()

    def test_not_windows_means_no_limit(self):
        self.assertFalse(self.in_effect('linux'))
        self.assertFalse(self.in_effect('darwin'))

    def test_long_paths_switched_on_means_no_limit(self):
        self.assertFalse(self.in_effect(module=self.fake_winreg(1)))

    def test_long_paths_off_or_unreadable_means_the_limit_applies(self):
        self.assertTrue(self.in_effect(module=self.fake_winreg(0)))
        self.assertTrue(self.in_effect(module=self.fake_winreg(2)))                   # only the value 1 switches long paths on
        self.assertTrue(self.in_effect(module=self.fake_winreg(open_error=OSError('no key'))))
        self.assertTrue(self.in_effect(module=self.fake_winreg(query_error=FileNotFoundError('no value'))))

    def test_winreg_missing_means_the_limit_applies(self):
        with mock.patch.object(g.sys, 'platform', 'win32'), mock.patch.dict(sys.modules, {'winreg': None}):      # None makes the import fail
            self.assertTrue(g._windows_path_limit_in_effect())


if __name__ == '__main__':
    unittest.main()
