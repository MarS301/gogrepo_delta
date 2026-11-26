"""Entry 80: what the first run of the best-effort job on Python 3.9 showed. The program reads old-format manifests on Python 3.8 and 3.9 (spaces before
an expression were an IndentationError for ast.literal_eval before 3.10), and the tests do not need 3.10 only features (assertNoLogs) or an empty
stderr on a Python that prints the 'older than recommended' warning. These tests run on every Python: the old behaviour is imitated where it differs."""
import ast
import glob
import io
import logging
import os
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

REAL_LITERAL_EVAL = ast.literal_eval


def literal_eval_before_3_10(text, *args, **kwargs):
    """ast.literal_eval as it was before Python 3.10: text that starts with spaces or tabs is an IndentationError."""
    if isinstance(text, str) and text[:1] in (' ', '\t'):
        raise IndentationError('unexpected indent')
    return REAL_LITERAL_EVAL(text, *args, **kwargs)


class LegacyLiteralTests(unittest.TestCase):
    def load(self, text):
        with mock.patch.object(g.ast, 'literal_eval', literal_eval_before_3_10):
            return g._load_legacy_literal(text)

    def test_the_imitation_really_refuses_leading_spaces(self):
        with self.assertRaises(IndentationError):
            literal_eval_before_3_10('   {}')
        self.assertEqual({}, literal_eval_before_3_10('{}  '))

    def test_a_wrapped_dictionary_loads_as_before_3_10(self):
        # the text of the failing test of the CI run: `AttrDict(**` is removed and leaves spaces in front
        loaded = self.load("AttrDict(**{'outer': AttrDict(**{'value': 7}), 'rows': [{'x': 1}], 'text': 'keep }) exactly'})")
        self.assertEqual(7, loaded.outer.value)
        self.assertEqual([{'x': 1}], loaded.rows)
        self.assertEqual('keep }) exactly', loaded.text)
        self.assertIsInstance(loaded, g.AttrDict)
        self.assertIsInstance(loaded.outer, g.AttrDict)

    def test_a_list_of_wrapped_items_loads(self):
        loaded = self.load("[AttrDict(**{'id': 1}), AttrDict(**{'id': 2})]")
        self.assertEqual([1, 2], [item.id for item in loaded])

    def test_text_that_already_starts_with_spaces_or_a_newline_loads(self):
        self.assertEqual({'a': 1}, dict(self.load("   {'a': 1}  ")))
        self.assertEqual({'a': 1}, dict(self.load("\t{'a': 1}\n")))

    def test_text_that_is_not_a_literal_is_still_refused(self):
        for text in ("__import__('os').system('echo x')", "AttrDict(**{'a': 1}).__class__", "{'a': open('x')}"):
            with self.subTest(text=text), self.assertRaises((ValueError, SyntaxError)):
                self.load(text)

    def test_the_same_result_on_this_python(self):
        text = "AttrDict(**{'outer': AttrDict(**{'value': 7}), 'rows': [{'x': 1}], 'text': 'keep }) exactly'})"
        self.assertEqual(g._load_legacy_literal(text), self.load(text))


class AssertNoLogsTests(unittest.TestCase):
    """The stand-in for TestCase.assertNoLogs of Python 3.10, used on 3.8 and 3.9 (tested on every version)."""
    def setUp(self):
        self.logger = logging.getLogger('assert_no_logs_test')
        self.logger.setLevel(logging.WARNING)
        self.logger.propagate = True

    def watch(self, level='INFO'):
        return _bootstrap._assert_no_logs(self, 'assert_no_logs_test', level)

    def test_nothing_logged_passes(self):
        with self.watch():
            pass

    def test_a_record_at_or_above_the_level_fails(self):
        for log in (self.logger.info, self.logger.warning, self.logger.error):
            with self.subTest(log=log.__name__), self.assertRaises(AssertionError) as raised:
                with self.watch():
                    log('something happened')
            self.assertIn('something happened', str(raised.exception))

    def test_a_record_below_the_level_is_ignored(self):
        with self.watch('WARNING'):
            self.logger.info('too quiet to count')
            self.logger.debug('and this')

    def test_it_accepts_a_numeric_level_and_a_logger_object(self):
        with self.assertRaises(AssertionError):
            with _bootstrap._assert_no_logs(self, self.logger, logging.ERROR):
                self.logger.error('numeric')

    def test_it_puts_the_logger_back_as_it_was(self):
        before = (self.logger.level, self.logger.propagate, list(self.logger.handlers))
        with self.watch('DEBUG'):
            pass
        with self.assertRaises(AssertionError):
            with self.watch('DEBUG'):
                self.logger.debug('x')
        self.assertEqual(before, (self.logger.level, self.logger.propagate, list(self.logger.handlers)))

    def test_the_stand_in_is_installed_only_where_the_real_one_is_missing(self):
        self.assertTrue(hasattr(unittest.TestCase, 'assertNoLogs'))
        if _bootstrap._assert_no_logs is not unittest.TestCase.assertNoLogs:
            self.skipTest('this Python has the real assertNoLogs')
        self.assertIs(_bootstrap._assert_no_logs, unittest.TestCase.assertNoLogs)


