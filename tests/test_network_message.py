"""Entry 71: a network problem (no connection, no answer, a cut-off answer, GOG busy) that ends a run gets one short, friendly line
and a hint, not a page of traceback; the traceback stays for -debug and for every other error."""
import logging
import types
import unittest

import requests

import _bootstrap  # noqa: F401
import gogrepo_delta as g

URL = 'https://auth.gog.com/token?client_id=1'


def req(url=URL):
    return requests.Request('GET', url).prepare()


def http_error(status, url=URL):
    r = requests.Response()
    r.status_code = status
    r.url = url
    r.request = req(url)
    return requests.HTTPError('%d error' % status, response=r)


class TextTests(unittest.TestCase):
    def test_no_connection_names_the_host_and_says_to_try_later(self):
        text = g.network_problem_text(requests.exceptions.ConnectionError('boom', request=req()))
        self.assertEqual('Network problem: could not connect to auth.gog.com. Please check your internet connection and try again later.', text)

    def test_no_answer_in_time(self):
        for error in (requests.exceptions.ReadTimeout('slow', request=req()), requests.exceptions.ConnectTimeout('slow', request=req())):
            with self.subTest(error=type(error).__name__):
                self.assertEqual('Network problem: auth.gog.com did not answer in time. Please check your internet connection and try again later.',
                                 g.network_problem_text(error))

    def test_a_cut_off_answer(self):
        text = g.network_problem_text(requests.exceptions.ChunkedEncodingError('cut', request=req()))
        self.assertIn('connection to auth.gog.com was interrupted', text)
        self.assertIn('try again later', text)

    def test_a_busy_or_broken_gog(self):
        for status in (500, 503, 408, 429):
            with self.subTest(status=status):
                text = g.network_problem_text(http_error(status))
                self.assertEqual('GOG is busy or not working right now (error %d from auth.gog.com). Please try again later.' % status, text)

    def test_without_a_known_host_it_says_gog(self):
        self.assertIn('could not connect to GOG.', g.network_problem_text(requests.exceptions.ConnectionError('boom')))

    def test_other_errors_get_no_friendly_line(self):
        for error in (http_error(404), http_error(403), http_error(400), ValueError('x'), KeyError('x'), requests.exceptions.InvalidURL('x')):
            with self.subTest(error=repr(error)):
                self.assertIsNone(g.network_problem_text(error))

    def test_the_text_holds_no_address_query_and_so_no_secret(self):
        text = g.network_problem_text(requests.exceptions.ConnectionError('boom', request=req(URL + '&refresh_token=SECRET')))
        self.assertNotIn('SECRET', text)
        self.assertNotIn('?', text)


class LogTests(unittest.TestCase):
    def fatal(self, error, level):
        with self.assertLogs('gogrepoc', level=level) as logs:
            try:
                raise error
            except requests.RequestException as e:
                g.log_fatal_request_error(e)
        return '\n'.join(logs.output)

    def test_a_network_problem_is_one_friendly_line_and_a_hint_without_a_traceback(self):
        log = self.fatal(requests.exceptions.ConnectionError('boom', request=req()), 'INFO')
        self.assertIn('Network problem: could not connect to auth.gog.com', log)
        self.assertIn('-debug', log)
        self.assertNotIn('Traceback', log)
        self.assertNotIn('fatal', log)

    def test_with_debug_the_traceback_follows_the_friendly_line(self):
        log = self.fatal(requests.exceptions.ConnectionError('boom', request=req()), 'DEBUG')
        self.assertIn('Network problem: could not connect to auth.gog.com', log)
        self.assertIn('Traceback', log)
        self.assertNotIn('Run the command again with -debug', log)

    def test_any_other_request_error_is_logged_as_before(self):
        for level in ('INFO', 'DEBUG'):
            with self.subTest(level=level):
                log = self.fatal(http_error(404), level)
                self.assertIn('fatal...', log)
                self.assertIn('Traceback', log)
                self.assertNotIn('Network problem', log)
                self.assertNotIn('-debug', log)


class MainBlockTests(unittest.TestCase):
    """The real `if __name__ == "__main__":` block of the script, with main() failing."""
    def run_block(self, error):
        with open(g.__file__, encoding='utf-8') as r:
            source = r.read()
        block = source[source.index('if __name__ == "__main__":'):].replace('__name__ == "__main__"', 'True', 1)
        calls = []
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

    def test_a_network_problem_ends_the_run_with_status_1_and_the_friendly_line(self):
        status, log = self.run_block(requests.exceptions.ConnectionError('boom', request=req()))
        self.assertEqual(1, status)
        self.assertIn('Network problem: could not connect to auth.gog.com', log)
        self.assertNotIn('Traceback', log)

    def test_another_exception_still_ends_with_the_traceback(self):
        status, log = self.run_block(RuntimeError('real bug'))
        self.assertEqual(1, status)
        self.assertIn('fatal...', log)
        self.assertIn('Traceback', log)


if __name__ == '__main__':
    unittest.main()
