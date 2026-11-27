"""Entry 0.5.94: `update` records everything GOG offers (every operating system, every language) unless it is told to keep less; download, verify, import and backup choose when they read
the manifest. `-os` / `-lang` (and the config file) still narrow it, and the value `all` stands for every system / language. When no language was narrowed, a language without a code is
kept too (under the name GOG sends), so a language added to [languages] later needs no `update --full`."""
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
import test_config
from test_language_fallback import download, fake_fetch_file_info, games_api

ALL_OS, ALL_LANG = list(g.VALID_OS_TYPES), list(g.VALID_LANG_TYPES)
DE, EN, FR = g.LANG_TABLE['de'], g.LANG_TABLE['en'], g.LANG_TABLE['fr']

# command line -> (function called by main, position of the os list, of the language list in its arguments)
COMMANDS = {'update': (['update'], 'cmd_update', 0, 1), 'download': (['download', 'somedir'], 'cmd_download', 5, 6), 'import': (['import', 'src', 'dest'], 'cmd_import', 2, 3),
            'verify': (['verify', 'somedir'], 'cmd_verify', 9, 10), 'backup': (['backup', 'src', 'dest'], 'cmd_backup', 3, 4)}


class RunMain(test_config.ConfigTestCase):
    def run_command(self, command, *flags, **detected):
        """What main() passes on for the command: (os list, language list, lang_fallback), and the log lines."""
        argv, function, os_pos, lang_pos = COMMANDS[command]
        args = g.process_argv(['gogrepo_delta.py'] + argv + list(flags) + ['-nolog'])
        with mock.patch.object(g, function) as called, mock.patch.object(g, 'detect_os', return_value=('mac', 'detected')) as detect_os, \
                mock.patch.object(g, 'detect_lang', return_value=(detected.get('lang', 'de'), 'system locale')) as detect_lang, self.assertLogs('gogrepoc', level='INFO') as logs:
            g.rootLogger.info('(marker)')
            g.main(args)
        self.detected = (detect_os.called, detect_lang.called)
        return called.call_args[0][os_pos], called.call_args[0][lang_pos], called.call_args[1].get('lang_fallback'), '\n'.join(logs.output)


class UpdateDefaultTests(RunMain):
    def test_nothing_given_keeps_every_system_and_language_without_a_fallback(self):
        os_list, lang_list, fallback, log = self.run_command('update')
        self.assertEqual((os_list, lang_list, fallback), (ALL_OS, ALL_LANG, None))
        self.assertEqual(self.detected, (False, False))                    # this computer's system and language are not asked
        self.assertIn('no -os given, keeping every operating system (windows, linux, mac)', log)
        self.assertIn('no -lang given, keeping every language', log)

    def test_an_explicit_choice_still_narrows_what_is_kept(self):
        self.assertEqual(self.run_command('update', '-os', 'windows')[:3], (['windows'], ALL_LANG, None))
        self.assertEqual(self.run_command('update', '-lang', 'en', 'de')[:3], (ALL_OS, ['en', 'de'], None))
        self.assertEqual(self.run_command('update', '-os', 'linux', '-lang', 'fr')[:3], (['linux'], ['fr'], None))

    def test_skip_options_keep_everything_except(self):
        self.assertEqual(self.run_command('update', '-skipos', 'mac')[:2], (['windows', 'linux'], ALL_LANG))
        self.assertEqual(self.run_command('update', '-skiplang', 'en')[:2], (ALL_OS, [c for c in ALL_LANG if c != 'en']))

    def test_nothing_is_logged_about_defaults_when_everything_is_given(self):
        log = self.run_command('update', '-os', 'linux', '-lang', 'en')[3]
        self.assertNotIn('no -os given', log)
        self.assertNotIn('no -lang given', log)

    def test_the_other_commands_still_use_this_computer(self):
        for command in ('download', 'import', 'verify', 'backup'):
            self.assertEqual(self.run_command(command)[:3], (['mac'], ['de'], 'en'), command)
            self.assertEqual(self.detected, (True, True), command)

    def test_languages_added_in_the_config_file_are_part_of_everything(self):
        with mock.patch.dict(g.LANG_TABLE, {'xx': 'Klingon'}), mock.patch.object(g, 'VALID_LANG_TYPES', g.VALID_LANG_TYPES + ['xx']):
            self.assertIn('xx', self.run_command('update')[1])


