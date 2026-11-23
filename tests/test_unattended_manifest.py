"""Entry 81: runs that nobody watches (scheduled tasks). A command that needs the manifest stops when there is none (it used to carry on with an empty
list, do nothing and end with exit status 0, e.g. when the task starts in the wrong folder), and -usebackup uses gog-manifest.dat.bak without asking
when the manifest is missing or damaged (a run that cannot ask used to stop)."""
import builtins
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_manifest_format import sample_items

MANIFEST, BACKUP = g.MANIFEST_FILENAME, g.MANIFEST_FILENAME + g.BACKUP_EXT
NEEDING = ('download', 'verify', 'import', 'backup', 'list', 'export', 'diagnostics')
FUNCTIONS_NEEDING = ('apply_tag_options', 'cmd_download', 'cmd_verify', 'cmd_import', 'cmd_backup', 'cmd_list', 'cmd_export', 'cmd_output_diagnostic_data')
FUNCTIONS_NOT_NEEDING = ('cmd_update', 'cmd_clean', 'cmd_clean_stages', 'cmd_wishlist')


class UnattendedTestCase(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp(prefix='unattended_')
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        self.addCleanup(setattr, g, 'MANIFEST_USE_BACKUP', g.MANIFEST_USE_BACKUP)
        g.MANIFEST_USE_BACKUP = False
        g.run_report.reset()
        patch = mock.patch.object(g, '_stdin_is_interactive', return_value=False)       # a scheduled task: nobody to ask
        self.not_interactive = patch.start()
        self.addCleanup(patch.stop)

    def text(self, path):
        with open(path, encoding='utf-8') as f:
            return f.read()

    def make_manifest_with_backup(self, old=2, new=4):
        g.save_manifest(sample_items(old))
        g.save_manifest(sample_items(new))                  # the second save leaves the first version as the backup

    def load_logged(self, command=None, require_existing=False):
        g.run_report.reset(command)
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            try:
                result = g.load_manifest(require_existing=require_existing)
            except SystemExit as e:
                result = e
            g.info('end of test')
        return result, '\n'.join(logs.output)


class MissingManifestTests(UnattendedTestCase):
    def test_a_manifest_that_is_required_and_missing_stops_the_run(self):
        for command in NEEDING:
            with self.subTest(command=command):
                result, log = self.load_logged(command, require_existing=True)
                self.assertIsInstance(result, SystemExit)
                self.assertEqual(1, result.code)
                self.assertIn(os.path.abspath(MANIFEST), log)
                self.assertIn("the manifest is read from the current folder, '%s'" % os.getcwd(), log)
                self.assertIn("'%s' needs it, so nothing was done" % command, log)
                self.assertIn("run 'update' first", log)
                self.assertEqual([], os.listdir(self.dir))        # and nothing was created

    def test_the_message_without_a_known_command_says_this_command(self):
        result, log = self.load_logged(None, require_existing=True)
        self.assertIsInstance(result, SystemExit)
        self.assertIn("'this command' needs it", log)

    def test_without_the_requirement_a_missing_manifest_is_the_first_run_whatever_the_command(self):
        # update, clean and wishlist do not ask for it; and a stale command name (as a test of another module may leave) changes nothing
        for command in ('update', 'clean', 'wishlist', 'login', 'download', None):
            with self.subTest(command=command):
                result, _ = self.load_logged(command)
                self.assertEqual([], result)

    def test_a_manifest_that_exists_but_lists_no_games_is_not_a_missing_one(self):
        g.save_manifest([])
        for command in NEEDING:
            with self.subTest(command=command):
                result, _ = self.load_logged(command, require_existing=True)
                self.assertEqual([], result)

    def test_the_commands_that_need_it_ask_for_it_and_the_others_do_not(self):
        import inspect
        for name in FUNCTIONS_NEEDING:
            with self.subTest(function=name):
                source = inspect.getsource(getattr(g, name))
                self.assertIn('load_manifest(require_existing=True)', source)
                self.assertNotIn('load_manifest()', source)
        for name in FUNCTIONS_NOT_NEEDING:
            with self.subTest(function=name):
                source = inspect.getsource(getattr(g, name))
                self.assertIn('load_manifest(', source)
                self.assertNotIn('require_existing', source)

    def test_the_command_names_are_commands_of_the_program(self):
        self.assertLessEqual(set(NEEDING), set(g.build_parser()[1].choices))

    def test_a_missing_manifest_with_a_backup_is_the_recovery_not_this_message(self):
        self.make_manifest_with_backup()
        os.remove(MANIFEST)
        result, log = self.load_logged('download', require_existing=True)
        self.assertIsInstance(result, SystemExit)             # not interactive: the recovery stops, as before
        self.assertIn('A backup copy exists', log)
        self.assertNotIn('needs it, so nothing was done', log)


class UseBackupTests(UnattendedTestCase):
    def test_without_the_flag_a_run_that_cannot_ask_stops_and_names_the_flag(self):
        self.make_manifest_with_backup()
        os.remove(MANIFEST)
        result, log = self.load_logged('download')
        self.assertIsInstance(result, SystemExit)
        self.assertEqual(1, result.code)
        self.assertIn('-usebackup', log)
        self.assertFalse(os.path.exists(MANIFEST))

    def test_with_the_flag_a_missing_manifest_is_restored_from_the_backup(self):
        self.make_manifest_with_backup(2, 4)
        backup_text = self.text(BACKUP)
        os.remove(MANIFEST)
        g.MANIFEST_USE_BACKUP = True
        with mock.patch.object(builtins, 'input', side_effect=AssertionError('must not ask')):
            result, log = self.load_logged('download')
        self.assertEqual(2, len(result))
        self.assertEqual(backup_text, self.text(MANIFEST))
        self.assertIn('-usebackup was given: using the backup copy', log)
        self.assertIn("restored '%s' from '%s'" % (MANIFEST, BACKUP), log)
        self.assertEqual([1, 0], g.run_report.counts['manifests restored from the backup copy'])

    def test_with_the_flag_a_damaged_manifest_is_restored_and_kept_as_damaged(self):
        self.make_manifest_with_backup(2, 4)
        with open(MANIFEST, 'w', encoding='utf-8') as f:
            f.write('{ "items": [ broken')
        g.MANIFEST_USE_BACKUP = True
        result, log = self.load_logged('verify')
        self.assertEqual(2, len(result))
        self.assertEqual('{ "items": [ broken', self.text(MANIFEST + '.damaged'))
        self.assertIn('the damaged file was kept as', log)

    def test_the_flag_also_works_in_a_terminal_without_asking(self):
        self.make_manifest_with_backup()
        os.remove(MANIFEST)
        g.MANIFEST_USE_BACKUP = True
        self.not_interactive.return_value = True
        with mock.patch.object(builtins, 'input', side_effect=AssertionError('must not ask')):
            result, _ = self.load_logged('update')
        self.assertEqual(2, len(result))

    def test_a_backup_that_is_not_usable_either_stops_the_run_and_changes_nothing(self):
        self.make_manifest_with_backup()
        with open(BACKUP, 'w', encoding='utf-8') as f:
            f.write('{ "items": [ also broken')
        with open(MANIFEST, 'w', encoding='utf-8') as f:
            f.write('{ "items": [ broken')
        g.MANIFEST_USE_BACKUP = True
        result, log = self.load_logged('download')
        self.assertIsInstance(result, SystemExit)
        self.assertEqual(1, result.code)
        self.assertIn('The backup copy is not usable either', log)
        self.assertEqual('{ "items": [ broken', self.text(MANIFEST))
        self.assertFalse(os.path.exists(MANIFEST + '.damaged'))
        self.assertNotIn('manifests restored from the backup copy', g.run_report.counts)

    def test_the_flag_does_not_invent_a_backup(self):
        g.save_manifest(sample_items(2))                     # one save: no backup copy
        self.assertFalse(os.path.exists(BACKUP))
        with open(MANIFEST, 'w', encoding='utf-8') as f:
            f.write('{ "items": [ broken')
        g.MANIFEST_USE_BACKUP = True
        result, log = self.load_logged('update')
        self.assertIsInstance(result, SystemExit)            # not interactive, no backup: stops, as before
        self.assertIn('There is no backup copy', log)
        self.assertEqual('{ "items": [ broken', self.text(MANIFEST))

    def test_the_flag_is_not_used_for_a_manifest_that_is_fine(self):
        self.make_manifest_with_backup(2, 4)
        g.MANIFEST_USE_BACKUP = True
        result, log = self.load_logged('download')
        self.assertEqual(4, len(result))
        self.assertNotIn('-usebackup was given', log)
        self.assertNotIn('manifests restored', g.run_report.counts)


class CommandLineTests(UnattendedTestCase):
    def run_main(self, *argv):
        g.run_report.reset()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(g, 'makeGOGSession', side_effect=AssertionError('the network must not be touched')), \
                mock.patch.object(g, 'load_token', side_effect=AssertionError('the token must not be read')), \
                contextlib.redirect_stdout(out), self.assertLogs('gogrepoc', level='DEBUG') as logs:
            try:
                status = g.main(g.process_argv(['gogrepo_delta.py'] + list(argv)))
            except SystemExit as e:
                status = e.code
            g.info('end of test')
        return status, out.getvalue(), '\n'.join(logs.output)

    def test_every_command_without_a_manifest_stops_before_the_network(self):
        arguments = {'download': ['download', 'games'], 'verify': ['verify', 'games'], 'import': ['import', 'source', 'games'],
                     'backup': ['backup', 'games', 'backups'], 'list': ['list'], 'export': ['export'], 'diagnostics': ['diagnostics']}
        self.assertEqual(set(NEEDING), set(arguments))
        for command, argv in arguments.items():
            with self.subTest(command=command):
                status, _, log = self.run_main(*(argv + ['-nolog']))
                self.assertEqual(1, status)
                self.assertIn("'%s' needs it, so nothing was done" % command, log)

    def test_the_flag_is_an_option_of_every_command_and_off_by_default(self):
        parser, subparsers = g.build_parser()
        for name, sub in subparsers.choices.items():
            with self.subTest(command=name):
                self.assertTrue(any('-usebackup' in action.option_strings for action in sub._actions))
        self.assertFalse(g.process_argv(['gogrepo_delta.py', 'list']).usebackup)
        self.assertTrue(g.process_argv(['gogrepo_delta.py', 'list', '-usebackup']).usebackup)

    def test_a_scheduled_list_uses_the_backup_with_the_flag_and_stops_without_it(self):
        self.make_manifest_with_backup()
        os.remove(MANIFEST)
        status, _, log = self.run_main('list', '-nolog')
        self.assertEqual(1, status)
        self.assertFalse(os.path.exists(MANIFEST))
        status, out, log = self.run_main('list', '-usebackup', '-nolog')
        self.assertEqual(0, status)
        self.assertTrue(os.path.exists(MANIFEST))
        self.assertIn('restored', log)

    def test_the_flag_does_not_stay_on_for_the_next_run(self):
        self.make_manifest_with_backup()
        self.run_main('list', '-usebackup', '-nolog')
        self.assertTrue(g.MANIFEST_USE_BACKUP)
        os.remove(MANIFEST)
        status, _, _ = self.run_main('list', '-nolog')
        self.assertEqual(1, status)
        self.assertFalse(g.MANIFEST_USE_BACKUP)
        self.assertFalse(os.path.exists(MANIFEST))

    def test_the_readme_explains_the_refusal_and_the_flag(self):
        with open(os.path.join(_bootstrap.ROOT, 'README.md'), encoding='utf-8') as r:
            readme = r.read()
        self.assertGreaterEqual(readme.count('--usebackup'), 2)          # where recovery is explained and in the advice for scheduled tasks
        for command in NEEDING:
            self.assertIn('`%s`' % command, readme)
        self.assertIn('manifests restored from the backup copy', readme)

    def test_the_help_says_what_the_flag_is_for(self):
        _, subparsers = g.build_parser()
        action = next(a for a in subparsers.choices['download']._actions if '-usebackup' in a.option_strings)
        self.assertIn('scheduled', action.help)
        self.assertIn('backup', action.help)


if __name__ == '__main__':
    unittest.main()
