"""Entry 72: a new token password that was typed twice and does not match (or is empty) is asked for again (up to 3 times, from a terminal)
instead of ending the run with a traceback. In the log of a real run this happened in the middle of a token refresh."""
import logging
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_token_password import Capture


def has_cryptography():
    try:
        import cryptography  # noqa: F401
        return True
    except ImportError:
        return False


class CreatePasswordTests(unittest.TestCase):
    def setUp(self):
        self.old = g._TOKEN_PASSWORD
        self.addCleanup(setattr, g, '_TOKEN_PASSWORD', self.old)
        g._TOKEN_PASSWORD = None
        self.log = Capture()
        g.rootLogger.addHandler(self.log)
        self.addCleanup(g.rootLogger.removeHandler, self.log)

    def create(self, answers, terminal=True):
        with mock.patch.object(g.getpass, 'getpass', side_effect=answers) as prompt, mock.patch.object(g, '_can_prompt_again', return_value=terminal):
            try:
                return g._token_password(create=True), prompt
            except Exception as e:
                return e, prompt

    def test_matching_passwords_are_accepted_at_once_and_remembered(self):
        result, prompt = self.create(['secret', 'secret'])
        self.assertEqual(('secret', 2), (result, prompt.call_count))
        self.assertEqual([], self.log.errors())
        with mock.patch.object(g.getpass, 'getpass', side_effect=AssertionError('must not ask again')):
            self.assertEqual('secret', g._token_password(create=True))

    def test_a_mismatch_is_asked_again_and_the_message_counts(self):
        result, prompt = self.create(['one', 'two', 'good', 'good'])
        self.assertEqual(('good', 4), (result, prompt.call_count))
        self.assertEqual(['The two passwords do not match. Please try again (1 of 3).'], self.log.errors())

    def test_the_third_attempt_may_be_the_one_that_works(self):
        result, prompt = self.create(['a', 'b', 'c', 'd', 'good', 'good'])
        self.assertEqual(('good', 6), (result, prompt.call_count))
        self.assertEqual(['The two passwords do not match. Please try again (1 of 3).',
                          'The two passwords do not match. Please try again (2 of 3).'], self.log.errors())

    def test_after_three_mismatches_it_stops_with_the_usual_error_and_keeps_nothing(self):
        result, prompt = self.create(['a', 'b', 'c', 'd', 'e', 'f', 'good', 'good'])
        self.assertIsInstance(result, ValueError)
        self.assertEqual('Token passwords do not match', str(result))
        self.assertEqual(6, prompt.call_count)
        self.assertEqual(2, len(self.log.errors()))
        self.assertIsNone(g._TOKEN_PASSWORD)

    def test_an_empty_password_is_asked_again_too(self):
        result, prompt = self.create(['', '', 'good', 'good'])
        self.assertEqual(('good', 4), (result, prompt.call_count))
        self.assertEqual(['The password must not be empty. Please try again (1 of 3).'], self.log.errors())

    def test_an_empty_password_typed_twice_is_empty_not_a_mismatch(self):
        result, _ = self.create(['', 'x', '', 'x', '', 'x'])
        self.assertIsInstance(result, ValueError)
        self.assertEqual('Token password must not be empty', str(result))

    def test_without_a_terminal_there_is_one_attempt_and_the_old_error(self):
        result, prompt = self.create(['one', 'two', 'good', 'good'], terminal=False)
        self.assertEqual(('Token passwords do not match', 2), (str(result), prompt.call_count))
        self.assertEqual([], self.log.errors())
        result, prompt = self.create(['', ''], terminal=False)
        self.assertEqual(('Token password must not be empty', 2), (str(result), prompt.call_count))

    def test_asking_for_an_existing_file_is_not_changed(self):
        with mock.patch.object(g.getpass, 'getpass', side_effect=['typed']) as prompt:
            self.assertEqual('typed', g._token_password())
        self.assertEqual(1, prompt.call_count)


