"""Entry 0.5.93: languages. The names in LANG_TABLE are the names GOG uses; a language that GOG offers and that the table lacks could not be chosen and its files were dropped without a word.
Now `update` ends with one combined warning that names such languages, and the config file can add them: a section [languages] with lines "code = name"."""
import contextlib
import io
import os
import runpy
import subprocess
import sys
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
import test_config
import test_run_summary as trs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parser_for(text):
    parser = g.make_config_parser()
    parser.read_string(text)
    return parser


class LoadExtraLanguagesTests(unittest.TestCase):
    EXISTING = {'de': 'Deutsch', 'en': 'English'}

    def load(self, text, existing=None):
        return g.load_extra_languages(parser_for(text), self.EXISTING if existing is None else existing, path='x.cfg')

    def assertRefused(self, text, *words):
        with self.assertRaises(g.ConfigError) as caught:
            self.load(text)
        for word in ('x.cfg', '[languages]') + words:
            self.assertIn(word, str(caught.exception))

    def test_no_section_and_no_file_add_nothing(self):
        self.assertEqual(self.load('[settings]\nhttp_timeout = 20\n'), {})
        self.assertEqual(g.load_extra_languages(None, self.EXISTING), {})

    def test_entries_are_added_with_the_name_exactly_as_written(self):
        self.assertEqual(self.load('[languages]\nxx = Klingon\nyy_2 = \u0442\u0435\u0441\u0442 (AL)\n'), {'xx': 'Klingon', 'yy_2': '\u0442\u0435\u0441\u0442 (AL)'})

    def test_surrounding_spaces_are_dropped_and_the_case_of_the_name_is_kept(self):
        self.assertEqual(self.load('[languages]\nxx =   Klingon Standard  \n'), {'xx': 'Klingon Standard'})

    def test_an_empty_value_means_not_set(self):
        self.assertEqual(self.load('[languages]\nxx =\n'), {})

    def test_the_code_is_written_in_any_case_and_used_in_lower_case(self):
        self.assertEqual(self.load('[languages]\nXX = Klingon\n'), {'xx': 'Klingon'})

    def test_codes_that_cannot_be_typed_after_lang_are_refused(self):
        for code in ('1x', '_x', 'x-y', 'x y', 'x.y', 'a' * 17, '\u00e4x'):
            with self.subTest(code=code):
                self.assertRefused('[languages]\n%s = Klingon\n' % code, '1 to 16 lower-case letters')

    def test_the_longest_code_is_16_characters(self):
        self.assertEqual(self.load('[languages]\n%s = Klingon\n' % ('a' * 16)), {'a' * 16: 'Klingon'})

    def test_a_built_in_code_with_another_name_is_refused(self):
        self.assertRefused('[languages]\nde = Deutsch2\n', "'de' is a built-in code (Deutsch)")

    def test_a_built_in_entry_written_again_is_accepted_and_adds_nothing(self):
        self.assertEqual(self.load('[languages]\nde = Deutsch\n'), {})

    def test_a_name_that_has_a_code_already_is_refused(self):
        self.assertRefused('[languages]\nxx = Deutsch\n', "has the code 'de' already")
        self.assertRefused('[languages]\nxx = Klingon\nyy = Klingon\n', "has the code 'xx' already")

    def test_a_name_that_cannot_be_a_folder_name_is_refused(self):
        for name in ('Klin:gon', 'Klin/gon', 'Klingon.', 'CON', 'Klin?gon'):
            with self.subTest(name=name):
                self.assertRefused('[languages]\nxx = %s\n' % name, 'folder name')

    def test_the_message_names_the_file_the_entry_and_the_reason(self):
        with self.assertRaises(g.ConfigError) as caught:
            self.load('[languages]\nde = Deutsch2\n')
        self.assertEqual(str(caught.exception), "config file x.cfg: [languages] de = Deutsch2: 'de' is a built-in code (Deutsch); choose another code")

    def test_the_built_in_table_passes_its_own_rules(self):
        self.assertEqual(g.load_extra_languages(parser_for('[languages]\n' + ''.join('%s = %s\n' % (code, name) for code, name in g.LANG_TABLE.items())), g.LANG_TABLE), {})


