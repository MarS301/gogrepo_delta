"""Default language with an English fallback: a game that has no version in your language still gives you the
English one, a game that has your language gives you only that. An explicit -lang stays strict."""
import contextlib
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'download_rig'))
import rig  # noqa: E402

DE, EN = g.LANG_TABLE['de'], g.LANG_TABLE['en']     # 'Deutsch', 'English'


def entry(name, lang, os_type='windows'):
    return SimpleNamespace(name=name, lang=lang, os_type=os_type)


def names(entries):
    return [e.name for e in entries]


class FilterLanguagesTests(unittest.TestCase):
    def test_without_fallback_only_the_wanted_languages(self):
        entries = [entry('de.exe', DE), entry('en.exe', EN)]
        self.assertEqual(names(g.filter_languages(entries, [DE])), ['de.exe'])
        self.assertEqual(names(g.filter_languages(entries, [DE], None)), ['de.exe'])
        self.assertEqual(g.filter_languages([entry('en.exe', EN)], [DE]), [])

    def test_wanted_language_wins_over_the_fallback(self):
        entries = [entry('en.exe', EN), entry('de.exe', DE)]
        self.assertEqual(names(g.filter_languages(entries, [DE], EN)), ['de.exe'])

    def test_fallback_is_used_when_the_wanted_language_is_missing(self):
        self.assertEqual(names(g.filter_languages([entry('en.exe', EN)], [DE], EN)), ['en.exe'])

    def test_the_decision_is_made_per_operating_system(self):
        entries = [entry('win_en.exe', EN), entry('win_de.exe', DE), entry('lin_en.sh', EN, 'linux'), entry('mac_en.pkg', EN, 'mac'), entry('mac_de.pkg', DE, 'mac')]
        self.assertEqual(sorted(names(g.filter_languages(entries, [DE], EN))), ['lin_en.sh', 'mac_de.pkg', 'win_de.exe'])

    def test_all_files_of_the_chosen_language_are_kept(self):
        entries = [entry('part1.bin', DE), entry('part2.bin', DE), entry('setup.exe', DE), entry('en.exe', EN)]
        self.assertEqual(names(g.filter_languages(entries, [DE], EN)), ['part1.bin', 'part2.bin', 'setup.exe'])

    def test_neither_language_gives_nothing(self):
        self.assertEqual(g.filter_languages([entry('fr.exe', g.LANG_TABLE['fr'])], [DE], EN), [])

    def test_several_wanted_languages_count_as_wanted(self):
        entries = [entry('de.exe', DE), entry('fr.exe', g.LANG_TABLE['fr']), entry('en.exe', EN)]
        self.assertEqual(names(g.filter_languages(entries, [DE, g.LANG_TABLE['fr']], EN)), ['de.exe', 'fr.exe'])

    def test_order_is_kept_and_nothing_is_modified(self):
        entries = [entry('b_en.sh', EN, 'linux'), entry('a_de.exe', DE), entry('c_en.exe', EN)]
        result = g.filter_languages(entries, [DE], EN)
        self.assertEqual(names(result), ['b_en.sh', 'a_de.exe'])
        self.assertEqual(len(entries), 3)

    def test_wanting_english_itself_is_harmless(self):
        entries = [entry('en.exe', EN), entry('de.exe', DE)]
        self.assertEqual(names(g.filter_languages(entries, [EN], EN)), ['en.exe'])


def download(name):
    return {'manualUrl': '/downloads/slug/%s' % name, 'name': name, 'version': '1.0', 'date': '', 'size': '10 MB'}


def fake_fetch_file_info(d, fetch_md5, save_md5_xml, session, product_api_context=None, diagnostic=False):
    d.name, d.size, d.md5 = d.desc, 1000, 'md5-' + d.desc


