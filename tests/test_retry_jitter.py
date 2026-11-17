"""Entry 72: every wait before a retry varies at random by up to 20 percent (5 s becomes anything from 4 to 6 s), so that threads that failed
together do not all try again together. A Retry-After of the server is never shortened."""
import types
import unittest
from unittest import mock

import requests

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_request_retry import FakeSession, response, RetryTestCase


class JitterFunctionTests(unittest.TestCase):
    def test_the_default_is_twenty_percent(self):
        self.assertEqual(0, g.RETRY_JITTER)      # the tests switch it off (see _bootstrap); the program's own value is checked in the source
        with open(g.__file__, encoding='utf-8') as r:
            self.assertIn('RETRY_JITTER = 0.2 ', r.read())

    def test_five_seconds_become_anything_from_four_to_six(self):
        with mock.patch.object(g, 'RETRY_JITTER', 0.2):
            values = [g._jittered(5) for _ in range(3000)]
        self.assertTrue(all(4.0 <= v <= 6.0 for v in values), (min(values), max(values)))
        self.assertLess(min(values), 4.2)                  # the whole range is used, in both directions
        self.assertGreater(max(values), 5.8)
        self.assertAlmostEqual(5.0, sum(values) / len(values), delta=0.1)    # and it is centred on the delay
        self.assertGreater(len(set(values)), 1000)         # and really random

    def test_the_two_ends_of_the_range(self):
        with mock.patch.object(g, 'RETRY_JITTER', 0.2):
            with mock.patch.object(g.random, 'uniform', lambda low, high: low):
                self.assertAlmostEqual(4.0, g._jittered(5))
            with mock.patch.object(g.random, 'uniform', lambda low, high: high):
                self.assertAlmostEqual(6.0, g._jittered(5))

    def test_it_scales_with_the_delay(self):
        with mock.patch.object(g, 'RETRY_JITTER', 0.2), mock.patch.object(g.random, 'uniform', lambda low, high: high):
            self.assertAlmostEqual(12.0, g._jittered(10))
            self.assertAlmostEqual(0.3, g._jittered(0.25))

    def test_no_jitter_and_no_wait_are_left_alone(self):
        self.assertEqual(5, g._jittered(5))                # RETRY_JITTER is 0 in the tests
        with mock.patch.object(g, 'RETRY_JITTER', 0.2):
            self.assertEqual(0, g._jittered(0))
        with mock.patch.object(g, 'RETRY_JITTER', 0):
            self.assertEqual(5, g._jittered(5))

    def test_without_jitter_the_random_generator_is_not_used(self):
        with mock.patch.object(g, 'RETRY_JITTER', 0), mock.patch.object(g.random, 'uniform', side_effect=AssertionError('must not be used')):
            self.assertEqual(5, g._jittered(5))

    def test_the_text_of_a_wait_has_at_most_one_decimal(self):
        for seconds, text in ((5, '5'), (10, '10'), (100, '100'), (2.5, '2.5'), (4.73918, '4.7'), (5.04, '5'), (0, '0'), (0.25, '0.2'), (5.96, '6')):
            with self.subTest(seconds=seconds):
                self.assertEqual(text, g._seconds_text(seconds))


class RetryWaitTests(RetryTestCase):
    def jitter_on(self, edge):
        for p in (mock.patch.object(g, 'RETRY_JITTER', 0.2), mock.patch.object(g.random, 'uniform', lambda low, high: edge(low, high))):
            p.start()
            self.addCleanup(p.stop)

    def test_request_waits_the_jittered_delay_and_says_so(self):
        self.jitter_on(lambda low, high: high)
        session = FakeSession([response(503), response(200)])
        _, log = self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertEqual([6.0], [round(s, 6) for s in self.sleeps])
        self.assertIn('will retry in 6s...', log)

    def test_request_head_waits_the_jittered_delay(self):
        self.jitter_on(lambda low, high: low)
        session = FakeSession([response(500), response(200)])
        self.logged(lambda: g.request_head(session, 'https://x/y'))
        self.assertEqual([4.0], [round(s, 6) for s in self.sleeps])

    def test_a_longer_retry_after_is_kept_exactly(self):
        self.jitter_on(lambda low, high: high)
        session = FakeSession([response(429, {'Retry-After': '30'}), response(200)])
        self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertEqual([30.0], self.sleeps)

    def test_a_retry_after_is_never_shortened_by_the_jitter(self):
        self.jitter_on(lambda low, high: low)               # the jittered delay would be 4 s
        session = FakeSession([response(429, {'Retry-After': '5'}), response(200)])
        self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertEqual([5.0], self.sleeps)

    def test_the_token_refresh_retries_with_the_jittered_delay(self):
        self.jitter_on(lambda low, high: high)
        s = FakeSession([response(503), response(200, body=b'{"access_token": "n", "refresh_token": "r", "expires_in": 3600}')])
        s.token = {'access_token': 'o', 'refresh_token': 'r', 'expiry': 0}
        s.headers = {}
        with mock.patch.object(g, 'save_token', lambda token: None):
            self.logged(lambda: g.renew_token(s))
        self.assertEqual([6.0], [round(x, 6) for x in self.sleeps])

    def test_every_wait_of_a_series_is_drawn_again(self):
        values = iter([1.0, 1.2, 0.8])
        self.jitter_on(lambda low, high: next(values))
        session = FakeSession([response(503)] * 3 + [response(200)])
        self.logged(lambda: g.request(session, 'https://x/y'))
        self.assertEqual([5.0, 6.0, 4.0], [round(x, 6) for x in self.sleeps])


if __name__ == '__main__':
    unittest.main()
