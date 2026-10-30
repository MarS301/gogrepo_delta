"""Default operating system and language, and how -os / -lang / -skipos / -skiplang override them."""
import contextlib
import io
import unittest
import warnings
from types import SimpleNamespace
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g


class LocaleNameTests(unittest.TestCase):
    def test_posix_style_names(self):
        for name, expected in (('de_DE', 'de'), ('de_DE.UTF-8', 'de'), ('en_US.UTF-8', 'en'), ('fr_CA', 'fr'), ('sv_SE@euro', 'sv'),
                               ('es-ES', 'es'), ('pl_PL', 'pl'), ('it_IT', 'it'), ('ru_RU', 'ru'), ('tr_TR', 'tr'), ('ko_KR', 'ko')):
            self.assertEqual(g.gog_language_from_locale_name(name), expected, name)

    def test_codes_that_differ_between_iso_and_gog(self):
        for name, expected in (('ja_JP', 'jp'), ('cs_CZ', 'cz'), ('bg_BG', 'bl'), ('el_GR', 'gk'), ('sr_RS', 'sb'), ('nb_NO', 'no'), ('nn_NO', 'no')):
            self.assertEqual(g.gog_language_from_locale_name(name), expected, name)

    def test_chinese_and_portuguese_variants(self):
        for name, expected in (('zh_CN', 'cn'), ('zh_SG', 'cn'), ('zh_TW', 'zh'), ('zh_HK', 'zh'), ('zh_Hant_TW', 'zh'),
                               ('pt_BR', 'br'), ('pt_PT', 'pt'), ('pt', 'pt')):
            self.assertEqual(g.gog_language_from_locale_name(name), expected, name)

    def test_windows_style_names(self):
        for name, expected in (('German_Germany', 'de'), ('English_United States', 'en'), ('French_France', 'fr'), ('Czech_Czechia', 'cz'),
                               ('Japanese_Japan', 'jp'), ('Chinese (Simplified)_China', 'cn'), ('Chinese (Traditional)_Taiwan', 'zh'),
                               ('Portuguese_Brazil', 'br'), ('Portuguese_Portugal', 'pt'), ('Norwegian_Norway', 'no')):
            self.assertEqual(g.gog_language_from_locale_name(name), expected, name)

    def test_unusable_names_give_none(self):
        for name in (None, '', '   ', 'C', 'POSIX', 'C.UTF-8', 'xx_XX', 'Klingon_Qo', 12345, ['de_DE']):
            self.assertIsNone(g.gog_language_from_locale_name(name), repr(name))

    def test_every_result_is_a_language_gog_offers(self):
        for name in ('de_DE', 'ja_JP', 'zh_TW', 'pt_BR', 'English_United States', 'bg_BG'):
            self.assertIn(g.gog_language_from_locale_name(name), g.VALID_LANG_TYPES)


class DetectOsTests(unittest.TestCase):
    def test_known_systems(self):
        self.assertEqual(g.detect_os('Windows'), ('windows', 'detected'))
        self.assertEqual(g.detect_os('Linux'), ('linux', 'detected'))
        self.assertEqual(g.detect_os('Darwin'), ('mac', 'detected'))

    def test_unknown_or_empty_system_uses_the_fallback(self):
        for name in ('FreeBSD', 'Java', '', '   '):
            self.assertEqual(g.detect_os(name), ('windows', 'fallback'), name)

    def test_failing_detection_uses_the_fallback(self):
        with mock.patch.object(g.platform, 'system', side_effect=OSError('boom')):
            self.assertEqual(g.detect_os(), ('windows', 'fallback'))
        with mock.patch.object(g.platform, 'system', return_value=None):
            self.assertEqual(g.detect_os(), ('windows', 'fallback'))

    def test_uses_platform_system_by_default(self):
        with mock.patch.object(g.platform, 'system', return_value='Darwin'):
            self.assertEqual(g.detect_os(), ('mac', 'detected'))