class ConfigTests(RunMain):
    def test_a_common_choice_narrows_update_like_an_option(self):
        self.write('[common]\nlang = de,en\nos = windows\n')
        self.assertEqual(self.run_command('update')[:3], (['windows'], ['de', 'en'], None))

    def test_the_value_all_in_the_update_section_keeps_everything_while_common_narrows_the_others(self):
        self.write('[common]\nlang = de,en\nos = windows,linux\n[update]\nlang = all\nos = all\n')
        self.assertEqual(self.run_command('update')[:3], (ALL_OS, ALL_LANG, None))
        self.assertEqual(self.run_command('download')[:2], (['windows', 'linux'], ['de', 'en']))

    def test_a_choice_in_another_command_section_does_not_touch_update(self):
        self.write('[download]\nlang = de\nos = linux\n[verify]\nlang = fr\n')
        self.assertEqual(self.run_command('update')[:2], (ALL_OS, ALL_LANG))
        self.assertEqual(self.run_command('download')[:2], (['linux'], ['de']))

    def test_an_option_beats_the_config_file(self):
        self.write('[update]\nlang = all\n')
        self.assertEqual(self.run_command('update', '-lang', 'fr')[1], ['fr'])


class AllValueTests(RunMain):
    def test_all_means_every_system_and_language_in_every_command(self):
        for command in COMMANDS:
            os_list, lang_list, fallback, log = self.run_command(command, '-os', 'all', '-lang', 'all')
            self.assertEqual((os_list, lang_list, fallback), (ALL_OS, ALL_LANG, None), command)
            self.assertNotIn('no -os given', log)

    def test_all_for_one_of_them_leaves_the_other_at_its_default(self):
        self.assertEqual(self.run_command('download', '-lang', 'all')[:3], (['mac'], ALL_LANG, None))
        self.assertEqual(self.run_command('download', '-os', 'all')[:3], (ALL_OS, ['de'], 'en'))

    def test_all_in_the_config_file(self):
        self.write('[download]\nlang = all\n')
        self.assertEqual(self.run_command('download')[1], ALL_LANG)

    def test_list_takes_all_as_no_filter(self):
        args = g.process_argv(['gogrepo_delta.py', 'list', '-os', 'all', '-lang', 'all', '-nolog'])
        self.assertEqual((args.os, args.lang), ([], []))

    def test_all_cannot_be_combined_with_other_values(self):
        for flags, option in ((['-os', 'all', 'windows'], '-os'), (['-os', 'linux', 'all'], '-os'), (['-lang', 'all', 'de'], '-lang'), (['-lang', 'en', 'all'], '-lang')):
            for command in ('update', 'download', 'list'):
                with self.subTest(command=command, flags=flags):
                    with mock.patch.object(g, 'error') as error, self.assertRaises(SystemExit) as stop:
                        g.process_argv(['gogrepo_delta.py', command] + (['somedir'] if command == 'download' else []) + flags + ['-nolog'])
                    self.assertEqual(stop.exception.code, 1)
                    self.assertIn('%s all cannot be combined with other values' % option, error.call_args[0][0])

    def test_all_is_no_value_for_the_skip_options(self):
        for flags in (['-skipos', 'all'], ['-skiplang', 'all']):
            with mock.patch.object(g, 'error') as error, self.assertRaises(SystemExit):
                g.process_argv(['gogrepo_delta.py', 'update'] + flags + ['-nolog'])
            self.assertIn('is not one of the valid', error.call_args[0][0])

    def test_a_wrong_value_is_still_refused(self):
        with mock.patch.object(g, 'error') as error, self.assertRaises(SystemExit):
            g.process_argv(['gogrepo_delta.py', 'update', '-lang', 'xx', '-nolog'])
        self.assertIn('specified language "xx"', error.call_args[0][0])