class UnknownLanguageNamesTests(unittest.TestCase):
    @staticmethod
    def game(title, *names, **more):
        return g.AttrDict(id=1, title=title, available_langs=g.AttrDict(**{title: list(names)}), **more)

    def test_only_names_that_the_table_lacks_are_found_with_their_games(self):
        found = g.unknown_language_names([self.game('alpha', 'English', 'Klingon'), self.game('beta', 'Klingon', 'Elvish', 'Deutsch')])
        self.assertEqual(found, {'Klingon': ['alpha', 'beta'], 'Elvish': ['beta']})

    def test_a_name_that_is_listed_twice_counts_its_game_once(self):
        self.assertEqual(g.unknown_language_names([self.game('alpha', 'Klingon', 'Klingon')]), {'Klingon': ['alpha']})

    def test_entries_without_available_langs_and_odd_values_are_ignored(self):
        games = [g.AttrDict(id=1, title='old'), g.AttrDict(id=2, title='none', available_langs=None), self.game('odd', None, 5, 'English')]
        games[2].available_langs['x'] = None
        self.assertEqual(g.unknown_language_names(games), {})

    def test_a_language_from_the_config_file_is_known(self):
        with mock.patch.dict(g.LANG_TABLE, {'xx': 'Klingon'}):
            self.assertEqual(g.unknown_language_names([self.game('alpha', 'Klingon')]), {})

    def test_every_name_of_the_pasted_real_lists_is_known(self):
        real = ['English', '\u010desk\u00fd', 'Deutsch', 'espa\u00f1ol', 'fran\u00e7ais', 'italiano', 'magyar', 'polski', '\u0440\u0443\u0441\u0441\u043a\u0438\u0439', '\u65e5\u672c\u8a9e',
                'Portugu\u00eas do Brasil', '\u4e2d\u6587(\u7b80\u4f53)', '\ud55c\uad6d\uc5b4', 'norsk', 'Dansk', 'nederlands', 'svenska', 'y\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430',
                'T\u00fcrk\u00e7e', '\u0627\u0644\u0639\u0631\u0628\u064a\u0629', '\u0e44\u0e17\u0e22', 'Espa\u00f1ol (AL)', 'portugu\u00eas', 'suomi', '\u4e2d\u6587', 'rom\u00e2n\u0103']
        self.assertEqual(g.unknown_language_names([self.game('alpha', *real)]), {})


class CaptureLog(unittest.TestCase):
    def setUp(self):
        import logging

        class Capture(logging.Handler):
            def __init__(self):
                logging.Handler.__init__(self)
                self.records = []

            def emit(self, record):
                self.records.append(record)
        self.handler = Capture()
        g.rootLogger.addHandler(self.handler)
        self.addCleanup(g.rootLogger.removeHandler, self.handler)
        g.flush_summarised()
        self.addCleanup(g.flush_summarised)

    def warnings(self):
        return [r.getMessage() for r in self.handler.records if r.levelname == 'WARNING']


class WarningTests(CaptureLog):
    def test_one_combined_warning_with_the_names_the_games_and_what_to_do(self):
        games = [UnknownLanguageNamesTests.game('alpha', 'Klingon'), UnknownLanguageNamesTests.game('beta', 'Klingon', 'Elvish'), UnknownLanguageNamesTests.game('gamma', 'English')]
        g.note_unknown_languages(games)
        g.flush_summarised()
        warnings = [m for m in self.warnings() if 'language name(s) that this program does not know' in m]
        self.assertEqual(len(warnings), 1, self.warnings())
        self.assertIn('GOG offers files in 2 language name(s)', warnings[0])
        self.assertIn('"Elvish" (in beta)', warnings[0])
        self.assertIn('"Klingon" (in 2 games, e.g. alpha)', warnings[0])
        self.assertIn('[languages]', warnings[0])
        self.assertIn('-lang', warnings[0])

    def test_nothing_unknown_gives_no_warning(self):
        g.note_unknown_languages([UnknownLanguageNamesTests.game('alpha', 'English', 'Deutsch')])
        g.flush_summarised()
        self.assertEqual(self.warnings(), [])

    def test_control_characters_in_a_name_are_shown_escaped(self):
        g.note_unknown_languages([UnknownLanguageNamesTests.game('alpha', 'Kling\x1bon')])
        g.flush_summarised()
        self.assertIn('Kling\\x1bon', self.warnings()[0])
        self.assertNotIn('\x1b', self.warnings()[0])


class UpdateWarningTests(trs.TempDirTests, CaptureLog):
    """The whole way: an update ends with the warning, also for a game that it did not fetch again, and not when the config file knows the language."""
    def setUp(self):
        trs.TempDirTests.setUp(self)
        CaptureLog.setUp(self)
        entry = g.AttrDict(id=1, title='alpha', folder_name='alpha', long_title='alpha', genre='', store_url='/g', rating=0, release_timestamp=0, changelog='', has_updates=False,
                           serial='', bg_url='', image_url='', downloads=[], galaxyDownloads=[], sharedDownloads=[], extras=[], available_langs=g.AttrDict(alpha=['English', 'Klingon']))
        g.save_manifest([entry])

    def update(self):
        with mock.patch.object(g, 'request', trs.games_api()), mock.patch.object(g, 'makeGOGSession', lambda: mock.MagicMock(token={})):
            g.cmd_update(['windows'], ['en'], True, True, True, [], [], False, 'both', 'resume', False, False, False, False, False, False, False)

    def test_the_warning_comes_at_the_end_of_the_update_and_is_not_a_failure(self):
        self.update()
        warnings = [m for m in self.warnings() if 'does not know' in m]
        self.assertEqual(len(warnings), 1, self.warnings())
        self.assertIn('"Klingon" (in alpha)', warnings[0])
        self.assertEqual(g.run_report.failures, [])

    def test_no_warning_when_the_language_is_in_the_table(self):
        with mock.patch.dict(g.LANG_TABLE, {'xx': 'Klingon'}):
            self.update()
        self.assertEqual([m for m in self.warnings() if 'does not know' in m], [])