class DetectLangTests(unittest.TestCase):
    def sources(self, getlocale=('de_DE', 'UTF-8'), windows=None, default=None):
        """Patch the three places a locale can come from."""
        return (mock.patch.object(g.locale, 'getlocale', return_value=getlocale) if not isinstance(getlocale, Exception) else mock.patch.object(g.locale, 'getlocale', side_effect=getlocale),
                mock.patch.object(g, '_windows_ui_locale_name', return_value=windows),
                mock.patch.object(g, '_default_locale_name', return_value=default))

    def detect(self, **kw):
        a, b, c = self.sources(**kw)
        with a, b, c:
            return g.detect_lang()

    def test_system_locale_is_used_first(self):
        self.assertEqual(self.detect(getlocale=('de_DE', 'UTF-8'), windows='fr_FR'), ('de', 'system locale'))

    def test_windows_display_language_when_the_system_locale_has_nothing(self):
        for empty in ((None, None), ('C', 'UTF-8'), ('xx_XX', 'UTF-8')):
            self.assertEqual(self.detect(getlocale=empty, windows='de_DE'), ('de', 'Windows display language'), empty)

    def test_default_locale_as_a_last_resort(self):
        self.assertEqual(self.detect(getlocale=(None, None), windows=None, default='fr_FR'), ('fr', 'default locale'))

    def test_a_source_that_raises_is_skipped(self):
        self.assertEqual(self.detect(getlocale=ValueError('boom'), windows='es_ES'), ('es', 'Windows display language'))
        with mock.patch.object(g.locale, 'getlocale', return_value=(None, None)), \
                mock.patch.object(g, '_windows_ui_locale_name', side_effect=AttributeError('no windll')), \
                mock.patch.object(g, '_default_locale_name', return_value='it_IT'):
            self.assertEqual(g.detect_lang(), ('it', 'default locale'))

    def test_falls_back_to_english_when_nothing_works(self):
        self.assertEqual(self.detect(getlocale=(None, None)), ('en', 'fallback'))
        self.assertEqual(self.detect(getlocale=ValueError('boom')), ('en', 'fallback'))
        self.assertEqual(self.detect(getlocale=('xx_XX', 'UTF-8'), windows='yy_YY', default='zz_ZZ'), ('en', 'fallback'))


class WindowsLocaleHelperTests(unittest.TestCase):
    def test_reads_the_display_language_through_the_windows_api(self):
        fake = SimpleNamespace(kernel32=SimpleNamespace(GetUserDefaultUILanguage=lambda: 1031))
        with mock.patch.object(g.platform, 'system', return_value='Windows'), mock.patch.object(g.ctypes, 'windll', fake, create=True):
            self.assertEqual(g._windows_ui_locale_name(), 'de_DE')

    def test_unknown_language_id(self):
        fake = SimpleNamespace(kernel32=SimpleNamespace(GetUserDefaultUILanguage=lambda: 0xFFFF))
        with mock.patch.object(g.platform, 'system', return_value='Windows'), mock.patch.object(g.ctypes, 'windll', fake, create=True):
            self.assertIsNone(g._windows_ui_locale_name())

    def test_not_used_on_other_systems(self):
        with mock.patch.object(g.platform, 'system', return_value='Linux'):
            self.assertIsNone(g._windows_ui_locale_name())

    def test_default_locale_helper_does_not_emit_deprecation_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            g._default_locale_name()


COMMANDS = {  # command line -> (function called by main, positions of os list and language list in its arguments)
    'update': (['update'], 'cmd_update', 0, 1),
    'download': (['download', 'somedir'], 'cmd_download', 5, 6),
    'import': (['import', 'src', 'dest'], 'cmd_import', 2, 3),
    'verify': (['verify', 'somedir'], 'cmd_verify', 9, 10),
    'backup': (['backup', 'src', 'dest'], 'cmd_backup', 3, 4),
}
ALL_BUT = lambda valid, skipped: [x for x in valid if x not in skipped]


