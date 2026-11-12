"""Entry 0.5.57: without the `cryptography` package the token is saved as plain text with a warning, but never over an existing
encrypted (or unreadable) token file and never when encryption was asked for on purpose; reading an encrypted file without the package
gives a message instead of a traceback."""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

TOKEN = {'access_token': 'abc', 'refresh_token': 'def', 'user_id': '42'}
ENCRYPTED_ENVELOPE = {'format': 'gogrepo-token', 'version': 1, 'encryption': 'encrypted', 'kdf': 'scrypt', 'kdf_n': 16384, 'kdf_r': 8,
                      'kdf_p': 1, 'salt': 'AAAAAAAAAAAAAAAAAAAAAA==', 'nonce': 'AAAAAAAAAAAAAAAA', 'ciphertext': 'AAAAAAAAAAAAAAAAAAAAAAAA'}
PLAIN_ENVELOPE = {'format': 'gogrepo-token', 'version': 1, 'encryption': 'plain', 'token': TOKEN}


def has_cryptography():
    try:
        g._token_crypto()
        return True
    except g.TokenModuleMissing:
        return False


class Base(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(g.TOKEN_MODE_ENV, None)
        self.path = os.path.join(self.dir, g.TOKEN_FILENAME)
        g._forget_token_password()
        g._TOKEN_PLAIN_FALLBACK_WARNED = False
        self.addCleanup(setattr, g, '_TOKEN_PLAIN_FALLBACK_WARNED', False)
        self.addCleanup(g._forget_token_password)

    def missing(self):
        """The "cryptography" package is not installed."""
        return mock.patch.object(g, '_token_crypto', side_effect=g.TokenModuleMissing('Encrypted token storage requires the "cryptography" package.'))

    def no_prompt(self):
        return mock.patch.object(g.getpass, 'getpass', side_effect=AssertionError('no password prompt expected'))

    def write(self, envelope):
        with open(self.path, 'w', encoding='utf-8') as w:
            json.dump(envelope, w)

    def digest(self):
        with open(self.path, 'rb') as r:
            return hashlib.sha256(r.read()).hexdigest()

    def read_json(self):
        with open(self.path, encoding='utf-8') as r:
            return json.load(r)

    def warnings_of(self, fn):
        """(result, [warning messages]) of calling fn."""
        records = []
        class Collect(logging.Handler):
            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    records.append(record.getMessage())
        handler = Collect()
        logger = logging.getLogger('gogrepoc')
        logger.addHandler(handler)
        try:
            return fn(), records
        finally:
            logger.removeHandler(handler)


class ExistingStateTests(Base):
    def test_no_file(self):
        self.assertEqual(g._existing_token_state(self.path), 'none')

    def test_plain_and_encrypted_files_are_recognised_without_decrypting(self):
        self.write(PLAIN_ENVELOPE)
        self.assertEqual(g._existing_token_state(self.path), 'plain')
        self.write(ENCRYPTED_ENVELOPE)
        self.assertEqual(g._existing_token_state(self.path), 'encrypted')

    def test_everything_else_is_unreadable(self):
        cases = {'garbage': 'not json at all {', 'empty': '', 'a list': '[1, 2]', 'wrong format': json.dumps({'format': 'other', 'version': 1, 'encryption': 'plain'}),
                 'future version': json.dumps(dict(PLAIN_ENVELOPE, version=2)), 'unknown mode': json.dumps(dict(PLAIN_ENVELOPE, encryption='rot13'))}
        for name, text in cases.items():
            with self.subTest(name):
                with open(self.path, 'w', encoding='utf-8') as w:
                    w.write(text)
                self.assertEqual(g._existing_token_state(self.path), 'unreadable')


class FallbackTests(Base):
    def test_a_new_token_is_saved_as_plain_text_with_one_warning_and_no_password_prompt(self):
        with self.missing(), self.no_prompt():
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
        self.assertEqual(self.read_json(), PLAIN_ENVELOPE)
        self.assertEqual(len(warnings), 1)
        self.assertIn('"cryptography" package is not installed', warnings[0])
        self.assertIn('NOT encrypted', warnings[0])
        self.assertIn('python -m pip install cryptography', warnings[0])
        self.assertIn(g.TOKEN_FILENAME, warnings[0])

    @unittest.skipIf(os.name == 'nt', 'POSIX permissions')
    def test_the_plain_file_is_private_like_the_encrypted_one(self):
        with self.missing(), self.no_prompt():
            g.save_token(TOKEN)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_the_warning_comes_once_per_run_not_for_every_save(self):
        with self.missing(), self.no_prompt():
            _, first = self.warnings_of(lambda: g.save_token(TOKEN))
            _, second = self.warnings_of(lambda: g.save_token(dict(TOKEN, access_token='new')))
        self.assertEqual((len(first), len(second)), (1, 0))
        self.assertEqual(self.read_json()['token']['access_token'], 'new')

    def test_an_existing_plain_file_is_refreshed_as_plain_text(self):
        self.write(PLAIN_ENVELOPE)
        with self.missing(), self.no_prompt():
            _, warnings = self.warnings_of(lambda: g.save_token(dict(TOKEN, access_token='refreshed')))
        self.assertEqual(self.read_json()['token']['access_token'], 'refreshed')
        self.assertEqual(self.read_json()['encryption'], 'plain')
        self.assertEqual(len(warnings), 1)

    def test_an_existing_encrypted_file_is_never_replaced(self):
        self.write(ENCRYPTED_ENVELOPE)
        before = self.digest()
        with self.missing(), self.no_prompt():
            with self.assertRaises(g.TokenModuleMissing) as raised:
                g.save_token(TOKEN)
        self.assertIn('is encrypted', str(raised.exception))
        self.assertIn('not replaced by a plain-text file', str(raised.exception))
        self.assertIn('python -m pip install cryptography', str(raised.exception))
        self.assertEqual(self.digest(), before)

    def test_an_unreadable_file_is_never_replaced_either(self):
        with open(self.path, 'w', encoding='utf-8') as w:
            w.write('damaged {')
        before = self.digest()
        with self.missing(), self.no_prompt():
            with self.assertRaises(g.TokenModuleMissing) as raised:
                g.save_token(TOKEN)
        self.assertIn('cannot be read', str(raised.exception))
        self.assertIn('delete', str(raised.exception))
        self.assertEqual(self.digest(), before)

    def test_encryption_asked_for_on_purpose_never_falls_back(self):
        os.environ[g.TOKEN_MODE_ENV] = 'encrypted'
        with self.missing(), self.no_prompt():
            with self.assertRaises(g.TokenModuleMissing) as raised:
                g.save_token(TOKEN)
        self.assertIn('GOGREPO_TOKEN_MODE=encrypted asks for an encrypted token file', str(raised.exception))
        self.assertIn('GOGREPO_TOKEN_MODE=plain', str(raised.exception))
        self.assertFalse(os.path.exists(self.path))

    def test_the_plain_mode_is_unchanged_and_needs_no_warning(self):
        os.environ[g.TOKEN_MODE_ENV] = 'plain'
        with self.missing(), self.no_prompt():
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
        self.assertEqual(self.read_json(), PLAIN_ENVELOPE)
        self.assertEqual(warnings, [])

    def test_a_wrong_mode_value_is_still_an_error(self):
        os.environ[g.TOKEN_MODE_ENV] = 'rot13'
        with self.missing():
            with self.assertRaises(ValueError):
                g.save_token(TOKEN)

    def test_the_legacy_token_is_migrated_to_plain_text_and_the_old_file_is_left_alone(self):
        legacy = os.path.join(self.dir, g.LEGACY_TOKEN_FILENAME)
        with open(legacy, 'w', encoding='utf-8') as w:
            w.write(repr(TOKEN))
        with open(legacy, 'rb') as r:
            before = hashlib.sha256(r.read()).hexdigest()
        with self.missing(), self.no_prompt():
            loaded = g.load_token()
        self.assertEqual(loaded, TOKEN)
        self.assertEqual(self.read_json(), PLAIN_ENVELOPE)
        with open(legacy, 'rb') as r:
            self.assertEqual(hashlib.sha256(r.read()).hexdigest(), before)


class ReadingTests(Base):
    def test_a_plain_file_is_read_without_the_package(self):
        self.write(PLAIN_ENVELOPE)
        with self.missing(), self.no_prompt():
            self.assertEqual(g.load_token(), TOKEN)

    def test_an_encrypted_file_without_the_package_gives_a_message_that_names_the_file(self):
        self.write(ENCRYPTED_ENVELOPE)
        with self.missing(), self.no_prompt():
            with self.assertRaises(g.TokenModuleMissing) as raised:
                g.load_token()
        self.assertIn(g.TOKEN_FILENAME + ' is encrypted', str(raised.exception))
        self.assertIn('python -m pip install cryptography', str(raised.exception))

    def test_the_missing_package_is_still_a_runtime_error_as_before(self):
        self.assertTrue(issubclass(g.TokenModuleMissing, RuntimeError))

    def test_the_real_import_failure_is_turned_into_the_same_error(self):
        with mock.patch.dict(sys.modules, {'cryptography.hazmat.primitives.ciphers.aead': None}):
            with self.assertRaises(g.TokenModuleMissing) as raised:
                g._token_crypto()
        self.assertIn('python -m pip install cryptography', str(raised.exception))


@unittest.skipUnless(has_cryptography(), 'the cryptography package is needed for this test')
class WithThePackageTests(Base):
    def test_a_new_token_is_still_encrypted_and_asks_for_a_new_password_twice(self):
        with mock.patch.object(g.getpass, 'getpass', side_effect=['pw', 'pw']) as prompt:
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
        self.assertEqual(self.read_json()['encryption'], 'encrypted')
        self.assertEqual([c[0][0] for c in prompt.call_args_list], ['Create password for gog-token.json: ', 'Confirm token password: '])
        self.assertEqual(warnings, [])
        self.assertEqual(g.load_token(), TOKEN)

    def test_a_plain_file_is_encrypted_with_a_new_password_that_is_confirmed(self):
        # e.g. the file was written without the package, which has been installed since (before 0.5.57 it asked once, as for an old password)
        self.write(PLAIN_ENVELOPE)
        with mock.patch.object(g.getpass, 'getpass', side_effect=['pw', 'pw']) as prompt:
            g.save_token(dict(TOKEN, access_token='again'))
        self.assertEqual(prompt.call_count, 2)
        self.assertEqual(self.read_json()['encryption'], 'encrypted')
        self.assertEqual(g.load_token()['access_token'], 'again')

    def test_a_mismatching_confirmation_leaves_the_plain_file_alone(self):
        self.write(PLAIN_ENVELOPE)
        before = self.digest()
        with mock.patch.object(g.getpass, 'getpass', side_effect=['pw', 'other']):
            with self.assertRaises(ValueError):
                g.save_token(TOKEN)
        self.assertEqual(self.digest(), before)

    def test_an_existing_encrypted_file_keeps_its_one_prompt(self):
        with mock.patch.object(g.getpass, 'getpass', side_effect=['pw', 'pw']):
            g.save_token(TOKEN)
        g._forget_token_password()
        with mock.patch.object(g.getpass, 'getpass', side_effect=['pw']) as prompt:
            g.save_token(dict(TOKEN, access_token='second'))
        self.assertEqual(prompt.call_count, 1)

    def test_with_the_package_there_is_no_warning_and_no_fallback_even_for_the_plain_default(self):
        with mock.patch.object(g.getpass, 'getpass', side_effect=['pw', 'pw']):
            _, warnings = self.warnings_of(lambda: g.save_token(TOKEN))
        self.assertEqual(warnings, [])
        self.assertEqual(self.read_json()['encryption'], 'encrypted')


RUNNER = r'''
import runpy, sys, types
for name in ('html5lib', 'psutil'):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = types.ModuleType(name)
sys.modules['cryptography.hazmat.primitives.ciphers.aead'] = None      # "not installed"
script = sys.argv[1]
sys.argv = [script] + sys.argv[2:]
runpy.run_path(script, run_name='__main__')
'''


class TopLevelTests(Base):
    def run_script(self, *argv):
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gogrepo_delta.py')
        env = dict(os.environ, GOGREPO_DELTA_CONFIG=os.path.join(self.dir, 'test.cfg'))
        done = subprocess.run([sys.executable, '-c', RUNNER, script] + list(argv) + ['-nolog'], cwd=self.dir, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr

    def test_an_encrypted_token_without_the_package_ends_with_a_message_and_no_traceback(self):
        self.write(ENCRYPTED_ENVELOPE)
        before = self.digest()
        status, output = self.run_script('update')
        self.assertEqual(status, 1, output)
        self.assertNotIn('Traceback', output)
        self.assertIn('is encrypted, but the "cryptography" package that opens it is not installed', output)
        self.assertIn('python -m pip install cryptography', output)
        self.assertEqual(self.digest(), before)


if __name__ == '__main__':
    unittest.main()
