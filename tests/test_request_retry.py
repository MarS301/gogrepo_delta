"""request(), request_head() and renew_token(): one retry loop (no recursion), Retry-After, ChunkedEncodingError, and a token refresh that
tells a temporary problem (network, GOG busy) from a refused login. All offline: fake sessions return real requests.Response objects."""
import email.utils
import inspect
import io
import logging
import os
import time
import types
import unittest
from unittest import mock

import requests

import _bootstrap  # noqa: F401
import gogrepo_delta as g


def response(status=200, headers=None, body=b'{}'):
    r = requests.Response()
    r.status_code = status
    r._content = body
    r.url = 'https://example.invalid/x'
    for k, v in (headers or {}).items():
        r.headers[k] = v
    return r


class FakeSession:
    """Answers from a list, one item per call: a Response, or an exception instance to raise. No `token`: not a token session."""
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def _answer(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        item = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, **kw):
        return self._answer('get', url, kw)

    def post(self, url, **kw):
        return self._answer('post', url, kw)

    def head(self, url, **kw):
        return self._answer('head', url, kw)


class RetryTestCase(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        for p in (mock.patch.object(g.time, 'sleep', self.sleeps.append), mock.patch.object(g, 'HTTP_RETRY_DELAY', 5)):
            p.start()
            self.addCleanup(p.stop)

    def logged(self, func):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            try:
                result = func()
            except (Exception, SystemExit) as e:      # AuthExpired is a SystemExit; the tests look at the exception separately
                result = e
            g.info('end of test')
        return result, '\n'.join(logs.output)


class RequestLoopTests(RetryTestCase):
    def test_a_busy_server_is_tried_again_after_the_retry_delay(self):
        session = FakeSession([response(503), response(200)])
        result, log = self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertEqual(200, result.status_code)
        self.assertEqual(2, len(session.calls))
        self.assertEqual([5], self.sleeps)
        self.assertIn('(4 retries left) -- will retry in 5s...', log)

    def test_it_gives_up_after_the_given_number_of_retries(self):
        session = FakeSession([response(503)])
        result, log = self.logged(lambda: g.request(session, 'https://x/y', retries=2))
        self.assertIsInstance(result, requests.HTTPError)
        self.assertEqual(3, len(session.calls))
        self.assertEqual([5, 5], self.sleeps)

    def test_no_retries_means_one_attempt_and_no_wait(self):
        session = FakeSession([response(503)])
        result, _ = self.logged(lambda: g.request(session, 'https://x/y', retries=0))
        self.assertIsInstance(result, requests.HTTPError)
        self.assertEqual((1, []), (len(session.calls), self.sleeps))

    def test_the_configured_no_retry_codes_are_raised_at_once_with_a_warning(self):
        session = FakeSession([response(404)])
        result, log = self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertIsInstance(result, requests.HTTPError)
        self.assertEqual((1, []), (len(session.calls), self.sleeps))
        self.assertIn('will not retry', log)
        self.assertIn('WARNING', log)

    def test_a_quiet_status_is_raised_at_once_without_a_warning(self):
        session = FakeSession([response(404)])
        result, log = self.logged(lambda: g.request(session, 'https://x/y', quiet_statuses=(404,)))
        self.assertIsInstance(result, requests.HTTPError)
        self.assertIn('will not retry', log)
        self.assertNotIn('WARNING', log)

    def test_no_retry_statuses_apply_to_that_call_only(self):
        session = FakeSession([response(400), response(200)])
        result, _ = self.logged(lambda: g.request(session, 'https://x/y', no_retry_statuses=(400,)))
        self.assertIsInstance(result, requests.HTTPError)
        self.assertEqual(1, len(session.calls))
        session = FakeSession([response(400), response(200)])
        result, _ = self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertEqual(200, result.status_code)           # without it a 400 is still retried, as before
        self.assertEqual(2, len(session.calls))

    def test_network_errors_are_retried(self):
        for error in (requests.exceptions.ConnectionError('reset'), requests.exceptions.ReadTimeout('slow'),
                      requests.exceptions.SSLError('ssl'), requests.exceptions.ChunkedEncodingError('cut off')):
            with self.subTest(error=type(error).__name__):
                del self.sleeps[:]
                session = FakeSession([error, response(200)])
                result, _ = self.logged(lambda: g.request(session, 'https://x/y'))
                self.assertEqual(200, result.status_code)
                self.assertEqual([5], self.sleeps)

    def test_other_exceptions_are_not_swallowed(self):
        session = FakeSession([KeyError('boom')])
        result, _ = self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertIsInstance(result, KeyError)
        self.assertEqual(1, len(session.calls))

    def test_a_long_series_of_retries_does_not_recurse(self):
        # the old request() called itself once per retry: more than about 900 retries ended in a RecursionError
        session = FakeSession([response(503)] * 1500 + [response(200)])
        result, _ = self.logged(lambda: g.request(session, 'https://x/y', retries=1600))
        self.assertEqual(200, result.status_code)
        self.assertEqual(1501, len(session.calls))

    def test_a_decimal_delay_is_shown_as_it_is(self):
        with mock.patch.object(g, 'HTTP_RETRY_DELAY', 2.5):
            session = FakeSession([response(503), response(200)])
            _, log = self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertIn('will retry in 2.5s...', log)
        self.assertEqual([2.5], self.sleeps)

    def test_the_delay_argument_waits_before_the_first_attempt(self):
        session = FakeSession([response(200)])
        self.logged(lambda: g.request(session, 'https://x/y', delay=3))
        self.assertEqual([3], self.sleeps)

    def test_the_request_is_built_as_before(self):
        session = FakeSession([response(200)])
        self.logged(lambda: g.request(session, 'https://x/y', args={'a': 1}, byte_range=(0, 9), stream=True))
        method, url, kw = session.calls[0]
        self.assertEqual(('get', 'https://x/y'), (method, url))
        self.assertEqual({'a': 1}, kw['params'])
        self.assertEqual({'Range': 'bytes=0-9'}, kw['headers'])
        self.assertTrue(kw['stream'])
        session = FakeSession([response(200)])
        self.logged(lambda: g.request(session, 'https://x/y', data={'k': 'v'}))
        method, _, kw = session.calls[0]
        self.assertEqual(('post', {'k': 'v'}), (method, kw['data']))
        self.assertNotIn('headers', kw)

    def test_the_signatures_keep_their_defaults(self):
        for func in (g.request, g.request_head):
            self.assertEqual(g.HTTP_RETRY_COUNT, inspect.signature(func).parameters['retries'].default)


class RequestHeadTests(RetryTestCase):
    def test_head_is_retried_and_built_as_before(self):
        session = FakeSession([response(500), response(200)])
        result, _ = self.logged(lambda: g.request_head(session, 'https://x/y', allow_redirects=False))
        self.assertEqual(200, result.status_code)
        self.assertEqual([5], self.sleeps)
        self.assertEqual(('head', False), (session.calls[0][0], session.calls[0][2]['allow_redirects']))

    def test_head_does_not_retry_the_no_retry_codes(self):
        session = FakeSession([response(403), response(200)])
        result, log = self.logged(lambda: g.request_head(session, 'https://x/y'))
        self.assertIsInstance(result, requests.HTTPError)
        self.assertEqual(1, len(session.calls))
        self.assertIn('will not retry', log)

    def test_head_honours_retry_after(self):
        session = FakeSession([response(429, {'Retry-After': '30'}), response(200)])
        self.logged(lambda: g.request_head(session, 'https://x/y'))
        self.assertEqual([30.0], self.sleeps)


class RetryAfterTests(RetryTestCase):
    def wait_for(self, header, status=429):
        del self.sleeps[:]
        session = FakeSession([response(status, {'Retry-After': header} if header is not None else {}), response(200)])
        self.logged(lambda: g.request(session, 'https://x/y'))
        return self.sleeps[0]

    def test_a_longer_retry_after_wins_over_the_delay(self):
        self.assertEqual(30.0, self.wait_for('30'))
        self.assertEqual(30.0, self.wait_for('30', status=503))

    def test_a_shorter_retry_after_never_shortens_the_delay(self):
        self.assertEqual(5, self.wait_for('1'))
        self.assertEqual(5, self.wait_for('0'))

    def test_no_header_or_a_bad_one_means_the_delay(self):
        for header in (None, '', 'soon', '-10', 'nan'):
            with self.subTest(header=header):
                self.assertEqual(5, self.wait_for(header))

    def test_it_never_waits_longer_than_the_limit(self):
        self.assertEqual(g.RETRY_AFTER_MAX, self.wait_for('86400'))

    def test_an_http_date_is_understood(self):
        when = email.utils.formatdate(time.time() + 61, usegmt=True)
        waited = self.wait_for(when)
        self.assertTrue(55 <= waited <= 61, waited)

    def test_an_http_date_in_the_past_means_the_delay(self):
        self.assertEqual(5, self.wait_for(email.utils.formatdate(time.time() - 3600, usegmt=True)))


class TokenRefreshTests(RetryTestCase):
    def session(self, answers, expiry=None):
        s = FakeSession(answers)
        s.token = {'access_token': 'old', 'refresh_token': 'r', 'expiry': time.time() - 100 if expiry is None else expiry}
        s.headers = {}
        return s

    def fresh(self, expires_in=3600):
        return response(200, body=('{"access_token": "new", "refresh_token": "r2", "expires_in": %d}' % expires_in).encode())

    def setUp(self):
        super().setUp()
        self.saved = []
        p = mock.patch.object(g, 'save_token', lambda token: self.saved.append(dict(token)))
        p.start()
        self.addCleanup(p.stop)

    def renew(self, session, **kw):
        return self.logged(lambda: g.renew_token(session, **kw))

    def test_a_good_refresh_updates_the_token_saves_it_and_sets_the_header(self):
        s = self.session([self.fresh()])
        before = time.time()
        _, _ = self.renew(s)
        self.assertEqual(('new', 'r2'), (s.token['access_token'], s.token['refresh_token']))
        self.assertGreaterEqual(s.token['expiry'], before + 3600)
        self.assertEqual('Bearer new', s.headers['Authorization'])
        self.assertEqual(1, len(self.saved))

    def test_a_valid_token_asks_nobody(self):
        s = self.session([self.fresh()], expiry=time.time() + 3600)
        self.renew(s)
        self.assertEqual([], s.calls)

    def test_a_session_without_a_token_is_left_alone(self):
        s = FakeSession([self.fresh()])
        self.renew(s)
        self.assertEqual([], s.calls)

    def test_a_busy_token_server_is_tried_again_and_the_login_survives(self):
        s = self.session([response(503), requests.exceptions.ConnectionError('down'), self.fresh()])
        _, log = self.renew(s)
        self.assertEqual('new', s.token['access_token'])
        self.assertEqual([5, 5], self.sleeps)
        self.assertIn('token refresh failed', log)
        self.assertIn('(4 retries left)', log)

    def test_a_network_problem_that_lasts_is_not_reported_as_an_expired_login(self):
        for error in (requests.exceptions.ConnectTimeout('slow'), requests.exceptions.ReadTimeout('slow'), requests.exceptions.ConnectionError('down'),
                      requests.exceptions.ChunkedEncodingError('cut off'), response(500), response(429)):
            with self.subTest(error=repr(error)):
                s = self.session([error])
                result, log = self.renew(s, retries=2)
                self.assertNotIsInstance(result, g.AuthExpired)
                self.assertIsInstance(result, requests.RequestException)
                self.assertEqual(3, len(s.calls))
                self.assertEqual('old', s.token['access_token'])
                self.assertEqual([], self.saved)
                self.assertNotIn('please login again', log.lower())      # it says the login is NOT affected, never that it is gone

    def test_a_refused_refresh_token_means_login_again_without_retrying(self):
        for status in (400, 401, 403):
            with self.subTest(status=status):
                s = self.session([response(status)])
                result, log = self.renew(s)
                self.assertIsInstance(result, g.AuthExpired)
                self.assertEqual(1, len(s.calls))
                self.assertEqual([], self.sleeps)
                self.assertIn('Please login again', log)

    def test_an_unusable_answer_means_login_again(self):
        for answer in (response(200, body=b'<html>captive portal</html>'), response(200, body=b'[1, 2]')):
            with self.subTest(body=answer.content):
                result, _ = self.renew(self.session([answer]))
                self.assertIsInstance(result, g.AuthExpired)

    def test_a_token_without_a_refresh_token_means_login_again(self):
        s = self.session([self.fresh()])
        del s.token['refresh_token']
        result, _ = self.renew(s)
        self.assertIsInstance(result, g.AuthExpired)
        self.assertEqual([], s.calls)

    def test_retry_after_is_honoured_by_the_refresh(self):
        s = self.session([response(429, {'Retry-After': '40'}), self.fresh()])
        self.renew(s)
        self.assertEqual([40.0], self.sleeps)

    def test_the_lock_is_free_after_a_failed_refresh(self):
        s = self.session([response(500)])
        self.renew(s, retries=0)
        self.assertTrue(g.token_lock.acquire(blocking=False))
        g.token_lock.release()

    def test_request_renews_first_and_a_lost_login_ends_it_as_before(self):
        s = self.session([response(400)])
        result, _ = self.logged(lambda: g.request(s, 'https://x/y'))
        self.assertIsInstance(result, g.AuthExpired)
        self.assertEqual(1, len(s.calls))           # only the refresh was asked; the real request never went out


class RedactionTests(unittest.TestCase):
    """Entry 69: tokens, secrets, codes and passwords never reach the log."""
    def test_query_values_are_hidden_and_the_rest_of_the_address_stays(self):
        text = ('400 Client Error: Bad Request for url: https://auth.gog.com/token?client_id=469&client_secret=S3CRET&grant_type=refresh_token'
                '&refresh_token=RT0KEN&x=1')
        self.assertEqual('400 Client Error: Bad Request for url: https://auth.gog.com/token?client_id=469&client_secret=***'
                         '&grant_type=refresh_token&refresh_token=***&x=1', g.redact_secrets(text))

    def test_the_login_code_and_the_other_names_are_hidden(self):
        for name in ('code', 'access_token', 'token', 'password', 'CODE', 'Refresh_Token'):
            with self.subTest(name=name):
                self.assertEqual('?a=1&%s=***&b=2' % name, g.redact_secrets('?a=1&%s=VALUE&b=2' % name))

    def test_dictionaries_json_and_headers_are_hidden(self):
        self.assertEqual("{'refresh_token': '***', \"access_token\": \"***\", 'user': 'me'}",
                         g.redact_secrets("{'refresh_token': 'ZZZ', \"access_token\": \"YYY\", 'user': 'me'}"))
        self.assertEqual('Authorization: Bearer ***', g.redact_secrets('Authorization: Bearer abc.def-1_2='))

    def test_ordinary_text_is_not_touched(self):
        for text in ('downloading id(s)/title(s): {witcher_3}', 'errorcode=5', 'the_code=1', 'token refresh failed: timed out (4 retries left)',
                     'refreshing token', 'loading token...', 'status code 404', 'https://api.gog.com/products/1207658924?expand=downloads'):
            with self.subTest(text=text):
                self.assertEqual(text, g.redact_secrets(text))

    def test_it_is_safe_to_apply_twice(self):
        once = g.redact_secrets('?refresh_token=abc&code=def')
        self.assertEqual(once, g.redact_secrets(once))

    def test_both_handlers_have_the_filter(self):
        for handler in (g.consoleHandler, g.loggingHandler):
            self.assertTrue(any(isinstance(f, g.SecretFilter) for f in handler.filters), handler)

    def test_the_filter_keeps_every_record_and_leaves_clean_ones_alone(self):
        record = logging.LogRecord('x', logging.INFO, __file__, 1, 'moved %s of %d', ('a.bin', 5), None)
        self.assertTrue(g.SecretFilter().filter(record))
        self.assertEqual(('moved %s of %d', ('a.bin', 5)), (record.msg, record.args))
        record = logging.LogRecord('x', logging.INFO, __file__, 1, 'bad %s', ('?refresh_token=abc',), None)
        self.assertTrue(g.SecretFilter().filter(record))
        self.assertEqual('bad ?refresh_token=***', record.getMessage())

    def test_a_record_that_cannot_be_formatted_is_not_dropped(self):
        record = logging.LogRecord('x', logging.INFO, __file__, 1, 'needs %s and %s', ('one',), None)
        self.assertTrue(g.SecretFilter().filter(record))


class LocalServerTests(RetryTestCase):
    """The same behaviour over a real socket: a local HTTP server stands in for GOG (and its token server)."""
    def serve(self, script):
        """script: one item per request, the last repeats. Item: (status, headers, body) or None (close the connection without an answer)."""
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        hits = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def do_GET(self):
                hits.append(self.path)
                item = script[min(len(hits), len(script)) - 1]
                if item is None:
                    self.close_connection = True
                    self.connection.close()
                    return
                status, headers, body = item
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:%d/x' % server.server_address[1], hits

    def test_request_survives_a_busy_answer_and_a_dropped_connection(self):
        url, hits = self.serve([(503, {'Retry-After': '12'}, b''), None, (200, {}, b'ok')])
        result, _ = self.logged(lambda: g.request(requests.Session(), url))
        self.assertEqual(b'ok', result.content)
        self.assertEqual(3, len(hits))
        self.assertEqual([12.0, 5], self.sleeps)

    def test_a_404_is_asked_once(self):
        url, hits = self.serve([(404, {}, b'')])
        result, _ = self.logged(lambda: g.request(requests.Session(), url))
        self.assertIsInstance(result, requests.HTTPError)
        self.assertEqual((1, []), (len(hits), self.sleeps))

    def test_the_token_refresh_survives_a_busy_token_server(self):
        good = b'{"access_token": "new", "refresh_token": "r2", "expires_in": 3600}'
        url, hits = self.serve([(503, {}, b''), (200, {}, good)])
        session = requests.Session()
        session.token = {'access_token': 'old', 'refresh_token': 'r', 'expiry': time.time() - 1}
        saved = []
        with mock.patch.object(g, 'GOG_TOKEN_URL', url), mock.patch.object(g, 'save_token', saved.append):
            self.logged(lambda: g.renew_token(session))
        self.assertEqual(2, len(hits))
        self.assertEqual('Bearer new', session.headers['Authorization'])
        self.assertEqual(1, len(saved))

    def test_a_refused_refresh_token_asks_the_token_server_once(self):
        url, hits = self.serve([(400, {}, b'{"error": "invalid_grant"}')])
        session = requests.Session()
        session.token = {'access_token': 'old', 'refresh_token': 'r', 'expiry': time.time() - 1}
        with mock.patch.object(g, 'GOG_TOKEN_URL', url):
            result, _ = self.logged(lambda: g.renew_token(session))
        self.assertIsInstance(result, g.AuthExpired)
        self.assertEqual((1, []), (len(hits), self.sleeps))

    def log_into_real_handlers(self, func):
        """Runs func with the program's own console filter and its log file handler (as main attaches them) on the logger; returns
        what the console handler wrote and what the log file now holds."""
        console = io.StringIO()
        handler = logging.StreamHandler(console)
        handler.setFormatter(g.logFormatter)
        for f in g.consoleHandler.filters:
            handler.addFilter(f)
        g.rootLogger.addHandler(handler)
        g.rootLogger.addHandler(g.loggingHandler)
        try:
            try:
                func()
            except (Exception, SystemExit):
                g.log_exception('fatal...')
        finally:
            g.rootLogger.removeHandler(handler)
            g.rootLogger.removeHandler(g.loggingHandler)
            g.loggingHandler.flush()
        with open(g.loggingHandler.baseFilename, encoding='utf-8') as r:
            return console.getvalue(), r.read()

    def test_a_refused_refresh_leaves_no_token_in_the_console_or_the_log_file(self):
        url, _ = self.serve([(400, {}, b'{"error": "invalid_grant"}')])
        session = requests.Session()
        session.token = {'access_token': 'ACC3SS', 'refresh_token': 'R3FRESH', 'expiry': time.time() - 1}
        with mock.patch.object(g, 'GOG_TOKEN_URL', url), mock.patch.object(g, 'GOG_SECRET', 'S3CRETVALUE'):
            console, logfile = self.log_into_real_handlers(lambda: g.renew_token(session))
        for where, text in (('console', console), ('log file', logfile)):
            with self.subTest(where=where):
                self.assertIn('400 Client Error', text)             # the error is still reported ...
                self.assertIn('refresh_token=***', text)            # ... with the values hidden
                for secret in ('R3FRESH', 'S3CRETVALUE'):
                    self.assertNotIn(secret, text)

    def test_the_traceback_of_a_failed_request_is_cleaned_too(self):
        url, _ = self.serve([(404, {}, b'')])
        console, logfile = self.log_into_real_handlers(lambda: g.request(requests.Session(), url + '?refresh_token=TR4CEBACK&code=0NECODE'))
        for where, text in (('console', console), ('log file', logfile)):
            with self.subTest(where=where):
                self.assertIn('Traceback', text)
                for secret in ('TR4CEBACK', '0NECODE'):
                    self.assertNotIn(secret, text)

if __name__ == '__main__':
    unittest.main()
