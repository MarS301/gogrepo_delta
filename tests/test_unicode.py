"""Text in any language: Chinese, Japanese, Korean, Russian, Arabic, Thai, accents and emoji in the manifest, the export,
the log file, game and file names, and in console output that is redirected on Windows (legacy code page)."""
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'download_rig'))
import rig  # noqa: E402

TEXTS = {'chinese': '\u4e2d\u6587\u6e38\u620f\uff1a\u5deb\u5e083 \u72c2\u730e', 'traditional chinese': '\u5deb\u5e2b3\uff1a\u72c2\u7375', 'japanese': '\u65e5\u672c\u8a9e\u306e\u30b2\u30fc\u30e0 \u3072\u3089\u304c\u306a \u30ab\u30bf\u30ab\u30ca',
         'korean': '\ud55c\uad6d\uc5b4 \uac8c\uc784', 'russian': '\u0412\u0435\u0434\u044c\u043c\u0430\u043a 3: \u0414\u0438\u043a\u0430\u044f \u041e\u0445\u043e\u0442\u0430', 'arabic': '\u0644\u0639\u0628\u0629 \u0639\u0631\u0628\u064a\u0629',
         'thai': '\u0e40\u0e01\u0e21\u0e20\u0e32\u0e29\u0e32\u0e44\u0e17\u0e22', 'emoji and astral plane': 'Game \U0001f3ae \U0001d514\U0001d52b\U0001d526\U0001d520\U0001d52c\U0001d521\U0001d522 \U0001f600', 'accents': '\u00dcn\u00efc\u00f6d\u00e9 \u00c7a va se\u00f1or'}


def items_with(text):
    return [g.AttrDict(id=i, title=t, long_title=t + ' \u2014 long', changelog='<p>' + t + '</p>', genre=t,
                       downloads=[g.AttrDict(name=t + '_setup.exe', desc=t, size=10, md5=None, lang='English', os_type='windows', version='1', updated='x')],
                       galaxyDownloads=[], sharedDownloads=[], extras=[g.AttrDict(name=t + '.pdf', desc=t, size=5, md5=None, updated='x')],
                       folder_name='game_%d' % i, serials=g.AttrDict(key=t)) for i, t in enumerate(text.values())]


class TempDirTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)


class ManifestTests(TempDirTests):
    def test_both_formats_round_trip_every_script(self):
        items = items_with(TEXTS)
        for fmt in ('json', 'legacy'):
            with mock.patch.object(g, 'MANIFEST_FORMAT', fmt):
                g.save_manifest(items, 'm_%s.dat' % fmt)
            self.assertEqual(g.load_manifest('m_%s.dat' % fmt), items, fmt)

    def test_the_characters_are_stored_as_real_utf8_text(self):
        with mock.patch.object(g, 'MANIFEST_FORMAT', 'json'):
            g.save_manifest(items_with(TEXTS))
        with open(g.MANIFEST_FILENAME, 'rb') as f:
            raw = f.read()
        for label, text in TEXTS.items():
            self.assertIn(text.encode('utf-8'), raw, label)      # not \uXXXX escapes: readable in any UTF-8 editor
        raw.decode('utf-8')

    def test_resume_manifest_and_token_style_files_too(self):
        items = items_with(TEXTS) + [g.AttrDict(complete=False, os_list=['windows'], lang_list=['de'], lang_fallback=None, installers='both')]
        g.save_resume_manifest(items)
        self.assertEqual(g.load_resume_manifest(), items)


class ExportTests(TempDirTests):
    def test_export_keeps_every_script_and_excel_can_open_it(self):
        g.save_manifest(items_with(TEXTS))
        g.cmd_export('lib.csv', None, ',')
        with open('lib.csv', 'rb') as f:
            self.assertEqual(f.read(3), b'\xef\xbb\xbf')            # byte order mark: Excel recognises UTF-8
        with open('lib.csv', encoding='utf-8-sig', newline='') as f:
            cells = [c for row in csv.reader(f) for c in row]
        for label, text in TEXTS.items():
            self.assertIn(text, cells, label)


class LogFileTests(TempDirTests):
    def test_the_log_file_is_utf8(self):
        self.assertEqual(g.loggingHandler.encoding, 'utf-8')
        handler = g.logging.FileHandler('test.log', encoding='utf-8')     # same encoding as the real handler, own file
        g.rootLogger.addHandler(handler)
        try:
            for text in TEXTS.values():
                g.info('title: %s', text)
        finally:
            g.rootLogger.removeHandler(handler)
            handler.close()
        with open('test.log', encoding='utf-8') as f:
            content = f.read()
        for text in TEXTS.values():
            self.assertIn(text, content)


