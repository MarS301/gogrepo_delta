"""The retry loop of chunk verification (_download_with_chunk_verification): a chunk that did not arrive completely is tried again
after HTTP_RETRY_DELAY seconds, as the plain download loop does; before, it said "will retry in Ns" and did not wait."""
import hashlib
import os
import shutil
import tempfile
import threading
import types
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

GOOD = b'b' * 10


def tree(expected=GOOD):
    xml = ('<file name="x.bin" total_size="10" chunks="1"><chunk id="0" from="0" to="9" method="md5">%s</chunk></file>'
           % hashlib.md5(expected).hexdigest())
    return g.xml.etree.ElementTree.fromstring(xml)


class ChunkRetryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='chunkretry_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, 'x.bin')
        with open(self.path, 'wb') as w:
            w.write(b'a' * 10)                      # the file on disk is wrong: the chunk has to be fetched
        self.job = types.SimpleNamespace(lock=threading.Lock(), sizes={'x.bin': 10}, session=None)
        self.requests = []
        self.sleeps = []
        self.lock_held_while_sleeping = []
        self.outcomes = []                          # per attempt: how many bytes arrive (10 = all)
        patches = [mock.patch.object(g, 'request', self.fake_request),
                   mock.patch.object(g, '_download_ioloop', self.fake_ioloop),
                   mock.patch.object(g.time, 'sleep', self.fake_sleep)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_request(self, session, url, byte_range=None, stream=False, **kw):
        self.requests.append(byte_range)
        return types.SimpleNamespace(headers={'Content-Range': 'bytes 0-9/10'})

    def fake_ioloop(self, job, tid, path, response, out):
        arriving = self.outcomes.pop(0)
        out.write(GOOD[:arriving])
        return arriving

    def fake_sleep(self, seconds):
        self.sleeps.append(seconds)
        self.lock_held_while_sleeping.append(self.job.lock.locked())

    def run_chunks(self):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            result = g._download_with_chunk_verification(self.job, 1, 'http://x/x.bin', 'x.bin', self.path, 10, tree())
            g.info('end of test')
        return result, '\n'.join(logs.output)

    def test_a_chunk_that_arrives_at_once_needs_no_wait(self):
        self.outcomes = [10]
        result, log = self.run_chunks()
        self.assertTrue(result)
        self.assertEqual((self.requests, self.sleeps), ([(0, 9)], []))

    def test_a_chunk_that_fails_once_is_tried_again_after_the_retry_delay(self):
        self.outcomes = [4, 10]
        result, log = self.run_chunks()
        self.assertTrue(result)
        self.assertEqual(self.requests, [(0, 9), (0, 9)])
        self.assertEqual(self.sleeps, [g.HTTP_RETRY_DELAY])
        self.assertIn('will retry in %ds' % g.HTTP_RETRY_DELAY, log)

    def test_it_gives_up_after_the_configured_number_of_retries_and_waits_between_all_of_them(self):
        with mock.patch.object(g, 'HTTP_RETRY_COUNT', 2), mock.patch.object(g, 'HTTP_RETRY_DELAY', 7):
            self.outcomes = [1, 2, 3]
            result, log = self.run_chunks()
        self.assertFalse(result)
        self.assertEqual(len(self.requests), 3)                       # the first try and two retries
        self.assertEqual(self.sleeps, [7, 7])                         # a wait before each retry, none after the last try
        self.assertIn('failed to download x.bin, byte_range=(0, 9)', log)

    def test_the_wait_does_not_hold_the_lock_of_the_other_downloads(self):
        self.outcomes = [4, 10]
        self.run_chunks()
        self.assertEqual(self.lock_held_while_sleeping, [False])

    def test_the_progress_counter_counts_only_what_arrived(self):
        self.outcomes = [4, 10]
        self.run_chunks()
        self.assertEqual(self.job.sizes['x.bin'], 10 + 4)             # what the failed attempt delivered stays counted as before

    def test_a_chunk_that_is_already_right_is_not_requested_at_all(self):
        with open(self.path, 'wb') as w:
            w.write(GOOD)
        result, log = self.run_chunks()
        self.assertTrue(result)
        self.assertEqual((self.requests, self.sleeps), ([], []))
        self.assertEqual(self.job.sizes['x.bin'], 0)

    def test_an_http_error_is_final_and_not_waited_for(self):
        import requests
        with mock.patch.object(g, 'request', side_effect=requests.HTTPError('403')):
            result, log = self.run_chunks()
        self.assertFalse(result)
        self.assertEqual(self.sleeps, [])

    def test_an_unexpected_content_range_is_final_and_not_waited_for(self):
        with mock.patch.object(g, 'request', lambda *a, **k: types.SimpleNamespace(headers={'Content-Range': 'bytes 5-9/10'})):
            result, log = self.run_chunks()
        self.assertFalse(result)
        self.assertEqual(self.sleeps, [])
        self.assertIn('unexpected Content-Range', log)

    def test_the_plain_loop_waits_the_same_time(self):
        # the loop that downloads without chunk data: the same constant between the tries
        self.outcomes = [3, 10]
        with mock.patch.object(g, 'open_notrunc', g.open_notruncwrrd), self.assertLogs('gogrepoc', level='DEBUG'):
            result = g._download_without_chunk_verification(self.job, 1, 'http://x/x.bin', 'x.bin', self.path, 10, 0, 9)
        self.assertTrue(result)
        self.assertEqual(self.sleeps, [g.HTTP_RETRY_DELAY])


if __name__ == '__main__':
    unittest.main()
