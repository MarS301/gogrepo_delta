"""Entry 0.5.86: the resume file. Finding A: an old-format resume file was read after a text replacement of every '{' and '}', which also changed
braces inside titles and changelogs. Finding B: a resume file that could not be read or understood was taken for 'nothing to resume', so a damaged
file silently became a fresh update. Now only a missing file means 'no resume file'; anything else stops the run with a message, and nothing is changed."""
import contextlib
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

RESUME = g.RESUME_MANIFEST_FILENAME


def game(i, **extra):
    return g.AttrDict(id=i, title='game_%d' % i, long_title='Game %d' % i, **extra)


def properties(**changes):
    props = dict(complete=False, resume_manifest_syntax_version=g.RESUME_MANIFEST_SYNTAX_VERSION, os_list=['windows'], lang_list=['en'],
                 lang_fallback=None, installers='standalone', strict=False, failure_counts={})
    props.update(changes)
    return g.AttrDict(**props)


class Reached(BaseException):
    """Raised by the fake GOG request: the update got past the resume file."""


class Base(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        self.addCleanup(setattr, g, 'MANIFEST_FORMAT', g.MANIFEST_FORMAT)
        g.run_report.reset('update')

    def write(self, text, name=RESUME, binary=False):
        with open(name, 'wb' if binary else 'w', **({} if binary else dict(encoding='utf-8', newline=''))) as f:
            f.write(text)

    def read(self, name=RESUME):
        with open(name, 'rb') as f:
            return f.read()

    def stops(self, call, *args, **kwargs):
        """Runs `call`, expects the program to stop with exit status 1 and a message; returns the message."""
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
            call(*args, **kwargs)
        self.assertEqual(raised.exception.code, 1)
        return '\n'.join(r.getMessage() for r in logs.records)


class LegacyBracesTests(Base):
    """Finding A."""
    def save_legacy(self, items):
        g.MANIFEST_FORMAT = 'legacy'
        g.save_resume_manifest(items)
        self.assertEqual(self.read()[:1], b'#')                       # really the old format

    def test_braces_in_titles_and_changelogs_survive_an_old_format_resume_file(self):
        items = [game(1, changelog='fixed {a} bug } and { another', folder_name='odd }{ name'),
                 g.AttrDict(id=2, title='a{b}c', long_title='}{', serials='{"x": "})"}', downloads=[], extras=[]),
                 properties()]
        self.save_legacy(items)
        self.assertEqual(g.load_resume_manifest(), items)

    def test_a_resume_file_with_python_2_long_sizes_loads(self):
        self.write("[{'id': 1, 'title': 'a}b', 'size': 5L, 'extras': [{'size': 7L, 'name': '{x}'}]}, {'complete': False}]")
        items = g.load_resume_manifest()
        self.assertEqual((items[0].title, items[0].size, items[0].extras[0].size, items[0].extras[0].name), ('a}b', 5, 7, '{x}'))

    def test_the_text_of_the_file_is_not_run_as_code(self):
        self.write("[__import__('os').getcwd(), {'complete': False}]")
        self.assertIn('damaged', self.stops(g.load_resume_manifest))

    def test_a_json_resume_file_with_braces_loads(self):
        items = [game(1, changelog='fixed {a} bug } and {', folder_name='odd }{ name'), properties()]
        g.MANIFEST_FORMAT = 'json'
        g.save_resume_manifest(items)
        self.assertEqual(g.load_resume_manifest(), items)


class FileLevelTests(Base):
    """Finding B, the file."""
    def test_a_missing_file_means_no_resume_file(self):
        self.assertEqual(g.load_resume_manifest(), [])

    def test_a_truncated_json_file_stops_and_is_not_changed(self):
        g.MANIFEST_FORMAT = 'json'
        g.save_resume_manifest([game(1), game(2), properties()])
        whole = self.read()
        self.write(whole[:len(whole) // 2], binary=True)
        before = self.read()
        message = self.stops(g.load_resume_manifest)
        self.assertIn("The resume file '%s' is damaged" % RESUME, message)
        self.assertIn('delete the file', message)
        self.assertIn('Nothing was changed', message)
        self.assertEqual(self.read(), before)

    def test_the_message_names_the_backup_copy_if_there_is_one(self):
        self.write('{"items": [', )
        self.assertNotIn('.bak', self.stops(g.load_resume_manifest))
        self.write('{}', name=RESUME + g.BACKUP_EXT)
        self.assertIn('copy %s over it' % (RESUME + g.BACKUP_EXT), self.stops(g.load_resume_manifest))

    def test_damaged_files_of_every_kind_stop(self):
        for name, content in (('garbage', 'this is not a resume file ['), ('empty', ''), ('only spaces', '  \n'),
                              ('json without items', '{"games": 1}'), ('json items not a list', '{"items": 5}'), ('json with no items', '{"items": []}'),
                              ('old format, not a list', "{'complete': False}"), ('old format, empty list', '[]'),
                              ('old format, cut off', "[{'id': 1, 'title': 'a"), ('json array', '[1, 2]x'),
                              ('old format, a number', '5'), ('old format, text', "'a resume file'"), ('old format, a tuple', "({'complete': False},)")):
            with self.subTest(name):
                self.write(content)
                before = self.read()
                self.assertIn('damaged', self.stops(g.load_resume_manifest))
                self.assertEqual(self.read(), before)

    def test_a_file_that_is_not_text_stops(self):
        self.write(b'\xff\xfe\x00 not utf-8 \x80', binary=True)
        self.assertIn('cannot be read', self.stops(g.load_resume_manifest))

    def test_a_file_that_cannot_be_opened_is_not_taken_for_no_file(self):
        os.mkdir(RESUME)                                              # a folder where the file should be: open() fails with an OSError
        message = self.stops(g.load_resume_manifest)
        self.assertIn('cannot be read', message)
        self.assertIn('permissions', message)

    def test_a_permission_error_is_not_taken_for_no_file(self):
        with mock.patch('builtins.open', side_effect=PermissionError(13, 'Permission denied')):
            self.assertIn('Permission denied', self.stops(g.load_resume_manifest))


class RecordTests(Base):
    """Finding B, what update relies on."""
    def check(self, *items):
        return g.check_resume_manifest(list(items))

    def test_a_good_record_is_returned(self):
        props = properties(failure_counts={'1000': 2})
        self.assertIs(self.check(game(1), game(2), props), props)

    def test_a_complete_file_needs_no_more_than_complete(self):
        props = g.AttrDict(complete=True, resume_manifest_syntax_version=g.RESUME_MANIFEST_SYNTAX_VERSION)
        self.assertIs(self.check(props), props)

    def test_an_old_version_is_left_to_the_question_about_it(self):
        for props in (g.AttrDict(complete=False), g.AttrDict(complete=False, resume_manifest_syntax_version=0), g.AttrDict()):
            self.assertIs(self.check(game(1), props), props)

    def test_the_last_entry_must_be_the_record(self):
        for last in ('text', 5, ['a'], None):
            with self.subTest(last=last):
                self.assertIn('properties record', self.stops(self.check, game(1), last))

    def test_every_game_entry_must_be_a_record(self):
        self.assertIn('not a record', self.stops(self.check, game(1), 'oops', properties()))

    def test_failure_counts_must_be_a_table_of_ids_and_counts(self):
        for bad in (['1000'], 'many', 5, {'1000': 'twice'}, {'1000': -1}, {'1000': True}, {'1000': 1.5}, {1000: 1}, {'1000': None}):
            with self.subTest(bad=bad):
                message = self.stops(self.check, game(1), properties(failure_counts=bad))
                self.assertIn('failure_counts', message)

    def test_no_failure_counts_is_fine(self):
        props = properties()
        del props['failure_counts']
        self.assertIs(self.check(game(1), props), props)
        self.assertIsNotNone(self.check(game(1), properties(failure_counts=None)))

    def test_complete_must_be_yes_or_no(self):
        for bad in ('no', 0, 1, [], {}):
            with self.subTest(bad=bad):
                self.assertIn("'complete'", self.stops(self.check, game(1), properties(complete=bad)))

    def test_an_incomplete_file_must_have_what_resuming_needs(self):
        for key, bad in (('os_list', None), ('os_list', 'windows'), ('lang_list', 5), ('installers', ['standalone']), ('strict', 'no'), ('strict', None)):
            with self.subTest(key=key, bad=bad):
                self.assertIn("'%s'" % key, self.stops(self.check, game(1), properties(**{key: bad})))
        for key in ('os_list', 'lang_list', 'installers', 'strict'):
            with self.subTest(missing=key):
                props = properties()
                del props[key]
                self.assertIn("'%s'" % key, self.stops(self.check, game(1), props))

    def test_a_file_of_this_version_must_say_whether_it_is_complete(self):
        props = properties()
        del props['complete']
        self.assertIn("'complete' is missing", self.stops(self.check, game(1), props))

    def test_a_game_less_file_with_only_the_record_is_fine(self):
        props = properties()
        self.assertIs(self.check(props), props)


class UpdateTests(Base):
    """Finding B in the update command: what it does with the resume file."""
    def update(self, resumemode='resume', request=None):
        calls = []

        def fake_request(session, url, args=None, **kwargs):
            calls.append(url)
            raise Reached()
        with mock.patch.object(g, 'request', request or fake_request), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})):
            try:
                g.cmd_update(['windows'], ['en'], False, False, False, [], [], False, 'both', resumemode, False, False, False, False, False, False, False)
            finally:
                self.calls = calls

    def save_resume(self, *items, **kwargs):
        g.MANIFEST_FORMAT = kwargs.get('format', 'json')
        g.save_resume_manifest(list(items))

    def test_without_a_resume_file_the_update_starts_normally(self):
        with self.assertRaises(Reached):
            self.update()
        self.assertEqual(len(self.calls), 1)

    def test_a_damaged_resume_file_stops_the_update_before_anything_is_fetched(self):
        self.write('{"items": [')
        before = self.read()
        message = self.stops(self.update)
        self.assertIn('damaged', message)
        self.assertEqual(self.calls, [])                              # nothing was requested
        self.assertEqual(self.read(), before)                         # nothing was changed
        self.assertFalse(os.path.exists(g.MANIFEST_FILENAME))

    def test_resumemode_noresume_does_not_hide_a_damaged_file_either(self):
        self.write('garbage')
        self.assertIn('damaged', self.stops(self.update, resumemode='noresume'))
        self.assertEqual(self.calls, [])

    def test_wrong_typed_failure_counts_stop_the_update(self):
        self.save_resume(game(1), properties(failure_counts=['1']))
        self.assertIn('failure_counts', self.stops(self.update))
        self.assertEqual(self.calls, [])

    def test_a_record_without_what_resuming_needs_stops_the_update(self):
        props = properties()
        del props['os_list']
        self.save_resume(game(1), props)
        self.assertIn("'os_list'", self.stops(self.update))
        self.assertEqual(self.calls, [])

    def test_a_complete_resume_file_does_not_resume_and_is_fine(self):
        self.save_resume(game(1), properties(complete=True))
        with self.assertRaises(Reached):
            self.update()
        self.assertEqual(len(self.calls), 1)

    def test_an_incomplete_resume_file_is_resumed(self):
        self.save_resume(game(1000, folder_name='game_1000'), properties(failure_counts={'1000': 1}))
        with self.assertRaises(Reached):
            self.update()
        self.assertIn('/gameDetails/1000', self.calls[0])             # the resume pass asks for the pending game first

    def test_an_old_format_resume_file_with_braces_is_resumed(self):
        self.save_resume(game(1000, changelog='{x} }', folder_name='game_1000'), properties(), format='legacy')
        with self.assertRaises(Reached):
            self.update()
        self.assertIn('/gameDetails/1000', self.calls[0])


