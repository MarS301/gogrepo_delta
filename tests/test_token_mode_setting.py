"""Entry 70: token_mode is a setting of gogrepo_delta.cfg ([settings], encrypted or plain, default encrypted). The environment variable
GOGREPO_TOKEN_MODE still works and, when it is set, wins over the file."""
import os
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_token_fallback import Base, TOKEN, PLAIN_ENVELOPE, has_cryptography

PATH = 'gogrepo_delta.cfg'


def settings_of(text):
    parser = g.make_config_parser()
    parser.read_string(text)
    return g.load_settings(parser, PATH)


class SettingTests(unittest.TestCase):
    def test_the_default_is_encrypted_with_and_without_a_file(self):
        self.assertEqual('encrypted', settings_of('')[0]['token_mode'])
        self.assertEqual('encrypted', settings_of('[settings]\nhttp_timeout = 30\n')[0]['token_mode'])      # an old file without the line
        self.assertEqual('encrypted', g.load_settings(None)[0]['token_mode'])

    def test_the_file_can_choose_either_word_in_any_case(self):
        for text, expected in (('plain', 'plain'), ('PLAIN', 'plain'), (' Encrypted ', 'encrypted'), ('encrypted', 'encrypted')):
            with self.subTest(text=text):
                values, problems = settings_of('[settings]\ntoken_mode = %s\n' % text)
                self.assertEqual((expected, []), (values['token_mode'], problems))

    def test_an_empty_value_means_the_default(self):
        self.assertEqual('encrypted', settings_of('[settings]\ntoken_mode =\n')[0]['token_mode'])

    def test_any_other_word_stops_the_program_with_a_clear_message(self):
        for text in ('plan', 'none', 'true', 'encrypt'):
            with self.subTest(text=text):
                with self.assertRaises(g.ConfigError) as raised:
                    settings_of('[settings]\ntoken_mode = %s\n' % text)
                message = str(raised.exception)
                self.assertIn('[settings] token_mode = %s' % text, message)
                self.assertIn('encrypted, plain', message)

    def test_the_new_config_file_has_it_with_its_default_and_an_explanation(self):
        text = g.default_config_text(g.build_parser()[1])
        self.assertIn('\ntoken_mode = encrypted\n', text)
        self.assertIn('gog-token.json', text)
        self.assertIn('GOGREPO_TOKEN_MODE', text)
        self.assertEqual('encrypted', settings_of(text)[0]['token_mode'])      # and the generated file reads back without a problem
        self.assertEqual([], settings_of(text)[1])


class ModeTests(Base):
    def cfg(self, mode):
        patch = mock.patch.dict(g.SETTING_VALUES, {'token_mode': mode})
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_setting_is_used_when_the_variable_is_not_set(self):
        self.cfg('plain')
        self.assertEqual('plain', g._token_mode())
        self.cfg('encrypted')
        self.assertEqual('encrypted', g._token_mode())

    def test_the_variable_wins_over_the_file_in_both_directions(self):
        self.cfg('plain')
        os.environ[g.TOKEN_MODE_ENV] = 'encrypted'
        self.assertEqual('encrypted', g._token_mode())
        self.cfg('encrypted')
        os.environ[g.TOKEN_MODE_ENV] = ' PLAIN '
        self.assertEqual('plain', g._token_mode())

    def test_a_bad_variable_is_still_refused_whatever_the_file_says(self):
        self.cfg('plain')
        for value in ('rot13', ''):
            with self.subTest(value=value):
                os.environ[g.TOKEN_MODE_ENV] = value
                with self.assertRaises(ValueError):
                    g._token_mode()

    def test_plain_in_the_file_saves_readable_text_without_password_or_warning(self):
        self.cfg('plain')
        with self.no_prompt():
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
        self.assertEqual(PLAIN_ENVELOPE, self.read_json())
        self.assertEqual([], warnings)

    def test_plain_in_the_file_needs_no_cryptography_package(self):
        self.cfg('plain')
        with self.missing(), self.no_prompt():
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
        self.assertEqual(PLAIN_ENVELOPE, self.read_json())
        self.assertEqual([], warnings)

    def test_encrypted_in_the_file_without_the_package_still_falls_back_with_a_warning_that_names_the_setting(self):
        # unchanged behaviour: only the environment variable makes encryption mandatory
        self.cfg('encrypted')
        with self.missing(), self.no_prompt():
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
        self.assertEqual(PLAIN_ENVELOPE, self.read_json())
        self.assertEqual(1, len(warnings))
        self.assertIn('NOT encrypted', warnings[0])
        self.assertIn('token_mode = plain', warnings[0])

    def test_encrypted_in_the_file_never_replaces_an_existing_encrypted_file_by_plain_text(self):
        from test_token_fallback import ENCRYPTED_ENVELOPE
        self.cfg('encrypted')
        self.write(ENCRYPTED_ENVELOPE)
        before = self.digest()
        with self.missing(), self.no_prompt(), self.assertRaises(g.TokenModuleMissing):
            g.save_token(TOKEN)
        self.assertEqual(before, self.digest())

    def test_the_variable_set_to_encrypted_still_stops_without_the_package_and_names_both_ways_out(self):
        self.cfg('plain')
        os.environ[g.TOKEN_MODE_ENV] = 'encrypted'
        with self.missing(), self.no_prompt(), self.assertRaises(g.TokenModuleMissing) as raised:
            g.save_token(TOKEN)
        self.assertIn('GOGREPO_TOKEN_MODE=plain', str(raised.exception))
        self.assertIn('token_mode = plain', str(raised.exception))
        self.assertFalse(os.path.exists(self.path))

    @unittest.skipUnless(has_cryptography(), 'needs the cryptography package')
    def test_plain_in_the_file_is_read_back_and_an_encrypted_mode_file_is_still_readable_afterwards(self):
        self.cfg('plain')
        g.save_token(TOKEN)
        self.assertEqual(TOKEN, g.load_token())
        self.cfg('encrypted')            # switching the setting does not touch the file, and the file is read as it is
        self.assertEqual(TOKEN, g.load_token())


if __name__ == '__main__':
    unittest.main()