class OlderPythonWarningTests(unittest.TestCase):
    def warning_of(self, version):
        stream = io.StringIO()
        g.check_python_version(version, stream)
        return stream.getvalue().encode('utf-8')

    def test_the_helper_removes_the_warning_the_program_really_prints(self):
        for version in ((3, 9, 25), (3, 8, 20)):
            with self.subTest(version=version):
                text = self.warning_of(version)
                self.assertTrue(text.startswith(b'Warning: Python '))
                self.assertEqual(b'', _bootstrap.without_old_python_warning(text))

    def test_other_output_is_kept(self):
        text = b'Logging error\nTraceback (most recent call last):\nWarning: something else\n'
        self.assertEqual(text, _bootstrap.without_old_python_warning(text))
        mixed = self.warning_of((3, 9, 1)) + text
        self.assertEqual(text, _bootstrap.without_old_python_warning(mixed))
        self.assertEqual(b'', _bootstrap.without_old_python_warning(b''))

    def test_a_current_python_prints_no_warning(self):
        self.assertEqual(b'', self.warning_of((3, 10, 0)))


class NoNewerPythonFeaturesTests(unittest.TestCase):
    """The README promises that Python 3.8 and 3.9 start (best effort). A static check of the program and the tests for what those versions
    do not have: 81 tests failed on Python 3.8 because of one call of random.Random.randbytes (3.9), which no test on a newer Python noticed."""
    ATTRIBUTES = {'randbytes': '3.9', 'removeprefix': '3.9', 'removesuffix': '3.9', 'bit_count': '3.10', 'lcm': '3.9', 'pairwise': '3.10',
                  'unparse': '3.9', 'is_relative_to': '3.9', 'with_stem': '3.9', 'readlink': '3.9', 'to_thread': '3.9',
                  'stdlib_module_names': '3.10', 'orig_argv': '3.10', 'file_digest': '3.11', 'add_note': '3.11'}
    KEYWORDS = {'root_dir': '3.10', 'ignore_cleanup_errors': '3.10', 'onexc': '3.12', 'process_group': '3.11'}
    MODULES = {'zoneinfo': '3.9', 'graphlib': '3.9', 'tomllib': '3.11'}
    # each use that is guarded: by skipUnless(sys.version_info >= (3, 10)), by `if sys.version_info >= (3, 12)` (onerror is used before), by hasattr
    ALLOWED = {('tests/test_repo_files.py', 'stdlib_module_names'), ('gogrepo_delta.py', 'onexc'), ('tests/test_old_python_support.py', 'randbytes')}

    def files(self):
        root = _bootstrap.ROOT
        paths = [os.path.join(root, 'gogrepo_delta.py')] + sorted(glob.glob(os.path.join(root, 'tests', '**', '*.py'), recursive=True))
        return [(os.path.relpath(p, root).replace(os.sep, '/'), p) for p in paths]

    def problems(self, relative, source):
        found = []
        tree = ast.parse(source, feature_version=(3, 8))               # syntax that 3.8 does not know (match, ...) is a SyntaxError
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                version = self.ATTRIBUTES.get(node.attr)
                if version and (relative, node.attr) not in self.ALLOWED:
                    found.append('%s:%d .%s needs Python %s' % (relative, node.lineno, node.attr, version))
                if node.attr == 'cache' and isinstance(node.value, ast.Name) and node.value.id == 'functools':
                    found.append('%s:%d functools.cache needs Python 3.9' % (relative, node.lineno))
            elif isinstance(node, ast.keyword) and node.arg in self.KEYWORDS and (relative, node.arg) not in self.ALLOWED:
                found.append('%s:%d %s= needs Python %s' % (relative, node.value.lineno, node.arg, self.KEYWORDS[node.arg]))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'zip' and any(k.arg == 'strict' for k in node.keywords):
                found.append('%s:%d zip(strict=) needs Python 3.10' % (relative, node.lineno))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
                for name in names:
                    if name.split('.')[0] in self.MODULES:
                        found.append('%s:%d import %s needs Python %s' % (relative, node.lineno, name, self.MODULES[name.split('.')[0]]))
        return found

    def test_the_program_and_the_tests_use_nothing_newer_than_python_3_8(self):
        found = []
        for relative, path in self.files():
            with open(path, encoding='utf-8') as r:
                found += self.problems(relative, r.read())
        self.assertEqual([], found)

    def test_the_check_finds_what_it_looks_for(self):
        source = ('import random, zoneinfo\nimport functools\nx = random.Random(1).randbytes(4)\ny = "a".removeprefix("a")\n'
                  'z = list(zip([1], [2], strict=True))\nimport glob\nglob.glob("*", root_dir=".")\n@functools.cache\ndef f(): pass\n')
        found = self.problems('x.py', source)
        for expected in ('randbytes', 'removeprefix', 'zip(strict=)', 'root_dir=', 'functools.cache', 'import zoneinfo'):
            self.assertTrue(any(expected in line for line in found), (expected, found))

    def test_the_check_ignores_comments_strings_and_the_allowed_use(self):
        source = '# glob.glob(root_dir=...) and randbytes are named here\ntext = "x.randbytes(3)"\nok = [1].count(1)\n'
        self.assertEqual([], self.problems('x.py', source))
        self.assertEqual([], self.problems('tests/test_repo_files.py', 'import sys\nsys.stdlib_module_names\n'))
        self.assertEqual(1, len(self.problems('tests/other.py', 'import sys\nsys.stdlib_module_names\n')))

    def test_syntax_newer_than_python_3_8_is_found(self):
        with self.assertRaises(SyntaxError):
            self.problems('x.py', 'match 1:\n    case 1:\n        pass\n')