class ConfigFileTests(test_config.ConfigTestCase):
    """The language table is built when the module is loaded, so these start a fresh python."""
    def run_python(self, code, config_text):
        self.write(config_text)
        return subprocess.run([sys.executable, '-c', test_config.IMPORTER + code, test_config.SCRIPT_DIR], capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, PYTHONIOENCODING='utf-8', **{test_config.ENV: self.path}), cwd=self.dir, stdin=subprocess.DEVNULL)

    def test_an_extra_language_can_be_chosen_with_lang_and_as_a_default(self):
        code = ("print(g.LANG_TABLE['xx'], 'xx' in g.VALID_LANG_TYPES, len(g.LANG_TABLE), g.EXTRA_LANGUAGES)\n"
                "print(g.process_argv(['gogrepo_delta.py', 'update', '-lang', 'xx', '-nolog']).lang)\n"
                "print(g.process_argv(['gogrepo_delta.py', 'update', '-nolog']).lang)\n")
        result = self.run_python(code, '[languages]\nxx = Klingon\n[common]\nlang = de,xx\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line for line in result.stdout.splitlines() if ' | ' not in line]         # process_argv also prints "defaults from the config file ..." on the console
        self.assertEqual(lines, ["Klingon True 33 {'xx': 'Klingon'}", "['xx']", "['de', 'xx']"])

    def test_without_the_section_nothing_changes(self):
        result = self.run_python("print(len(g.LANG_TABLE), g.EXTRA_LANGUAGES)", '[settings]\nhttp_timeout = 20\n')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '32 {}'))

    def test_a_language_that_cannot_be_used_stops_the_program_with_a_message(self):
        for text, words in (('[languages]\nde = Deutsch2\n', "'de' is a built-in code"), ('[languages]\nxx = Deutsch\n', "has the code 'de' already"),
                            ('[languages]\n1x = Klingon\n', '1 to 16 lower-case letters'), ('[languages]\nxx = Klin:gon\n', 'folder name')):
            with self.subTest(text=text):
                result = self.run_python("print('started')", text)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                for word in (self.path, '[languages]', words):
                    self.assertIn(word, result.stderr)

    def test_the_new_file_explains_the_section_and_it_adds_nothing(self):
        text = g.default_config_text(g.build_parser()[1])
        self.assertIn('[languages]', text)
        self.assertIn('\n; xx = Klingon\n', text)                  # the example line itself, commented out, not only the explanation
        self.assertEqual(g.load_extra_languages(parser_for(text), g.LANG_TABLE), {})
        self.assertEqual(g.load_settings(parser_for(text))[1], [])

    def test_the_section_is_not_reported_as_an_unknown_command(self):
        self.write('[languages]\nxx = Klingon\n[nonsense]\na = 1\n')
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            g.process_argv(['gogrepo_delta.py', 'list', '-nolog'])
            g.info('end of test')
        problems = [m for m in logs.output if 'is not a command' in m]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('[nonsense]', problems[0])
        self.assertIn('settings, languages, common', problems[0])


class SurveyTests(unittest.TestCase):
    def test_the_survey_names_the_languages_the_program_does_not_know(self):
        g.save_manifest([g.AttrDict(id=1, title='alpha', folder_name='alpha', long_title='alpha', genre='', store_url='/g', rating=0, release_timestamp=0, changelog='',
                                    has_updates=False, serial='', bg_url='', image_url='', downloads=[], galaxyDownloads=[], sharedDownloads=[], extras=[],
                                    available_langs=g.AttrDict(alpha=['English', 'Klingon']))])
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['gogrepo_survey_names.py']), contextlib.redirect_stdout(out):
            runpy.run_path(os.path.join(ROOT, 'gogrepo_survey_names.py'), run_name='__main__')
        text = out.getvalue()
        self.assertIn('language names GOG offers that this program does not know (files in them are never downloaded): 1', text)
        self.assertIn("'Klingon' - 1 game(s), e.g. alpha", text)


if __name__ == '__main__':
    unittest.main()