class FilterDownloadsTests(unittest.TestCase):
    """The language is chosen from GOG's data before any file information is requested."""
    def run_filter(self, downloads, lang_list, os_list, fallback):
        out, fetched = [], []

        def tracking_fetch(d, *a, **k):
            fetched.append(d.desc)
            fake_fetch_file_info(d, *a, **k)
        with mock.patch.object(g, 'fetch_file_info', tracking_fetch):
            g.filter_downloads(out, downloads, lang_list, os_list, False, None, None, False, fallback)
        return sorted(e.name for e in out), sorted(fetched)

    def games(self):
        return [(EN, {'windows': [download('en_win_1.exe'), download('en_win_2.exe')], 'linux': [download('en_linux.sh')]}),
                (DE, {'windows': [download('de_win.exe')]})]

    def test_german_windows_and_english_linux(self):
        got, fetched = self.run_filter(self.games(), ['de'], ['windows', 'linux'], 'en')
        self.assertEqual(got, ['de_win.exe', 'en_linux.sh'])
        self.assertEqual(fetched, got)                      # no file info was requested for the ignored English windows files

    def test_strict_without_fallback(self):
        self.assertEqual(self.run_filter(self.games(), ['de'], ['windows', 'linux'], None)[0], ['de_win.exe'])

    def test_only_the_selected_operating_systems(self):
        self.assertEqual(self.run_filter(self.games(), ['de'], ['windows'], 'en')[0], ['de_win.exe'])
        self.assertEqual(self.run_filter(self.games(), ['de'], ['linux'], 'en')[0], ['en_linux.sh'])

    def test_english_is_used_when_the_wanted_language_has_no_files_for_that_system(self):
        games = [(EN, {'windows': [download('en_win.exe')]}), (DE, {'windows': []})]
        self.assertEqual(self.run_filter(games, ['de'], ['windows'], 'en')[0], ['en_win.exe'])

    def test_no_english_either_gives_nothing(self):
        games = [(g.LANG_TABLE['fr'], {'windows': [download('fr_win.exe')]})]
        self.assertEqual(self.run_filter(games, ['de'], ['windows'], 'en'), ([], []))

    def test_chinese_locale_example(self):
        games = [(EN, {'windows': [download('en.exe')]}), (g.LANG_TABLE['cn'], {'windows': [download('cn.exe')]})]
        self.assertEqual(self.run_filter(games, ['cn'], ['windows'], 'en')[0], ['cn.exe'])
        self.assertEqual(self.run_filter(games[:1], ['cn'], ['windows'], 'en')[0], ['en.exe'])

    def test_explicit_languages_are_never_widened(self):
        self.assertEqual(self.run_filter(self.games()[:1], ['de'], ['windows'], None)[0], [])