@unittest.skipUnless(has_cryptography(), 'needs the cryptography package')
class SaveTests(unittest.TestCase):
    """The case of the real log: a plain token file is encrypted while the token is saved after a refresh."""
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp(prefix='tokcreate_')
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        self.old_password, self.old_mode = g._TOKEN_PASSWORD, os.environ.pop(g.TOKEN_MODE_ENV, None)
        self.addCleanup(setattr, g, '_TOKEN_PASSWORD', self.old_password)
        if self.old_mode is not None:
            self.addCleanup(os.environ.__setitem__, g.TOKEN_MODE_ENV, self.old_mode)
        g._TOKEN_PASSWORD = None
        with mock.patch.dict(g.SETTING_VALUES, {'token_mode': 'plain'}):
            g.save_token({'access_token': 'OLD', 'refresh_token': 'R', 'expiry': 1})
        g._TOKEN_PASSWORD = None

    def test_a_mismatch_while_saving_is_asked_again_and_the_file_is_then_encrypted(self):
        token = {'access_token': 'NEW', 'refresh_token': 'R2', 'expiry': 2}
        with mock.patch.dict(g.SETTING_VALUES, {'token_mode': 'encrypted'}), mock.patch.object(g, '_can_prompt_again', return_value=True), \
                mock.patch.object(g.getpass, 'getpass', side_effect=['one', 'two', 'good', 'good']):
            g.save_token(token)
        g._TOKEN_PASSWORD = None
        with mock.patch.object(g.getpass, 'getpass', return_value='good'):
            self.assertEqual('NEW', g.load_token()['access_token'])


@unittest.skipUnless(has_cryptography(), 'needs the cryptography package')
class LoginOverEncryptedFileTests(unittest.TestCase):
    """0.5.74: a login (a save that follows no read) over an encrypted token file: the file is replaced, so the password is typed twice."""
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp(prefix='tokover_')
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        self.old_password, self.old_mode = g._TOKEN_PASSWORD, os.environ.pop(g.TOKEN_MODE_ENV, None)
        self.addCleanup(setattr, g, '_TOKEN_PASSWORD', self.old_password)
        if self.old_mode is not None:
            self.addCleanup(os.environ.__setitem__, g.TOKEN_MODE_ENV, self.old_mode)
        g._TOKEN_PASSWORD = None
        with mock.patch.object(g.getpass, 'getpass', return_value='old'):
            g.save_token({'access_token': 'OLD', 'refresh_token': 'R', 'expiry': 1})
        g._TOKEN_PASSWORD = None

    def save(self, answers, terminal=True):
        with mock.patch.object(g.getpass, 'getpass', side_effect=answers) as prompt, mock.patch.object(g, '_can_prompt_again', return_value=terminal):
            g.save_token({'access_token': 'NEW', 'refresh_token': 'R2', 'expiry': 2})
        return prompt

    def load(self, password):
        g._TOKEN_PASSWORD = None
        with mock.patch.object(g.getpass, 'getpass', return_value=password):
            return g.load_token()

    def test_the_password_is_asked_twice_and_may_be_the_old_one(self):
        self.assertEqual(2, self.save(['old', 'old']).call_count)
        self.assertEqual('NEW', self.load('old')['access_token'])

    def test_or_a_new_one(self):
        self.save(['new', 'new'])
        self.assertEqual('NEW', self.load('new')['access_token'])

    def test_a_typo_is_caught_by_the_second_prompt_instead_of_setting_a_password_nobody_knows(self):
        prompt = self.save(['olf', 'old', 'old', 'old'])       # the first pair does not match: asked again
        self.assertEqual(4, prompt.call_count)
        self.assertEqual('NEW', self.load('old')['access_token'])

    def test_after_a_read_nothing_more_is_asked(self):
        # an update: the token is read (one prompt), then refreshed and saved (no prompt)
        with mock.patch.object(g.getpass, 'getpass', return_value='old') as prompt:
            g._TOKEN_PASSWORD = None
            g.load_token()
            g.save_token({'access_token': 'REFRESHED', 'refresh_token': 'R3', 'expiry': 3})
        self.assertEqual(1, prompt.call_count)
        self.assertEqual('REFRESHED', self.load('old')['access_token'])

    def test_without_a_terminal_a_mismatch_still_stops_and_the_old_file_stays(self):
        with open(g.TOKEN_FILENAME, 'rb') as r:
            before = r.read()
        with self.assertRaises(ValueError):
            self.save(['olf', 'old'], terminal=False)
        with open(g.TOKEN_FILENAME, 'rb') as r:
            self.assertEqual(before, r.read())

if __name__ == '__main__':
    unittest.main()
