"""`selfupdate` (entry 0.5.53): the check for a newer release. It only looks; nothing is downloaded or installed. GitHub is faked here,
no test talks to the network."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import requests

import _bootstrap  # noqa: F401
import gogrepo_delta as g

URL = g.RELEASES_PAGE_URL + '/tag/v0.5.60'


class FakeResponse(object):
    def __init__(self, status=200, body=b'', chunks=None, fail_after=None):
        self.status_code = status
        self.chunks = chunks if chunks is not None else [body]
        self.fail_after = fail_after
        self.closed = False

    def iter_content(self, chunk_size=1):
        for number, chunk in enumerate(self.chunks):
            if self.fail_after is not None and number == self.fail_after:
                raise requests.exceptions.ChunkedEncodingError('cut')
            yield chunk

    def close(self):
        self.closed = True


class FakeSession(object):
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def release(**changes):
    data = {'tag_name': 'v0.5.60', 'name': 'Version 0.5.60', 'html_url': URL, 'draft': False, 'prerelease': False}
    data.update(changes)
    return FakeResponse(200, json.dumps(data).encode('utf-8'))


def latest_from(response=None, error=None):
    session = FakeSession(response, error)
    with mock.patch.object(g, 'makeGitHubSession', lambda: session):
        try:
            return g.fetch_latest_release(), session
        except g.SelfUpdateError as e:
            return e, session


class VersionTextTests(unittest.TestCase):
    def test_release_tags_are_read_as_numbers(self):
        self.assertEqual(g.parse_release_version('v0.5.53'), (0, 5, 53))
        self.assertEqual(g.parse_release_version('0.5.53'), (0, 5, 53))
        self.assertEqual(g.parse_release_version(' v1.12.3\n'), (1, 12, 3))

    def test_anything_else_is_rejected(self):
        for bad in ('', 'latest', 'v0.5', '0.5.53-beta', 'v1.2.3.4', 'v0.5.53; rm -rf', '\x1b[31mv0.5.53', 'v0.5.x', None, 5, ['0.5.1']):
            self.assertIsNone(g.parse_release_version(bad), repr(bad))

    def test_versions_compare_as_numbers_not_as_text(self):
        self.assertGreater(g.parse_release_version('v0.5.10'), g.parse_release_version('v0.5.9'))
        self.assertGreater(g.parse_release_version('v0.10.0'), g.parse_release_version('v0.9.99'))

    def test_text_from_the_internet_loses_its_control_characters(self):
        shown = g.printable_text('Release \x1b[2J\x1b[31mred\r\nnext\tline\x07')
        self.assertNotIn('\x1b', shown)
        self.assertNotIn('\n', shown)
        self.assertTrue(shown.isprintable())
        self.assertIn('Release', shown)

    def test_long_text_is_cut_and_spaces_collapse(self):
        self.assertEqual(g.printable_text('a   b    c'), 'a b c')
        cut = g.printable_text('x' * 500, 40)
        self.assertEqual(len(cut), 40)
        self.assertTrue(cut.endswith('...'))


class FetchTests(unittest.TestCase):
    def test_a_good_answer_gives_version_title_and_address(self):
        latest, session = latest_from(release())
        self.assertEqual(latest, {'version': (0, 5, 60), 'tag': 'v0.5.60', 'title': 'Version 0.5.60', 'url': URL})

    def test_the_request_is_plain_and_does_not_follow_redirects(self):
        _, session = latest_from(release())
        url, kwargs = session.calls[0]
        self.assertEqual(url, g.REPO_HOME_URL + '/releases/latest')
        self.assertIs(kwargs['allow_redirects'], False)
        self.assertEqual(kwargs['timeout'], g.HTTP_TIMEOUT)
        self.assertTrue(kwargs['stream'])
        self.assertEqual(set(kwargs), {'allow_redirects', 'timeout', 'stream'})        # no headers, no data, no credentials added here

    def test_the_github_session_carries_no_credentials(self):
        headers = {k.lower() for k in g.makeGitHubSession().headers}
        self.assertNotIn('authorization', headers)
        self.assertNotIn('cookie', headers)

    def test_an_address_outside_the_release_pages_is_replaced_by_the_general_one(self):
        for url in ('https://evil.example/releases/tag/v1', 'http://github.com/MarS301/gogrepo_delta/releases/tag/v1', None, 5,
                    'https://github.com/MarS301/gogrepo_delta/releasesX', 'https://github.com/MarS301/gogrepo_delta/releases'):
            latest, _ = latest_from(release(html_url=url))
            self.assertEqual(latest['url'], g.RELEASES_PAGE_URL, url)

    def test_the_title_is_made_printable(self):
        latest, _ = latest_from(release(name='Big \x1b[31mnews\n' + 'y' * 300))
        self.assertTrue(latest['title'].isprintable())
        self.assertLessEqual(len(latest['title']), 80)

    def test_a_missing_title_is_fine(self):
        latest, _ = latest_from(release(name=None))
        self.assertEqual(latest['title'], '')

    def test_every_failure_is_a_selfupdate_error_with_words_and_the_response_is_closed(self):
        cases = [('redirect', FakeResponse(301), 'redirected'),
                 ('not found', FakeResponse(404), 'no published release'),
                 ('limit 403', FakeResponse(403), 'limit'),
                 ('limit 429', FakeResponse(429), 'limit'),
                 ('server', FakeResponse(500), 'HTTP 500'),
                 ('not json', FakeResponse(200, b'<html>'), 'could not be understood'),
                 ('not an object', FakeResponse(200, b'[1, 2]'), 'could not be understood'),
                 ('bad bytes', FakeResponse(200, b'\xff\xfe\x00'), 'could not be understood'),
                 ('draft', release(draft=True), 'draft or pre-release'),
                 ('prerelease', release(prerelease=True), 'draft or pre-release'),
                 ('bad tag', release(tag_name='nightly'), 'not a version number'),
                 ('no tag', release(tag_name=None), 'not a version number'),
                 ('too big', FakeResponse(200, chunks=[b'x' * 600000, b'x' * 600000]), 'unexpectedly large'),
                 ('cut off', FakeResponse(200, chunks=[b'{', b'}'], fail_after=1), 'interrupted')]
        for name, response, words in cases:
            error, _ = latest_from(response)
            self.assertIsInstance(error, g.SelfUpdateError, name)
            self.assertIn(words, str(error), name)
            self.assertTrue(response.closed, name)

    def test_the_tag_in_the_message_is_printable_too(self):
        error, _ = latest_from(release(tag_name='\x1b[2Jevil'))
        self.assertNotIn('\x1b', str(error))

    def test_network_problems_are_reported_without_a_traceback(self):
        for exc in (requests.ConnectionError('boom http://x'), requests.Timeout('slow'), requests.exceptions.SSLError('cert')):
            error, _ = latest_from(error=exc)
            self.assertIsInstance(error, g.SelfUpdateError)
            self.assertIn('could not reach GitHub', str(error))
            self.assertIn(type(exc).__name__, str(error))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset('selfupdate')

    def run_check(self, response=None, error=None, version=None):
        session = FakeSession(response, error)
        patches = [mock.patch.object(g, 'makeGitHubSession', lambda: session)]
        if version:
            patches.append(mock.patch.object(g, '__version__', version))
        with patches[0], (patches[1] if version else mock.patch.object(g, 'HTTP_TIMEOUT', g.HTTP_TIMEOUT)):
            with self.assertLogs('gogrepoc', level='INFO') as logs:
                g.cmd_selfupdate(True)
        return '\n'.join(r.levelname + ' ' + r.getMessage() for r in logs.records)

    def test_a_newer_release_is_announced_with_its_address_and_nothing_is_installed(self):
        log = self.run_check(release(), version='0.5.53')
        self.assertIn('a newer release is available: v0.5.60 (Version 0.5.60)', log)
        self.assertIn('get it from ' + URL, log)
        self.assertIn('nothing was downloaded or installed', log)
        self.assertIn('SHA256SUMS', log)
        self.assertEqual(g.run_report.counts, {'newer releases available': [1, 0]})
        self.assertEqual(g.run_report.exit_status(), 0)

    def test_the_same_version_is_the_latest(self):
        log = self.run_check(release(), version='0.5.60')
        self.assertIn('this is the latest release', log)
        self.assertNotIn('newer release is available', log)
        self.assertEqual(g.run_report.counts, {})

    def test_a_version_ahead_of_the_release_is_called_a_development_version(self):
        log = self.run_check(release(), version='0.5.61')
        self.assertIn('newer than the latest release', log)
        self.assertNotIn('newer release is available', log)

    def test_ten_is_newer_than_nine(self):
        log = self.run_check(release(tag_name='v0.5.10', name=None), version='0.5.9')
        self.assertIn('a newer release is available: v0.5.10', log)

    def test_a_failure_is_an_error_and_exit_status_one(self):
        log = self.run_check(FakeResponse(404), version='0.5.53')
        self.assertIn('ERROR could not check for a newer release: GitHub knows no published release', log)
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertEqual(g.run_report.failures[0][0], 'release check')

    def test_no_network_is_a_failure_not_a_traceback(self):
        log = self.run_check(error=requests.ConnectionError('offline'))
        self.assertIn('could not reach GitHub', log)
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_a_text_with_escape_sequences_cannot_reach_the_console(self):
        log = self.run_check(release(name='\x1b[2J\x1b[31mevil\nline2'), version='0.5.53')
        self.assertNotIn('\x1b', log)
        self.assertIn('evil line2', log)

    def test_nothing_is_written_to_disk(self):
        self.run_check(release(), version='0.5.53')
        self.assertEqual(os.listdir(self.dir), [])

    def test_the_gog_login_and_the_gog_session_are_never_touched(self):
        boom = mock.Mock(side_effect=AssertionError('must not be used by selfupdate'))
        with mock.patch.object(g, 'makeGOGSession', boom), mock.patch.object(g, 'load_token', boom), \
                mock.patch.object(g, 'save_token', boom), mock.patch.object(g, 'request', boom), mock.patch.object(g, 'load_manifest', boom):
            self.run_check(release(), version='0.5.53')
        boom.assert_not_called()


class CommandLineTests(unittest.TestCase):
    def parse(self, *argv):
        return g.process_argv(['gogrepo_delta.py'] + list(argv) + ['-nolog'])

    def test_the_command_has_one_switch_which_is_optional(self):
        self.assertFalse(self.parse('selfupdate').check)
        self.assertTrue(self.parse('selfupdate', '-check').check)
        self.assertTrue(self.parse('selfupdate', '--check').check)

    def test_the_common_switches_work(self):
        self.assertTrue(self.parse('selfupdate', '-debug').debug)

    def test_there_is_no_download_or_install_switch(self):
        with self.assertRaises(SystemExit), mock.patch('sys.stderr'):
            self.parse('selfupdate', '-download')

    def test_main_runs_the_check_and_returns_the_exit_status(self):
        session = FakeSession(release())
        with mock.patch.object(g, 'makeGitHubSession', lambda: session), mock.patch.object(g, '__version__', '0.5.53'), \
                self.assertLogs('gogrepoc', level='INFO') as logs:
            status = g.main(self.parse('selfupdate'))
        self.assertEqual(status, 0)
        self.assertIn('-- summary: selfupdate', [r.getMessage() for r in logs.records])
        with mock.patch.object(g, 'makeGitHubSession', lambda: FakeSession(FakeResponse(500))), self.assertLogs('gogrepoc', level='INFO'):
            self.assertEqual(g.main(self.parse('selfupdate')), 1)

    def test_update_self_is_still_not_connected_to_any_command(self):
        with mock.patch.object(g, 'update_self', side_effect=AssertionError('must not run')) as old:
            with mock.patch.object(g, 'makeGitHubSession', lambda: FakeSession(release())), self.assertLogs('gogrepoc', level='INFO'):
                g.main(self.parse('selfupdate'))
        old.assert_not_called()


if __name__ == '__main__':
    unittest.main()
