"""Entry 0.5.92: the command line run (the block under `if __name__ == "__main__"`, executed here from the script's own source, as the other entry point tests do) releases the wakelock only if it was made.
Before, `wakelock = Wakelock()` was inside the try and the finally used the name: if Wakelock() itself failed, the finally raised UnboundLocalError and hid the real error."""
import logging
import os
import unittest

import _bootstrap  # noqa: F401
import gogrepo_delta as g


class FakeWakelock(object):
    made = []

    def __init__(self):
        self.taken = self.released = 0
        FakeWakelock.made.append(self)

    def take_wakelock(self):
        self.taken += 1

    def release_wakelock(self):
        self.released += 1


class Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def texts(self):
        return [r.getMessage() for r in self.records]


SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gogrepo_delta.py')


class CliMainTests(unittest.TestCase):
    def setUp(self):
        FakeWakelock.made = []
        self.handler = Capture()
        g.rootLogger.addHandler(self.handler)
        self.addCleanup(g.rootLogger.removeHandler, self.handler)

    def run_cli(self, main, wakelock=FakeWakelock):
        with open(SCRIPT, encoding='utf-8') as f:
            source = f.read()
        block = source[source.index('if __name__ == "__main__":'):]
        namespace = dict(vars(g), __name__='__main__', main=main, process_argv=lambda argv: [], ensure_config_file=lambda: None, Wakelock=wakelock)
        try:
            exec(compile(block, SCRIPT, 'exec'), namespace)
        except SystemExit as e:
            return e.code
        return None

    def released_once(self):
        self.assertEqual(len(FakeWakelock.made), 1)
        self.assertEqual((FakeWakelock.made[0].taken, FakeWakelock.made[0].released), (1, 1))

    def test_a_run_that_succeeds_releases_the_wakelock_and_says_goodbye(self):
        self.assertIsNone(self.run_cli(lambda args: 0))
        self.released_once()
        self.assertIn('exiting...', self.handler.texts())

    def test_a_run_with_failures_exits_with_their_status_after_releasing(self):
        self.assertEqual(self.run_cli(lambda args: 1), 1)
        self.released_once()

    def test_the_real_error_is_reported_when_the_wakelock_cannot_be_made(self):
        calls = []

        def broken():
            raise RuntimeError('no wakelock here')
        code = self.run_cli(lambda args: calls.append(args) or 0, wakelock=broken)          # an UnboundLocalError instead of SystemExit would pass through here
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])                                           # the command did not run
        self.assertTrue(any('fatal...' in text for text in self.handler.texts()))
        self.assertTrue(any(r.exc_info and 'no wakelock here' in str(r.exc_info[1]) for r in self.handler.records))       # the traceback names the real error

    def test_the_wakelock_is_released_when_taking_it_fails(self):
        class FailingTake(FakeWakelock):
            def take_wakelock(self):
                raise OSError('cannot take it')
        self.assertEqual(self.run_cli(lambda args: 0, wakelock=FailingTake), 1)
        self.assertEqual((len(FakeWakelock.made), FakeWakelock.made[0].released), (1, 1))

    def test_an_error_in_the_command_exits_with_1_and_releases(self):
        def failing(args):
            raise ValueError('boom')
        self.assertEqual(self.run_cli(failing), 1)
        self.released_once()

    def test_ctrl_c_exits_with_1_and_releases(self):
        def interrupted(args):
            raise KeyboardInterrupt()
        self.assertEqual(self.run_cli(interrupted), 1)
        self.released_once()

    def test_a_system_exit_of_the_command_keeps_its_code_and_releases(self):
        def leaving(args):
            raise SystemExit(7)
        self.assertEqual(self.run_cli(leaving), 7)
        self.released_once()


if __name__ == '__main__':
    unittest.main()
