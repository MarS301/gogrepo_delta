"""Entry 0.5.67: the download messages name games and movies, the progress lines say what their numbers are, two typos of the error messages
are gone, and the dead code that was not worth reviving stays removed."""
import contextlib
import os
import threading
import unittest
from types import SimpleNamespace

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_clean_target import game


class ProgressTests(unittest.TestCase):
    def job(self, rates, sizes):
        return SimpleNamespace(lock=threading.Lock(), rates=rates, sizes=sizes)

    def report(self, job):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g._report_progress(job)
        return [r.getMessage() for r in logs.records]

    def test_a_line_says_what_is_left_the_speed_and_the_connections(self):
        path = os.path.join('lib', 'movie-movie', 'movie.mp4')
        lines = self.report(self.job({path: [(1, (2 * 1024 ** 2, 1.0))]}, {path: 1024 ** 2 * 1072}))
        self.assertEqual(len(lines), 2)
        self.assertIn('1072.0MB left', lines[0])
        self.assertIn('2.0MB/s', lines[0])
        self.assertIn(' 1 connection ', lines[0])
        self.assertNotIn('connections', lines[0])
        self.assertTrue(lines[0].endswith('movie-movie/movie.mp4'))
        self.assertTrue(lines[1].endswith('remaining in total'))

    def test_several_connections_are_plural(self):
        path = os.path.join('lib', 'g', 'f.bin')
        lines = self.report(self.job({path: [(1, (1024 ** 2, 1.0)), (2, (1024 ** 2, 1.0))]}, {path: 1024 ** 2}))
        self.assertIn(' 2 connections ', lines[0])
        self.assertIn('2.0MB/s', lines[0])

    def test_the_file_names_line_up_for_one_and_for_several_connections(self):
        one, many = os.path.join('lib', 'g', 'one.bin'), os.path.join('lib', 'g', 'many.bin')
        lines = self.report(self.job({one: [(1, (1024 ** 2, 1.0))], many: [(1, (1024 ** 2, 1.0)), (2, (1024 ** 2, 1.0))]},
                                     {one: 1024 ** 2, many: 1024 ** 2}))
        self.assertEqual(lines[0].index('g/many.bin'), lines[1].index('g/one.bin'))

    def test_the_old_cryptic_form_is_gone(self):
        path = os.path.join('lib', 'g', 'f.bin')
        lines = self.report(self.job({path: [(1, (1024 ** 2, 1.0))]}, {path: 1024 ** 2}))
        self.assertNotRegex(lines[0], r'\dx ')

    def test_the_total_is_summed_over_all_files_and_the_rates_are_cleared(self):
        a, b = os.path.join('lib', 'g', 'a.bin'), os.path.join('lib', 'g', 'b.bin')
        job = self.job({a: [(1, (1024 ** 2, 1.0))], b: [(1, (1024 ** 2, 1.0))]}, {a: 1024 ** 3, b: 1024 ** 3})
        lines = self.report(job)
        self.assertIn('2.00GB remaining in total', lines[-1])
        self.assertEqual(job.rates, {})

    def test_nothing_is_printed_when_nothing_moved(self):
        with self.assertRaises(AssertionError):                       # assertLogs: no log line at all
            self.report(self.job({}, {}))


class SelectionMessageTests(unittest.TestCase):
    def setUp(self):
        self.items = [game('alpha'), game('beta')]

    def select(self, items, ids=(), skipids=()):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            try:
                chosen = g._select_download_items(items, list(ids), list(skipids), [])
            except SystemExit as e:
                chosen = e
        return chosen, [(r.levelname, r.getMessage()) for r in logs.records]

    def test_the_announcements_do_not_say_games_only(self):
        chosen, log = self.select(self.items, ids=['alpha'], skipids=['beta'])
        messages = [m for level, m in log]
        self.assertIn('downloading id(s)/title(s): {alpha}', messages)
        self.assertIn('skipping id(s)/title(s): {beta}', messages)
        self.assertEqual([i.title for i in chosen], ['alpha'])

    def errors(self, log):
        return [m for level, m in log if level == 'ERROR']

    def test_ids_that_match_nothing(self):
        chosen, log = self.select(self.items, ids=['zzzz'])
        self.assertIsInstance(chosen, SystemExit)
        self.assertIn('no game or movie with id in "[\'zzzz\']" was found.', self.errors(log))

    def test_ids_and_skipids_that_leave_nothing_have_a_space_and_one_found(self):
        chosen, log = self.select(self.items, ids=['alpha'], skipids=['alpha'])
        error = [m for m in self.errors(log) if m.startswith('no game or movie')][0]
        self.assertEqual(error, 'no game or movie with id(s) in "[\'alpha\']" was found after skipping the ones with id(s) in "[\'alpha\']".')
        self.assertNotIn('foundafter', error)

    def test_skipids_that_remove_everything(self):
        chosen, log = self.select([game('alpha')], skipids=['alpha'])
        error = [m for m in self.errors(log) if m.startswith('no game or movie')][0]
        self.assertEqual(error, 'no game or movie was found after skipping the ones with id(s) in "[\'alpha\']".')
        self.assertEqual(error.count('was found'), 1)

    def test_an_empty_manifest(self):
        with self.assertLogs('gogrepoc', level='INFO') as logs, self.assertRaises(SystemExit):
            g._select_download_items([], [], [], [])
        self.assertIn('no game or movie found', [r.getMessage() for r in logs.records])

    def test_the_update_messages_say_id_not_game_id(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gogrepo_delta.py'), encoding='utf-8') as f:
            source = f.read()
        self.assertNotIn('game id(s)', source)


class RemovedCodeTests(unittest.TestCase):
    """Code that nothing used and that was judged not worth reviving (0.5.67). If one of these comes back on purpose, change this test."""
    def test_the_dead_code_is_gone(self):
        for name in ('update_self', 'save_config_file', 'load_config_file', 'CONFIG_FILENAME', 'input_timeout', 'MANIFEST_SYNTAX_VERSION',
                     'purge_md5_chunkdata', 'signal'):
            self.assertFalse(hasattr(g, name), name)

    def test_what_looks_similar_but_is_used_stays(self):
        for name in ('RESUME_MANIFEST_SYNTAX_VERSION', 'USER_CONFIG_FILENAME', 'REPO_HOME_URL', 'NEW_RELEASE_URL', 'GOG_MEDIA_TYPE_MOVIE',
                     'makeGitHubSession', 'cmd_selfupdate'):
            self.assertTrue(hasattr(g, name), name)

    def test_the_legacy_readers_that_are_still_needed_stay(self):
        self.assertTrue(hasattr(g, '_load_legacy_literal'))
        self.assertTrue(hasattr(g, 'open_notrunc'))


if __name__ == '__main__':
    unittest.main()
