"""Entry 73 (token review): a token file that is damaged, edited or from another program ends with one clear message (no traceback), a file
cannot ask for unlimited memory or time, the key derivation can be made stronger, and a plain save over an encrypted file is said aloud."""
import base64
import copy
import json
import types
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_token_fallback import Base, TOKEN, ENCRYPTED_ENVELOPE, PLAIN_ENVELOPE, has_cryptography


def b64(data):
    return base64.b64encode(data).decode('ascii')


class FileValidationTests(Base):
    """A reader that needs the cryptography package is only reached with it, so these run with the package or are skipped."""
    def setUp(self):
        super().setUp()
        if not has_cryptography():
            self.skipTest('needs the cryptography package')

    def load_error(self, envelope):
        self.write(envelope)
        with self.no_prompt(), self.assertRaises(g.TokenFileError) as raised:      # and no password is asked for a file that cannot be used
            g.load_token()
        self.assertIsInstance(raised.exception, ValueError)
        self.assertIn(g.TOKEN_FILENAME, str(raised.exception))
        return str(raised.exception)

    def changed(self, **changes):
        envelope = copy.deepcopy(ENCRYPTED_ENVELOPE)
        for key, value in changes.items():
            if value is KeyError:
                del envelope[key]
            else:
                envelope[key] = value
        return envelope

    def test_kdf_values_outside_the_limits_are_refused(self):
        for key, value in (('kdf_n', 2 ** 13), ('kdf_n', 2 ** 21), ('kdf_n', 16385), ('kdf_n', 0), ('kdf_n', -16384), ('kdf_n', 'sixteen'),
                           ('kdf_n', 16384.0), ('kdf_n', None), ('kdf_n', True), ('kdf_n', KeyError),
                           ('kdf_r', 7), ('kdf_r', 33), ('kdf_r', '8'), ('kdf_r', KeyError),
                           ('kdf_p', 0), ('kdf_p', 17), ('kdf_p', True), ('kdf_r', True), ('kdf_p', 10 ** 9), ('kdf_p', 1.5), ('kdf_p', KeyError)):
            with self.subTest(key=key, value=value):
                self.assertIn(key, self.load_error(self.changed(**{key: value})))

    def test_a_file_cannot_ask_for_too_much_memory(self):
        message = self.load_error(self.changed(kdf_n=2 ** 19))               # 128 * N * r = 512 MiB
        self.assertIn('256 MiB', message)
        self.load_error(self.changed(kdf_n=2 ** 20, kdf_r=32))                # 4 GiB

    def test_the_largest_accepted_derivation_passes_the_check_without_being_run(self):
        self.assertEqual((2 ** 18, 8, 16), g._token_kdf_parameters(self.changed(kdf_n=2 ** 18, kdf_r=8, kdf_p=16), 'x'))
        self.assertEqual((16384, 8, 1), g._token_kdf_parameters(ENCRYPTED_ENVELOPE, 'x'))

    def test_damaged_or_missing_fields_are_refused(self):
        for key, value in (('salt', KeyError), ('salt', '!!!not base64!!!'), ('salt', 'AAAAAAAAAAAAAAAAAAAAAA==!!!!'), ('salt', b64(b'short')), ('salt', b64(b'')), ('salt', 5), ('salt', None),
                           ('nonce', KeyError), ('nonce', b64(b'x' * 16)), ('nonce', '%%%'),
                           ('ciphertext', KeyError), ('ciphertext', ''), ('ciphertext', 7), ('ciphertext', 'a')):
            with self.subTest(key=key, value=value):
                self.assertIn(key, self.load_error(self.changed(**{key: value})))

    def test_a_key_derivation_other_than_scrypt_is_refused(self):
        self.assertIn('key derivation', self.load_error(self.changed(kdf='pbkdf2')))

    def test_an_unknown_mode_version_or_format_is_refused(self):
        self.load_error(self.changed(encryption='rot13'))
        self.load_error(self.changed(version=2))
        self.load_error(self.changed(format='something-else'))

    def test_a_file_that_is_not_a_token_file_is_refused(self):
        for text in (b'{broken', b'', b'[1, 2, 3]', b'"text"', b'\xff\xfe\x00binary'):
            with self.subTest(text=text):
                with open(self.path, 'wb') as w:
                    w.write(text)
                with self.no_prompt(), self.assertRaises(g.TokenFileError) as raised:
                    g.load_token()
                self.assertIn(g.TOKEN_FILENAME, str(raised.exception))

    def test_a_plain_file_whose_token_is_not_an_object_is_refused(self):
        self.write(dict(PLAIN_ENVELOPE, token=['a']))
        with self.assertRaises(g.TokenFileError):
            g.load_token()

    def test_a_good_password_over_content_that_is_not_a_token_is_refused(self):
        salt, nonce = b'\x01' * 16, b'\x02' * 12
        key = g._token_key('pw', salt)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        for content in (b'not json at all', b'[1, 2]'):
            with self.subTest(content=content):
                envelope = self.changed(salt=b64(salt), nonce=b64(nonce), ciphertext=b64(AESGCM(key).encrypt(nonce, content, b'gogrepo-token')))
                self.write(envelope)
                g._forget_token_password()
                with mock.patch.object(g.getpass, 'getpass', return_value='pw'), self.assertRaises(g.TokenFileError):
                    g.load_token()

    def test_a_wrong_password_is_still_a_password_error(self):
        self.write(ENCRYPTED_ENVELOPE)
        with mock.patch.object(g.getpass, 'getpass', return_value='whatever'), self.assertRaises(g.TokenPasswordError):
            g.load_token()

    def test_a_stronger_derivation_can_be_saved_and_read_back(self):
        # Python's default memory limit (32 MiB) refuses N = 2**15 with r = 8: before 0.5.73 raising the setting would have made saving fail
        with mock.patch.object(g, '_TOKEN_SCRYPT_N', 2 ** 15):
            with mock.patch.object(g.getpass, 'getpass', return_value='pw'):
                g.save_token(TOKEN)
            self.assertEqual(2 ** 15, self.read_json()['kdf_n'])
        g._forget_token_password()
        with mock.patch.object(g.getpass, 'getpass', return_value='pw'):
            self.assertEqual(TOKEN, g.load_token())

    def test_the_key_depends_on_the_parameters(self):
        salt = b'\x03' * 16
        self.assertEqual(32, len(g._token_key('pw', salt, 2 ** 15, 8, 1)))
        self.assertNotEqual(g._token_key('pw', salt, 2 ** 14, 8, 1), g._token_key('pw', salt, 2 ** 15, 8, 1))