class FilterDownloadsTests(unittest.TestCase):
    """What update records: a language that GOG offers and that has no code is kept when nobody narrowed the languages."""
    KLINGON = 'Klingon'

    def games(self):
        return [(EN, {'windows': [download('en_win.exe')]}), (DE, {'windows': [download('de_win.exe')]}), (self.KLINGON, {'windows': [download('kl_win.exe')], 'linux': [download('kl_lin.sh')]})]

    def kept(self, lang_list, os_list=('windows', 'linux'), fallback=None):
        out = []
        with mock.patch.object(g, 'fetch_file_info', fake_fetch_file_info):
            g.filter_downloads(out, self.games(), list(lang_list), list(os_list), False, None, None, False, fallback)
        return sorted((e.name, e.lang) for e in out)

    def test_every_language_keeps_the_unknown_one_with_its_name(self):
        self.assertEqual(self.kept(ALL_LANG), [('de_win.exe', DE), ('en_win.exe', EN), ('kl_lin.sh', self.KLINGON), ('kl_win.exe', self.KLINGON)])

    def test_the_operating_system_still_narrows(self):
        self.assertEqual(self.kept(ALL_LANG, os_list=['linux']), [('kl_lin.sh', self.KLINGON)])

    def test_narrowed_languages_drop_it(self):
        self.assertEqual(self.kept(['de', 'en']), [('de_win.exe', DE), ('en_win.exe', EN)])
        self.assertEqual(self.kept([c for c in ALL_LANG if c != 'fr']), [('de_win.exe', DE), ('en_win.exe', EN)])      # all but one is a narrowing too: -skiplang fr

    def test_one_missing_known_language_is_a_narrowing(self):
        self.assertEqual(self.kept([c for c in ALL_LANG if c != 'en']), [('de_win.exe', DE)])

    def test_a_language_from_the_config_file_is_known_and_kept_as_before(self):
        with mock.patch.dict(g.LANG_TABLE, {'xx': self.KLINGON}), mock.patch.object(g, 'VALID_LANG_TYPES', ALL_LANG + ['xx']):
            self.assertEqual(self.kept(ALL_LANG + ['xx']), [('de_win.exe', DE), ('en_win.exe', EN), ('kl_lin.sh', self.KLINGON), ('kl_win.exe', self.KLINGON)])
            self.assertEqual(self.kept(['xx']), [('kl_lin.sh', self.KLINGON), ('kl_win.exe', self.KLINGON)])


class DownloadChoosesFromTheFullManifestTests(unittest.TestCase):
    """download, verify, ... read the full manifest with this computer's language (English as the fallback) and do not use the files of other languages."""
    @staticmethod
    def entry(name, lang, os_type='windows'):
        return g.AttrDict(name=name, lang=lang, os_type=os_type)

    def test_the_fallback_and_the_choice_work_on_a_manifest_that_holds_everything(self):
        entries = [self.entry('en_win.exe', EN), self.entry('de_win.exe', DE), self.entry('fr_win.exe', FR), self.entry('kl_win.exe', 'Klingon'),
                   self.entry('en_lin.sh', EN, 'linux'), self.entry('fr_lin.sh', FR, 'linux')]
        names = lambda wanted, fallback: sorted(e.name for e in g.filter_languages(entries, wanted, fallback))
        self.assertEqual(names([DE], EN), ['de_win.exe', 'en_lin.sh'])        # German where there is German, English where there is not
        self.assertEqual(names([DE], None), ['de_win.exe'])
        self.assertEqual(names([FR], EN), ['fr_lin.sh', 'fr_win.exe'])
        self.assertEqual(names([EN], EN), ['en_lin.sh', 'en_win.exe'])        # the unknown language is never chosen


class EndToEndTests(unittest.TestCase):
    """A real `update` run (fake GOG data of test_language_fallback: game_0 has German and English Windows files, game_1 English only, game_2 German Windows and English Windows and Linux)."""
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)

    def update(self, *flags):
        args = g.process_argv(['gogrepo_delta.py', 'update', '-nolog'] + list(flags))
        with mock.patch.object(g, 'request', games_api()), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})), \
                mock.patch.object(g, 'fetch_file_info', fake_fetch_file_info):
            g.main(args)
        return dict((game.title, game) for game in g.load_manifest())

    def names(self, games):
        return dict((title, sorted(d.name for d in game.downloads)) for title, game in games.items())

    def test_a_plain_update_stores_every_language_and_system_the_game_offers(self):
        self.assertEqual(self.names(self.update()), {'game_0': ['alpha_de.exe', 'alpha_en.exe'], 'game_1': ['beta_en.exe'],
                                                      'game_2': ['gamma_de.exe', 'gamma_en.exe', 'gamma_linux_en.sh']})

    def test_choosing_from_that_manifest_gives_what_the_old_narrow_update_stored(self):
        games = self.update()
        german_with_english_fallback = dict((title, sorted(e.name for e in g.filter_languages(game.downloads, [DE], EN))) for title, game in games.items())
        self.assertEqual(german_with_english_fallback, {'game_0': ['alpha_de.exe'], 'game_1': ['beta_en.exe'], 'game_2': ['gamma_de.exe', 'gamma_linux_en.sh']})

    def test_a_narrow_update_stores_only_what_was_asked(self):
        self.assertEqual(self.names(self.update('-os', 'windows', '-lang', 'de')), {'game_0': ['alpha_de.exe'], 'game_1': [], 'game_2': ['gamma_de.exe']})

    def test_the_value_all_works_in_a_real_update(self):
        self.assertEqual(self.names(self.update('-os', 'all', '-lang', 'all'))['game_2'], ['gamma_de.exe', 'gamma_en.exe', 'gamma_linux_en.sh'])


if __name__ == '__main__':
    unittest.main()
