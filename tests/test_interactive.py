"""Is a person there to answer a question? (_stdin_is_interactive)

On Windows, sys.stdin.isatty() is also true for the NUL device, so the script asks the console API as well. The real API
can only be called on Windows; here its answer is replaced (and, separately, the way it is called is checked with a
stand-in for the Windows libraries). The real thing is covered by test_run_summary, which starts the script with no input."""
import ctypes
import sys
import types
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g


class FakeStdin(object):
    def __init__(self, tty, fileno=7):
        self.tty, self._fileno = tty, fileno

    def isatty(self):
        return self.tty

    def fileno(self):
        return self._fileno


def interactive(stdin, os_name, console=None):
    """The answer of the real _stdin_is_interactive (the test bootstrap replaces the one in the module by a stub that says no)
    for a pretend stdin on a pretend operating system. `console` stands in for the Windows console check; it is a mock, so
    the tests can see whether and how it was asked."""
    console = console if console is not None else mock.Mock(return_value=True)
    with mock.patch.object(sys, 'stdin', stdin), mock.patch.object(g.os, 'name', os_name), \
            mock.patch.object(g, '_windows_console_input', console):
        result = g._real_stdin_is_interactive()
    interactive.console = console
    return result


class DecisionTests(unittest.TestCase):
    def test_a_terminal_on_linux_or_mac_is_interactive(self):
        self.assertTrue(interactive(FakeStdin(True), 'posix'))

    def test_no_terminal_on_linux_or_mac_is_not(self):
        self.assertFalse(interactive(FakeStdin(False), 'posix'))

    def test_a_missing_stdin_is_not_interactive(self):
        self.assertFalse(interactive(None, 'posix'))
        self.assertFalse(interactive(None, 'nt'))

    def test_a_stdin_that_cannot_be_asked_is_not_interactive(self):
        class Broken(object):
            def isatty(self):
                raise ValueError('I/O operation on closed file')
        self.assertFalse(interactive(Broken(), 'posix'))
        self.assertFalse(interactive(Broken(), 'nt'))

    def test_on_windows_a_real_console_is_interactive(self):
        console = mock.Mock(return_value=True)
        self.assertTrue(interactive(FakeStdin(True, fileno=5), 'nt', console))
        console.assert_called_once_with(5)

    def test_on_windows_nul_looks_like_a_terminal_but_is_not_interactive(self):
        # isatty() says yes for NUL; the console check says no
        self.assertFalse(interactive(FakeStdin(True), 'nt', mock.Mock(return_value=False)))

    def test_on_windows_a_failing_console_check_means_not_interactive(self):
        self.assertFalse(interactive(FakeStdin(True), 'nt', mock.Mock(side_effect=OSError('bad handle'))))

    def test_on_windows_without_isatty_the_console_is_not_asked(self):
        self.assertFalse(interactive(FakeStdin(False), 'nt'))
        interactive.console.assert_not_called()

    def test_the_console_is_not_asked_on_other_systems(self):
        self.assertTrue(interactive(FakeStdin(True), 'posix'))
        interactive.console.assert_not_called()


class ConsoleCallTests(unittest.TestCase):
    """How _windows_console_input uses the Windows libraries, with stand-ins for them (the real ones only exist on Windows)."""

    def run_with(self, console_mode_result):
        calls = {}

        def get_console_mode(handle, mode_pointer):
            calls['handle'] = handle
            calls['pointer_given'] = mode_pointer is not None
            return console_mode_result

        kernel32 = types.SimpleNamespace(GetConsoleMode=get_console_mode)
        fake_msvcrt = types.SimpleNamespace(get_osfhandle=lambda fd: 1000 + fd)
        with mock.patch.dict(sys.modules, {'msvcrt': fake_msvcrt}), \
                mock.patch.object(ctypes, 'WinDLL', lambda name, use_last_error=False: kernel32, create=True):
            return g._windows_console_input(3), calls

    def test_asks_the_console_mode_of_the_handle_belonging_to_the_descriptor(self):
        result, calls = self.run_with(1)
        self.assertTrue(result)
        self.assertEqual(calls['handle'], 1003)
        self.assertTrue(calls['pointer_given'])

    def test_a_failing_call_means_no_console(self):
        result, calls = self.run_with(0)         # GetConsoleMode returns 0 (false) for NUL, files and pipes
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