class IncompatibleVersionTests(Base):
    """The question about a resume file of another version no longer relies on input() failing."""
    def make(self, complete=False):
        g.MANIFEST_FORMAT = 'json'
        props = properties(complete=complete)
        props['resume_manifest_syntax_version'] = 0
        g.save_resume_manifest([game(1000, folder_name='game_1000'), props])

    def run_update(self, answers=None, error=None):
        update = UpdateTests('test_without_a_resume_file_the_update_starts_normally')
        update.dir = self.dir
        replies = iter(answers or [])

        def fake_input(prompt=''):
            if error is not None:
                raise error
            return next(replies)
        with mock.patch('builtins.input', fake_input):
            return update.update(), update

    def test_without_a_terminal_the_update_stops_with_a_message(self):
        self.make()
        before = self.read()
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
            self.run_update(error=EOFError())
        self.assertEqual(raised.exception.code, 1)
        text = '\n'.join(r.getMessage() for r in logs.records)
        self.assertIn('incompatible version', text)
        self.assertIn('no terminal', text)
        self.assertEqual(self.read(), before)

    def test_answering_d_discards_the_file_and_goes_on(self):
        self.make()
        with self.assertRaises(Reached):
            self.run_update(answers=['x', 'D'])                      # a wrong answer is asked again

    def test_answering_a_aborts_and_changes_nothing(self):
        self.make()
        before = self.read()
        with self.assertRaises(SystemExit):
            self.run_update(answers=['a'])
        self.assertEqual(self.read(), before)

    def test_a_complete_file_of_another_version_is_discarded_without_asking(self):
        self.make(complete=True)
        with self.assertRaises(Reached):
            self.run_update(error=AssertionError('asked'))


if __name__ == '__main__':
    unittest.main()