class PlainOverEncryptedTests(Base):
    def setUp(self):
        super().setUp()
        patch = mock.patch.dict(g.SETTING_VALUES, {'token_mode': 'plain'})
        patch.start()
        self.addCleanup(patch.stop)

    def test_saving_plain_over_an_encrypted_file_is_warned_about_and_done(self):
        self.write(ENCRYPTED_ENVELOPE)
        with self.no_prompt():
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
        self.assertEqual(PLAIN_ENVELOPE, self.read_json())
        self.assertEqual(1, len(warnings))
        self.assertIn('was encrypted and is now saved as readable plain text', warnings[0])
        self.assertIn('token_mode', warnings[0])

    def test_no_warning_for_a_new_file_or_a_plain_one(self):
        with self.no_prompt():
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
            self.assertEqual([], warnings)
            _, warnings = self.warnings_of(lambda: g.save_token(dict(TOKEN, access_token='x')))
            self.assertEqual([], warnings)


class TopLevelTests(unittest.TestCase):
    """The real `if __name__ == "__main__":` block of the script with main() failing."""
    def run_block(self, error):
        with open(g.__file__, encoding='utf-8') as r:
            source = r.read()
        block = source[source.index('if __name__ == "__main__":'):].replace('__name__ == "__main__"', 'True', 1)
        wake = types.SimpleNamespace(take_wakelock=lambda: None, release_wakelock=lambda: None)

        def failing_main(argv):
            raise error
        namespace = dict(g.__dict__, main=failing_main, Wakelock=lambda: wake, ensure_config_file=lambda: None, process_argv=lambda argv: argv)
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            try:
                exec(compile(block, g.__file__, 'exec'), namespace)
                status = 0
            except SystemExit as e:
                status = e.code
        return status, '\n'.join(logs.output)

    def test_a_damaged_token_file_ends_the_run_with_a_message_and_no_traceback(self):
        status, log = self.run_block(g.TokenFileError('gog-token.json is damaged: it is not a token file'))
        self.assertEqual(1, status)
        self.assertIn('gog-token.json is damaged', log)
        self.assertIn('Delete %s and run the login command again' % g.TOKEN_FILENAME, log)
        self.assertNotIn('Traceback', log)


class SourceTests(unittest.TestCase):
    def test_base64_is_imported_normally(self):
        with open(g.__file__, encoding='utf-8') as r:
            source = r.read()
        self.assertNotIn("__import__('base64')", source)
        self.assertIn('\nimport base64\n', source)


if __name__ == '__main__':
    unittest.main()