class FakeResponse(object):
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def games_api(interrupt_on_id=None):
    """Three games: German+English / English only / German Windows but English-only Linux."""
    detail = {
        1000: [(EN, {'windows': [download('alpha_en.exe')]}), (DE, {'windows': [download('alpha_de.exe')]})],
        1001: [(EN, {'windows': [download('beta_en.exe')]})],
        1002: [(DE, {'windows': [download('gamma_de.exe')]}), (EN, {'windows': [download('gamma_en.exe')], 'linux': [download('gamma_linux_en.sh')]})],
    }
    products = [dict(id=1000 + i, slug='game_%d' % i, title='Game %d' % i, category='RPG', image='//images.test/%d' % i,
                     url='/game/game_%d' % i, rating=40, updates=0) for i in range(3)]

    def request(session, url, args=None, **kwargs):
        if '/gameDetails/' in url:
            game_id = int(url.rsplit('/', 1)[1].split('.')[0])
            if game_id == interrupt_on_id:
                raise KeyboardInterrupt()
            return FakeResponse(dict(backgroundImage='', cdKey='', forumLink='', changelog='', releaseTimestamp=1500000000, messages=[],
                                     downloads=detail[game_id], galaxyDownloads=[], extras=[], dlcs=[]))
        return FakeResponse(dict(products=products, totalPages=1))
    return request


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.dir, ignore_errors=True)

    @contextlib.contextmanager
    def api(self, interrupt_on_id=None):
        with mock.patch.object(g, 'request', games_api(interrupt_on_id)), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})), \
                mock.patch.object(g, 'fetch_file_info', fake_fetch_file_info):
            yield

    def update(self, lang_list, fallback, os_list=('windows', 'linux')):
        g.cmd_update(list(os_list), lang_list, True, True, True, [], [], False, 'both', 'resume', False, False, False, False, False, False, False, lang_fallback=fallback)

    def stored(self):
        return {game.title: sorted(d.name for d in game.downloads) for game in g.load_manifest()}

    def test_manifest_gets_german_where_it_exists_and_english_otherwise(self):
        with self.api():
            self.update(['de'], 'en')
        self.assertEqual(self.stored(), {'game_0': ['alpha_de.exe'], 'game_1': ['beta_en.exe'], 'game_2': ['gamma_de.exe', 'gamma_linux_en.sh']})

    def test_without_the_fallback_games_without_german_are_missing(self):
        with self.api():
            self.update(['de'], None)
        self.assertEqual(self.stored(), {'game_0': ['alpha_de.exe'], 'game_1': [], 'game_2': ['gamma_de.exe']})

    def test_explicit_languages_still_work(self):
        with self.api():
            self.update(['de', 'en'], None)
        self.assertEqual(self.stored()['game_0'], ['alpha_de.exe', 'alpha_en.exe'])

    def test_the_fallback_is_saved_with_the_resume_information(self):
        with self.api(interrupt_on_id=1001), self.assertRaises(KeyboardInterrupt):
            self.update(['de'], 'en')
        properties = g.load_resume_manifest()[-1]
        self.assertEqual(properties['lang_fallback'], 'en')
        self.assertEqual(properties['lang_list'], ['de'])

    def test_a_resumed_update_keeps_using_the_saved_fallback(self):
        with self.api(interrupt_on_id=1001), self.assertRaises(KeyboardInterrupt):
            self.update(['de'], 'en')
        with self.api():
            self.update(['de'], None)                       # the resumed run is started without a fallback, the saved one applies
        self.assertEqual(self.stored(), {'game_0': ['alpha_de.exe'], 'game_1': ['beta_en.exe'], 'game_2': ['gamma_de.exe', 'gamma_linux_en.sh']})

    def test_an_old_resume_file_without_the_setting_means_no_fallback(self):
        with self.api(interrupt_on_id=1001), self.assertRaises(KeyboardInterrupt):
            self.update(['de'], None)
        resume = g.load_resume_manifest()
        del resume[-1]['lang_fallback']                     # what a resume file written by an older version looks like
        g.save_resume_manifest(resume)
        with self.api():
            self.update(['de'], 'en')                       # the saved properties (strict) apply to the resumed part
        self.assertEqual(self.stored()['game_1'], [])


