"""Entry 80: what the first run of the best-effort job on Python 3.9 showed. The program reads old-format manifests on Python 3.8 and 3.9 (spaces before
an expression were an IndentationError for ast.literal_eval before 3.10), and the tests do not need 3.10 only features (assertNoLogs) or an empty
stderr on a Python that prints the 'older than recommended' warning. These tests run on every Python: the old behaviour is imitated where it differs."""
import ast
import io
import logging
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


if __name__ == '__main__':
    unittest.main()
