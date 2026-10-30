import contextlib
import io
import unittest
import _bootstrap  # noqa: F401
import gogrepo_delta as gogrepoc


def parse(*argv):
    # -nolog keeps process_argv from creating a log file in the current folder
    return gogrepoc.process_argv(['gogrepo_delta.py'] + list(argv) + ['-nolog'])


class CommandLineTests(unittest.TestCase):
    def silent(self):
        return self.assertLogs('gogrepoc', level='ERROR')

    def test_lists_are_collected(self):
        args = parse('update', '-os', 'linux', 'windows', '-lang', 'en', 'de')
        self.assertEqual(args.os, ['linux', 'windows'])
        self.assertEqual(args.lang, ['en', 'de'])

    def test_ids_are_collected_after_the_subcommand(self):
        self.assertEqual(parse('download', 'somedir', '-ids', '1', '2').ids, ['1', '2'])

    def test_every_single_dash_option_also_works_with_two_dashes(self):
        cases = [('update', ['-os', 'linux'], ['--os', 'linux']),
                 ('update', ['-skiphidden', '-full'], ['--skiphidden', '--full']),
                 ('download', ['d', '-dryrun', '-skipextras'], ['d', '--dryrun', '--skipextras']),
                 ('download', ['d', '-ids', '5'], ['d', '--ids', '5']),
                 ('verify', ['d', '-skipmd5', '-delete'], ['d', '--skipmd5', '--delete'])]
        for command, single, double in cases:
            self.assertEqual(vars(parse(command, *single)), vars(parse(command, *double)), (command, single))

    def test_common_flags_are_accepted_by_every_subcommand_in_both_spellings(self):
        for command in ('update', 'download', 'verify', 'clean', 'backup', 'import', 'trash', 'diagnostics', 'login', 'clear_partial_downloads'):
            extra = {'download': ['d'], 'verify': ['d'], 'clean': ['d'], 'backup': ['s', 'd'], 'import': ['s', 'd'], 'trash': ['d'], 'clear_partial_downloads': ['d']}.get(command, [])
            single = gogrepoc.process_argv(['gogrepo_delta.py', command] + extra + ['-nolog', '-debug'])
            double = gogrepoc.process_argv(['gogrepo_delta.py', command] + extra + ['--nolog', '--debug'])
            self.assertTrue(single.nolog and single.debug, command)
            self.assertTrue(double.nolog and double.debug, command)

    def test_unknown_os_and_language_are_rejected(self):
        with self.silent(), self.assertRaises(SystemExit):
            parse('update', '-os', 'beos')
        with self.silent(), self.assertRaises(SystemExit):
            parse('update', '-skiplang', 'xx')

    def test_missing_or_unknown_command_is_rejected(self):
        # argparse prints a usage message to stderr and exits with status 2; capture it so the test output stays clean
        for argv, expected in (([], 'required: command'), (['bogus'], "invalid choice: 'bogus'")):
            captured = io.StringIO()
            with contextlib.redirect_stderr(captured), self.assertRaises(SystemExit) as raised:
                gogrepoc.process_argv(['gogrepo_delta.py'] + argv)
            self.assertEqual(raised.exception.code, 2)
            self.assertIn(expected, captured.getvalue())

    def test_login_password_is_optional(self):
        self.assertIsNone(parse('login', 'someone').password)
        self.assertEqual(parse('login', 'someone', 'secret').password, 'secret')


if __name__ == '__main__':
    unittest.main()
