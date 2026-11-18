"""Entry 76: a game whose details cannot be fetched is tried again by the next updates (the resume manifest), but only `resume_retry_count`
times; then it is given up, so that it no longer holds back the update that was asked for. A fake GOG account API (patched `request`)."""
import contextlib
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g


class FakeResponse(object):
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeAccount(object):
    """Games 1000 ... : the ids in `failing` raise a connection error when their details are fetched. `fetched` counts the attempts."""
    def __init__(self, count):
        self.ids = [1000 + i for i in range(count)]
        self.failing = set()
        self.fetched = {}

    def add(self, game_id):
        self.ids.append(game_id)

    def request(self, session, url, args=None, **kwargs):
        if '/gameDetails/' in url:
            game_id = int(url.rsplit('/', 1)[1].split('.')[0])
            self.fetched[game_id] = self.fetched.get(game_id, 0) + 1
            if game_id in self.failing:
                raise g.requests.exceptions.ConnectionError('temporary connection failure')
            return FakeResponse(dict(backgroundImage='', cdKey='', forumLink='', changelog='', releaseTimestamp=1500000000, messages=[],
                                     downloads=[], galaxyDownloads=[], extras=[], dlcs=[]))
        products = [dict(id=i, slug='game_%03d' % (i - 1000), title='Game %d' % (i - 1000), category='RPG', image='//images.test/%d' % i,
                         url='/game/game_%03d' % (i - 1000), rating=40, updates=0) for i in self.ids]
        return FakeResponse(dict(products=products, totalPages=1))


class ResumeRetryTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp(prefix='resumeretry_')
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self.cwd)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.account = FakeAccount(5)
        for p in (mock.patch.object(g, 'request', self.account.request),
                  mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={}))):
            p.start()
            self.addCleanup(p.stop)

    def update(self, resumemode='resume'):
        """One run of a default `update` (skipknown, updateonly, partial): returns the log and the exit status of the run."""
        g.run_report.reset()
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_update(['windows'], ['en'], True, True, True, [], [], False, 'both', resumemode, False, False, False, False, False, False, False)
        output = '\n'.join(logs.output)
        self.assertNotIn('would not read back identically', output)       # the counts must be JSON-safe (text keys), or the format falls back
        return output, g.run_report.exit_status()

    def props(self):
        return g.load_resume_manifest()[-1]

    def pending(self):
        return [item.id for item in g.load_resume_manifest()[:-1]]

    def titles(self):
        return sorted(game.title for game in g.load_manifest())

    # --- the limit
    def test_a_game_is_tried_again_three_times_then_given_up(self):
        self.account.failing = {1002}
        log, status = self.update()                                  # the first try
        self.assertEqual(([1002], {'1002': 1}, False, 1), (self.pending(), self.props()['failure_counts'], self.props()['complete'], status))
        self.assertIn('remain in the resume manifest', log)
        self.assertIn('a game is given up after 3 retries', log)
        for run, count in ((2, 2), (3, 3)):                          # the first and second retry ... the third retry: still pending
            with self.subTest(run=run):
                log, status = self.update()
                self.assertEqual(([1002], {'1002': count}, False, 1), (self.pending(), self.props()['failure_counts'], self.props()['complete'], status))
                self.assertNotIn('giving up', log)
        log, status = self.update()                                  # the fourth failure: first try + 3 retries are used up
        self.assertIn("giving up on 'game_002' (id 1002) for now: its details could not be fetched", log)
        self.assertEqual(([], True, 1), (self.pending(), self.props()['complete'], status))     # the failure is still reported: exit status 1
        self.assertGreater(self.props()['failure_counts']['1002'], 3)
        self.assertEqual(['game_000', 'game_001', 'game_003', 'game_004'], self.titles())

    def test_after_the_give_up_the_game_never_holds_back_an_update_again(self):
        self.account.failing = {1002}
        for _ in range(4):
            self.update()
        self.account.add(1005)                                       # a new game: it is fetched by the very next update
        log, status = self.update()
        self.assertIn('game_005', self.titles())
        self.assertEqual(([], True), (self.pending(), self.props()['complete']))
        self.assertIn('giving up on', log)                           # the bad game is tried once more and reported, not retried
        self.assertEqual(1, status)

    def test_while_retries_remain_the_resume_pass_comes_first_as_before(self):
        self.account.failing = {1002}
        self.update()
        self.account.add(1005)
        self.update()                                                # a resume pass: only the failed game is tried
        self.assertNotIn('game_005', self.titles())
        for _ in range(2):
            self.update()
        self.assertIn('game_005', self.titles())                     # when the game is given up the update that was asked for follows

    def test_the_games_that_work_are_in_the_manifest_from_the_first_run(self):
        self.account.failing = {1002}
        self.update()
        self.assertEqual(['game_000', 'game_001', 'game_003', 'game_004'], self.titles())

    # --- the setting
    def test_the_number_of_retries_is_the_setting(self):
        # runs until the game is given up, and the number of times its details were asked for: the first try, the retries, and (when the
        # resume pass is complete) the update that was asked for, which asks once more
        for retries, runs, attempts in ((0, 1, 1), (1, 2, 3), (5, 6, 7)):
            with self.subTest(retries=retries):
                folder = os.path.join(self.dir, 'retries_%d' % retries)
                os.makedirs(folder)
                os.chdir(folder)
                self.account.failing, self.account.fetched = {1002}, {}
                with mock.patch.object(g, 'RESUME_RETRY_COUNT', retries):
                    for run in range(1, runs + 1):
                        log, _ = self.update()
                        self.assertEqual(run == runs, 'giving up' in log, 'run %d' % run)
                    self.assertEqual(([], True), (self.pending(), self.props()['complete']))
                self.assertEqual(attempts, self.account.fetched[1002])

    def test_zero_retries_gives_a_game_up_at_once_and_still_reports_it(self):
        self.account.failing = {1002}
        with mock.patch.object(g, 'RESUME_RETRY_COUNT', 0):
            log, status = self.update()
        self.assertIn("giving up on 'game_002' (id 1002) for now: its details could not be fetched 1 time in a row", log)
        self.assertEqual(([], True, 1), (self.pending(), self.props()['complete'], status))

    def test_the_message_says_how_many_retries(self):
        self.account.failing = {1002}
        with mock.patch.object(g, 'RESUME_RETRY_COUNT', 1):
            log, _ = self.update()
        self.assertIn('a game is given up after 1 retry)', log)

    def test_the_setting_is_in_the_config_file_with_its_default(self):
        self.assertEqual(3, g.SETTING_VALUES['resume_retry_count'])
        self.assertEqual(3, g.RESUME_RETRY_COUNT)
        text = g.default_config_text(g.build_parser()[1])
        self.assertIn('\nresume_retry_count = 3\n', text)

    # --- counting
    def test_a_game_that_works_again_starts_counting_from_the_beginning(self):
        self.account.failing = {1002}
        self.update()
        self.update()
        self.assertEqual({'1002': 2}, self.props()['failure_counts'])
        self.account.failing = set()
        self.update()
        self.assertEqual(({}, [], True), (self.props()['failure_counts'], self.pending(), self.props()['complete']))
        self.assertIn('game_002', self.titles())

    def test_other_games_are_counted_on_their_own(self):
        self.account.failing = {1001, 1003}
        self.update()
        self.account.failing = {1003}
        self.update()
        self.assertEqual({'1003': 2}, self.props()['failure_counts'])
        self.assertEqual([1003], self.pending())

    def test_the_counts_are_kept_when_the_resume_manifest_is_complete_and_by_noresume(self):
        self.account.failing = {1002}
        self.update()
        self.update(resumemode='noresume')                           # no resume pass, but the count goes on
        self.assertEqual({'1002': 2}, self.props()['failure_counts'])

    def test_an_interrupted_update_adds_no_failure(self):
        self.account.failing = set()

        def interrupt(session, url, args=None, **kwargs):
            if '/gameDetails/1003' in url:
                raise KeyboardInterrupt()
            return self.account.request(session, url, args, **kwargs)
        with mock.patch.object(g, 'request', interrupt), self.assertRaises(KeyboardInterrupt):
            self.update()
        self.assertEqual({}, self.props()['failure_counts'])
        self.assertEqual(sorted([1003, 1004]), sorted(self.pending()))

    def test_a_resume_manifest_of_an_older_version_has_no_counts_and_starts_them(self):
        self.account.failing = {1002}
        self.update()
        items = g.load_resume_manifest()
        del items[-1]['failure_counts']
        g.save_resume_manifest(items)
        self.update()
        self.assertEqual({'1002': 1}, self.props()['failure_counts'])

    def test_every_failed_try_is_in_the_run_summary_and_the_exit_status(self):
        self.account.failing = {1002}
        for _ in range(4):
            g.run_report.reset()
            self.update()
            self.assertEqual(1, g.run_report.exit_status())
            self.assertEqual('game_002', g.run_report.failures[0][0])


if __name__ == '__main__':
    unittest.main()