class OtherCommandsTests(unittest.TestCase):
    """backup, verify and import use the same selection. Files exist only for the entries that should be chosen."""
    def setUp(self):
        self.cwd, self.root = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.root)
        self.src, self.dest = os.path.join(self.root, 'src'), os.path.join(self.root, 'dest')
        self.contents = {}
        self.games = []
        for gid, title, files in ((1, 'alpha', [('alpha_en.exe', EN, 'windows'), ('alpha_de.exe', DE, 'windows')]),
                                  (2, 'beta', [('beta_en.exe', EN, 'windows')]),
                                  (3, 'gamma', [('gamma_de.exe', DE, 'windows'), ('gamma_en.exe', EN, 'windows'), ('gamma_linux_en.sh', EN, 'linux')])):
            downloads = []
            for name, lang, os_type in files:
                data = (name * 50).encode()[:400]
                self.contents[name] = data
                downloads.append(g.AttrDict(name=name, desc=name, lang=lang, os_type=os_type, size=len(data), md5=g.hashstream.__module__ and __import__('hashlib').md5(data).hexdigest(),
                                            href='http://x/' + name, version='1', updated='2020', old_updated='2020', prev_verified=False, force_change=False, unreleased=False,
                                            md5_exempt=False, old_name=None, gog_data=g.AttrDict()))
            self.games.append(g.AttrDict(id=gid, title=title, folder_name=title, long_title=title, genre='', store_url='/g', rating=0, release_timestamp=0, changelog='',
                                         has_updates=False, serial='', bg_url='', image_url='', downloads=downloads, galaxyDownloads=[], sharedDownloads=[], extras=[]))
        g.save_manifest(self.games)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, folder, name):
        os.makedirs(os.path.join(folder, name.split('_')[0]), exist_ok=True)
        with open(os.path.join(folder, name.split('_')[0], name), 'wb') as f:
            f.write(self.contents[name])

    def files_in(self, folder):
        return sorted(f for _, _, fs in os.walk(folder) for f in fs)

    def test_backup_copies_the_chosen_files_only(self):
        for name in self.contents:
            self.write(self.src, name)
        g.cmd_backup(self.src, self.dest, False, ['windows', 'linux'], ['de'], [], [], False, False, False, lang_fallback='en')
        self.assertEqual(self.files_in(self.dest), ['alpha_de.exe', 'beta_en.exe', 'gamma_de.exe', 'gamma_linux_en.sh'])

    def test_backup_with_an_explicit_language_is_strict(self):
        for name in self.contents:
            self.write(self.src, name)
        g.cmd_backup(self.src, self.dest, False, ['windows', 'linux'], ['de'], [], [], False, False, False)
        self.assertEqual(self.files_in(self.dest), ['alpha_de.exe', 'gamma_de.exe'])

    def test_verify_expects_only_the_chosen_files(self):
        for name in ('alpha_de.exe', 'beta_en.exe', 'gamma_de.exe', 'gamma_linux_en.sh'):     # the English files that are not chosen are absent
            self.write(self.root, name)
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g.rootLogger.info('(marker)')
            g.cmd_verify(self.root, False, [], True, True, False, False, False, [], ['windows', 'linux'], ['de'], False, False, False, [], False, False, False, 0, lang_fallback='en')
        text = '\n'.join(logs.output)
        self.assertNotIn('missing file', text)
        for name in ('alpha_de.exe', 'beta_en.exe', 'gamma_de.exe', 'gamma_linux_en.sh'):
            self.assertIn(name, text)

    def test_verify_with_an_explicit_language_skips_games_without_it(self):
        for name in ('alpha_de.exe', 'gamma_de.exe'):
            self.write(self.root, name)
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g.rootLogger.info('(marker)')
            g.cmd_verify(self.root, False, [], True, True, False, False, False, [], ['windows', 'linux'], ['de'], False, False, False, [], False, False, False, 0)
        text = '\n'.join(logs.output)
        self.assertNotIn('beta_en.exe', text)
        self.assertNotIn('missing file', text)

    def test_import_matches_only_the_chosen_files(self):
        for name in self.contents:
            self.write(self.src, name)
        g.cmd_import(self.src, self.dest, ['windows', 'linux'], ['de'], False, [], [], False, False, False, False, lang_fallback='en')
        self.assertEqual(self.files_in(self.dest), ['alpha_de.exe', 'beta_en.exe', 'gamma_de.exe', 'gamma_linux_en.sh'])

    def test_import_with_an_explicit_language_is_strict(self):
        for name in self.contents:
            self.write(self.src, name)
        g.cmd_import(self.src, self.dest, ['windows', 'linux'], ['de'], False, [], [], False, False, False, False)
        self.assertEqual(self.files_in(self.dest), ['alpha_de.exe', 'gamma_de.exe'])


class DownloadScenarioTests(unittest.TestCase):
    def downloaded(self, name):
        r = rig.run(g, name)
        return sorted(os.path.basename(k) for k, v in r['tree'].items() if v and not k.startswith('!') and not os.path.basename(k).startswith('!'))

    def test_download_with_the_fallback(self):
        self.assertEqual(self.downloaded('lang_fallback_download'), ['setup_alpha_de.exe', 'setup_beta_en.exe', 'setup_gamma_de.exe', 'setup_gamma_linux_en.sh'])

    def test_download_without_the_fallback_is_strict(self):
        self.assertEqual(self.downloaded('lang_strict_download'), ['setup_alpha_de.exe', 'setup_gamma_de.exe'])


if __name__ == '__main__':
    unittest.main()
