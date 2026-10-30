"""Tests for the combined MD5 warnings and the quiet_statuses option of request()."""
import logging, os, sys, threading, time, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import _bootstrap  # noqa: F401
import requests
import gogrepo_delta as G

class Capture(logging.Handler):
    def __init__(self): super().__init__(logging.DEBUG); self.records = []
    def emit(self, r): self.records.append(r)
    def at(self, level): return [r.getMessage() for r in self.records if r.levelno == level]

# URLs copied from the user's log
URL = 'https://gog-cdn-fastly.gog.com/token=nva=1791549284~dirs=4~token=0bb2409895bad6e13f0f9/secure/witcher_3/goty/lang/%s'

class Base(unittest.TestCase):
    def setUp(self):
        self.cap = Capture(); G.rootLogger.addHandler(self.cap)
        self.old_level = G.rootLogger.level; G.rootLogger.setLevel(logging.INFO)
        G.flush_summarised(); self.cap.records.clear()
    def tearDown(self):
        G.rootLogger.removeHandler(self.cap); G.rootLogger.setLevel(self.old_level)

class Summaries(Base):
    def test_prefix_notice_is_one_combined_warning(self):
        for i in range(15):
            out = G.append_xml_extension_to_url_path(URL % ('patch_witcher3_de_goty_2.0.0.%d.exe' % i))
            self.assertTrue(out.endswith('.exe.xml') or out.endswith('.xml'))          # URL building unchanged
        self.assertEqual(self.cap.at(logging.WARNING), [])                              # nothing while running
        G.flush_summarised()
        warnings = self.cap.at(logging.WARNING)
        self.assertEqual(len(warnings), 1); self.assertIn('15 file(s)', warnings[0]); self.assertIn("'prefix'", warnings[0])
        G.flush_summarised(); self.assertEqual(len(self.cap.at(logging.WARNING)), 1)    # flush clears

    def test_url_with_prefix_param_still_rewritten_silently(self):
        out = G.append_xml_extension_to_url_path('https://x.example/secure/a.exe?prefix=secure/a.exe&wsTime=1')
        self.assertIn('prefix=secure%2Fa.exe.xml'.replace('%2F', '/'), out.replace('%2F', '/'))
        G.flush_summarised(); self.assertEqual(self.cap.at(logging.WARNING), [])

    def test_no_md5_names_deduplicated_and_capped(self):
        for n in range(20): G.note_summarised('no md5 data', 'file%d.exe' % n, G.NO_MD5_MESSAGE)
        G.note_summarised('no md5 data', 'file0.exe', G.NO_MD5_MESSAGE)                   # second site, same file
        G.flush_summarised()
        (w,) = self.cap.at(logging.WARNING)
        self.assertIn('20 file(s)', w); self.assertIn('file0.exe', w); self.assertIn('and 5 more', w); self.assertNotIn('file19.exe', w)

    def test_details_available_at_debug(self):
        G.rootLogger.setLevel(logging.DEBUG)
        G.note_summarised('no md5 data', 'patch.exe', G.NO_MD5_MESSAGE)
        self.assertTrue(any('patch.exe' in m for m in self.cap.at(logging.DEBUG)))

    def test_thread_safe(self):
        ts = [threading.Thread(target=lambda i=i: [G.note_summarised('k', 'f%d_%d' % (i, j), '{count}') for j in range(50)]) for i in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        G.flush_summarised(); self.assertEqual(self.cap.at(logging.WARNING), ['400'])

    def test_replay_of_users_log_gives_two_warnings(self):
        """~45 files: all have no 'prefix', 15 of them also have no MD5 XML (404)."""
        for i in range(45): G.append_xml_extension_to_url_path(URL % ('file%d.exe' % i))
        for i in range(15):
            G.note_summarised('no md5 data', 'patch_%d.exe' % i, G.NO_MD5_MESSAGE)   # fetch_file_info 404 handler
            G.note_summarised('no md5 data', 'patch_%d.exe' % i, G.NO_MD5_MESSAGE)   # filter_downloads
        G.flush_summarised(); self.assertEqual(len(self.cap.at(logging.WARNING)), 2)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404 if self.path.endswith('.xml') else 200); self.end_headers(); self.wfile.write(b'x')
    def log_message(self, *a): pass

class QuietStatuses(Base):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(('127.0.0.1', 0), Handler); cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
    def session(self):
        s = requests.Session(); s.token = {'expiry': time.time() + 10000, 'refresh_token': 'x'}; return s
    def url(self, name): return 'http://127.0.0.1:%d/%s' % (self.port, name)

    def test_default_404_still_warns(self):
        with self.assertRaises(requests.HTTPError): G.request(self.session(), self.url('a.exe.xml'))
        self.assertEqual(len(self.cap.at(logging.WARNING)), 1); self.assertIn('will not retry', self.cap.at(logging.WARNING)[0])

    def test_quiet_404_does_not_warn_but_still_raises(self):
        with self.assertRaises(requests.HTTPError) as cm: G.request(self.session(), self.url('a.exe.xml'), quiet_statuses=(404,))
        self.assertEqual(cm.exception.response.status_code, 404)
        self.assertEqual(self.cap.at(logging.WARNING), [])

    def test_quiet_404_logged_at_debug(self):
        G.rootLogger.setLevel(logging.DEBUG)
        with self.assertRaises(requests.HTTPError): G.request(self.session(), self.url('a.exe.xml'), quiet_statuses=(404,))
        self.assertTrue(any('will not retry' in m for m in self.cap.at(logging.DEBUG)))

    def test_success_unaffected(self):
        self.assertEqual(G.request(self.session(), self.url('a.exe'), quiet_statuses=(404,)).status_code, 200)

if __name__ == '__main__':
    unittest.main(verbosity=2)