class DefaultsPerCommandTests(unittest.TestCase):
    def call(self, command, flags, detected_lang='de'):
        argv, function, os_pos, lang_pos = COMMANDS[command]
        args = g.process_argv(['gogrepo_delta.py'] + argv + list(flags) + ['-nolog'])
        with mock.patch.object(g, function) as called, \
                mock.patch.object(g, 'detect_os', return_value=('mac', 'detected')), \
                mock.patch.object(g, 'detect_lang', return_value=(detected_lang, 'system locale')):
            g.main(args)
        return called

    def selection(self, command, *flags):
        _, _, os_pos, lang_pos = COMMANDS[command]
        positional = self.call(command, flags).call_args[0]
        return positional[os_pos], positional[lang_pos]

    def fallback(self, command, *flags, **kw):
        return self.call(command, flags, **kw).call_args[1]['lang_fallback']

    def test_nothing_given_uses_the_detected_os_and_language(self):
        for command in COMMANDS:
            self.assertEqual(self.selection(command), (['mac'], ['de']), command)

    def test_explicit_os_overrides_only_the_os(self):
        for command in COMMANDS:
            self.assertEqual(self.selection(command, '-os', 'linux', 'windows'), (['linux', 'windows'], ['de']), command)

    def test_explicit_lang_overrides_only_the_language(self):
        for command in COMMANDS:
            self.assertEqual(self.selection(command, '-lang', 'fr', 'pl'), (['mac'], ['fr', 'pl']), command)

    def test_explicit_os_and_lang(self):
        for command in COMMANDS:
            self.assertEqual(self.selection(command, '-os', 'linux', '-lang', 'en', 'de'), (['linux'], ['en', 'de']), command)

    def test_skipos_means_everything_except(self):
        for command in COMMANDS:
            os_list, lang_list = self.selection(command, '-skipos', 'linux')
            self.assertEqual(os_list, ['windows', 'mac'], command)
            self.assertEqual(lang_list, ['de'], command)

    def test_skiplang_means_everything_except(self):
        for command in COMMANDS:
            os_list, lang_list = self.selection(command, '-skiplang', 'en', 'de')
            self.assertEqual(lang_list, ALL_BUT(g.VALID_LANG_TYPES, ['en', 'de']), command)
            self.assertEqual(os_list, ['mac'], command)

    def test_skipos_and_skiplang_together(self):
        for command in COMMANDS:
            os_list, lang_list = self.selection(command, '-skipos', 'windows', 'mac', '-skiplang', 'en')
            self.assertEqual(os_list, ['linux'], command)
            self.assertEqual(lang_list, ALL_BUT(g.VALID_LANG_TYPES, ['en']), command)

    def test_os_and_skipos_cannot_be_combined_and_neither_can_lang_and_skiplang(self):
        # the parser rejects the contradiction, so there is no "which one wins" question
        for command in COMMANDS:
            argv = COMMANDS[command][0]
            for flags in (['-os', 'linux', '-skipos', 'linux'], ['-lang', 'en', '-skiplang', 'de']):
                captured = io.StringIO()
                with contextlib.redirect_stderr(captured), self.assertRaises(SystemExit):
                    g.process_argv(['gogrepo_delta.py'] + argv + flags + ['-nolog'])
                self.assertIn('not allowed with argument', captured.getvalue(), (command, flags))

    def test_english_fallback_comes_with_a_non_english_default_language(self):
        for command in COMMANDS:
            self.assertEqual(self.fallback(command), 'en', command)

    def test_no_fallback_when_the_default_language_is_english(self):
        for command in COMMANDS:
            self.assertIsNone(self.fallback(command, detected_lang='en'), command)

    def test_no_fallback_for_explicit_languages_or_skip(self):
        for command in COMMANDS:
            self.assertIsNone(self.fallback(command, '-lang', 'de'), command)
            self.assertIsNone(self.fallback(command, '-skiplang', 'en'), command)

    def test_fallback_still_applies_when_only_the_os_is_given(self):
        for command in COMMANDS:
            self.assertEqual(self.fallback(command, '-os', 'linux'), 'en', command)

    def test_the_fallback_is_announced(self):
        argv, function, _, _ = COMMANDS['download']
        args = g.process_argv(['gogrepo_delta.py'] + argv + ['-nolog'])
        with mock.patch.object(g, function), mock.patch.object(g, 'detect_os', return_value=('mac', 'detected')), \
                mock.patch.object(g, 'detect_lang', return_value=('de', 'system locale')), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.main(args)
        self.assertIn('with English for games that have no version in that language', '\n'.join(logs.output))

    def test_the_chosen_defaults_are_logged(self):
        argv, function, _, _ = COMMANDS['download']
        args = g.process_argv(['gogrepo_delta.py'] + argv + ['-nolog'])
        with mock.patch.object(g, function), mock.patch.object(g, 'detect_os', return_value=('mac', 'detected')), \
                mock.patch.object(g, 'detect_lang', return_value=('de', 'system locale')), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.main(args)
        text = '\n'.join(logs.output)
        self.assertIn('no -os given, using mac', text)
        self.assertIn('no -lang given, using de (from your system: system locale)', text)

    def test_nothing_is_logged_about_defaults_when_everything_is_given(self):
        argv, function, _, _ = COMMANDS['download']
        args = g.process_argv(['gogrepo_delta.py'] + argv + ['-os', 'linux', '-lang', 'en', '-nolog'])
        with mock.patch.object(g, function), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.rootLogger.info('(marker)')
            g.main(args)
        self.assertNotIn('no -os given', '\n'.join(logs.output))
        self.assertNotIn('no -lang given', '\n'.join(logs.output))

    def test_fallback_is_used_when_detection_fails(self):
        argv, function, os_pos, lang_pos = COMMANDS['download']
        args = g.process_argv(['gogrepo_delta.py'] + argv + ['-nolog'])
        with mock.patch.object(g, function) as called, mock.patch.object(g.platform, 'system', side_effect=OSError('boom')), \
                mock.patch.object(g.locale, 'getlocale', side_effect=ValueError('boom')), \
                mock.patch.object(g, '_windows_ui_locale_name', return_value=None), mock.patch.object(g, '_default_locale_name', return_value=None):
            g.main(args)
        self.assertEqual((called.call_args[0][os_pos], called.call_args[0][lang_pos]), (['windows'], ['en']))


if __name__ == '__main__':
    unittest.main()