class RigTests(unittest.TestCase):
    def test_the_rig_blob_is_what_randbytes_returns(self):
        import random
        import sys
        sys.path.insert(0, os.path.join(_bootstrap.ROOT, 'tests', 'download_rig'))
        try:
            import rig
        finally:
            sys.path.pop(0)
        for seed in (0, 1, 'abc', 99999):
            for size in (0, 1, 7, 4096, 1000003):
                expected = random.Random(seed).randbytes(size) if hasattr(random.Random, 'randbytes') else None
                actual = rig.blob(seed, size)
                self.assertEqual(size, len(actual))
                if expected is not None:
                    self.assertEqual(expected, actual)
        self.assertNotEqual(rig.blob(1, 64), rig.blob(2, 64))
        self.assertEqual(rig.blob(5, 64), rig.blob(5, 64))

    def test_the_rig_blob_of_size_zero_does_not_need_getrandbits_of_zero_bits(self):
        # Random.getrandbits(0) raised ValueError on older Pythons
        import random
        import sys
        sys.path.insert(0, os.path.join(_bootstrap.ROOT, 'tests', 'download_rig'))
        try:
            import rig
        finally:
            sys.path.pop(0)

        class OldRandom(random.Random):
            def getrandbits(self, k):
                if k == 0:
                    raise ValueError('number of bits must be greater than zero')
                return super().getrandbits(k)
        with mock.patch.object(rig.random, 'Random', OldRandom):
            self.assertEqual(b'', rig.blob(3, 0))
            self.assertEqual(8, len(rig.blob(3, 8)))

    def test_a_scenario_that_fails_leaves_the_working_folder_as_it_was(self):
        import sys
        sys.path.insert(0, os.path.join(_bootstrap.ROOT, 'tests', 'download_rig'))
        try:
            import rig
        finally:
            sys.path.pop(0)
        before = os.getcwd()
        with self.assertRaises(KeyError):
            rig.run(g, 'there_is_no_such_scenario')
        self.assertEqual(before, os.getcwd())

    def test_a_scenario_that_fails_early_leaves_no_folder_behind(self):
        import glob
        import sys
        import tempfile
        sys.path.insert(0, os.path.join(_bootstrap.ROOT, 'tests', 'download_rig'))
        try:
            import rig
        finally:
            sys.path.pop(0)
        real_server = rig.Server                   # rig.Server is replaced below, so the fake must not look it up again

        class Recording(real_server):
            made = []

            def __init__(self):
                real_server.__init__(self)
                self.stopped = False
                Recording.made.append(self)

            def stop(self):
                self.stopped = True
                real_server.stop(self)

        pattern = os.path.join(tempfile.gettempdir(), 'rig_*')
        before = set(glob.glob(pattern))
        with mock.patch.object(rig, 'Server', Recording):
            with self.assertRaises(KeyError):
                rig.run(g, 'there_is_no_such_scenario')
        self.assertEqual(set(glob.glob(pattern)) - before, set())
        self.assertEqual([server.stopped for server in Recording.made], [True])           # the fake server of the scenario is stopped too

if __name__ == '__main__':
    unittest.main()