class ConsoleTests(unittest.TestCase):
    """Output that is redirected on Windows uses the legacy code page; run the script in a child process to see that."""
    SNIPPET = ("import importlib.util, sys, types\n"
               "sys.modules.setdefault('html5lib', types.ModuleType('html5lib'))\n"
               "spec = importlib.util.spec_from_file_location('g', sys.argv[1]); g = importlib.util.module_from_spec(spec); sys.modules['g'] = g; spec.loader.exec_module(g)\n"
               "g.info('before')\ng.info('title: \\u4e2d\\u6587 \\u65e5\\u672c\\u8a9e \\u0412\\u0435\\u0434\\u044c\\u043c\\u0430\\u043a')\ng.info('after')\nprint('print: \\u5deb\\u5e083')\n")

    def run_child(self, encoding):
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gogrepo_delta.py')
        env = dict(os.environ, PYTHONIOENCODING=encoding)
        return subprocess.run([sys.executable, '-c', self.SNIPPET, script], capture_output=True, env=env, timeout=60, stdin=subprocess.DEVNULL)

    def test_a_legacy_code_page_does_not_break_logging_or_print(self):
        for encoding in ('cp1252', 'ascii', 'latin-1'):
            result = self.run_child(encoding)
            self.assertEqual(result.returncode, 0, (encoding, result.stderr[-300:]))
            self.assertEqual(result.stderr, b'', encoding)             # no "Logging error" traceback
            out = result.stdout.decode(encoding)
            self.assertIn('before', out)
            self.assertIn('after', out)                                 # the lines around the Chinese one are not lost
            self.assertIn('\\u4e2d\\u6587', out)                        # the Chinese title is shown as an escape instead of being dropped
            self.assertIn('print: \\u5deb', out)

    def test_utf8_output_shows_the_real_characters(self):
        result = self.run_child('utf-8')
        self.assertEqual(result.returncode, 0)
        out = result.stdout.decode('utf-8')
        self.assertIn('title: \u4e2d\u6587 \u65e5\u672c\u8a9e \u0412\u0435\u0434\u044c\u043c\u0430\u043a', out)
        self.assertEqual(result.stderr, b'')

    def test_characters_the_code_page_can_show_are_not_escaped(self):
        result = self.run_child('cp1252')
        self.assertEqual(result.returncode, 0)
        script = self.SNIPPET.replace("g.info('before')", "g.info('caf\\u00e9 \\u00fcber')")
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gogrepo_delta.py')
        result = subprocess.run([sys.executable, '-c', script, script_path], capture_output=True, env=dict(os.environ, PYTHONIOENCODING='cp1252'), timeout=60, stdin=subprocess.DEVNULL)
        self.assertIn('caf\u00e9 \u00fcber', result.stdout.decode('cp1252'))


class DownloadTests(unittest.TestCase):
    def test_games_with_chinese_japanese_and_russian_names_download_correctly(self):
        r = rig.run(g, 'unicode_names')
        files = {k: v for k, v in r['tree'].items() if v is not None}
        folder = '\u4e2d\u6587\u6e38\u620f \u0412\u0435\u0434\u044c\u043c\u0430\u043a'
        for relpath in (folder + '/setup_\u5deb\u59083_\u72c2\u730e.exe', folder + '/\u0432\u0435\u0434\u044c\u043c\u0430\u043a_manual_\u65e5\u672c\u8a9e.pdf', 'japanese_game/setup_japan.exe'):
            self.assertIn(relpath, files, relpath)
            self.assertEqual(files[relpath][1], r['served'][os.path.basename(relpath)], relpath)

    def test_info_files_contain_the_real_text(self):
        r = rig.run(g, 'unicode_names')
        self.assertIsNone(r['exc'])
        folder = '\u4e2d\u6587\u6e38\u620f \u0412\u0435\u0434\u044c\u043c\u0430\u043a'
        first = r['info_texts'][folder + '/!info.txt']
        self.assertIn('title.......... ' + folder, first)
        self.assertIn('\u4e2d\u6587\u6e38\u620f\uff1a\u5deb\u5e083 \u2014 \u0412\u0435\u0434\u044c\u043c\u0430\u043a 3', first)          # the long title
        self.assertIn('\u66f4\u65b0\u65e5\u5fd7 \u2714 Caf\u00e9', first)                                                           # the changelog
        self.assertIn('[setup_\u5deb\u59083_\u72c2\u730e.exe]', first)                                                      # the file list
        second = r['info_texts']['japanese_game/!info.txt']
        self.assertIn('\u65e5\u672c\u8a9e\u306e\u30b2\u30fc\u30e0', second)
        self.assertIn('\u30b2\u30fc\u30e0 \ud55c\uad6d\uc5b4 \u0e44\u0e17\u0e22', second)


if __name__ == '__main__':
    unittest.main()
