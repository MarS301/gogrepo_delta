"""`clean` with its stages (-partials, -provisional, -orphans, -trash), the rules for combining them, the two bug fixes
(the !provisional folder was never emptied; missing !downloading / !orphaned crashed) and the deprecated commands
`trash` and `clear_partial_downloads` (entry 0.5.52)."""
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

DOWNLOADING = g.DOWNLOADING_DIR_NAME
PROVISIONAL = g.PROVISIONAL_DIR_NAME
ORPHANED = g.ORPHAN_DIR_NAME


def args_for(*argv):
    return g.process_argv(['gogrepo_delta.py'] + list(argv) + ['-nolog'])


def fails_with(*argv):
    """The message of the parser error (exit status 2) for these arguments."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), mock.patch.object(g, 'error'):
        with unittest.TestCase().assertRaises(SystemExit) as raised:
            args_for(*argv)
    assert raised.exception.code == 2, raised.exception.code
    return err.getvalue()


class CleanOptionTests(unittest.TestCase):
    def test_without_switches_no_stage_is_selected_so_clean_does_what_it_always_did(self):
        a = args_for('clean', 'dir')
        self.assertEqual(a.gamedir, 'dir')
        for name in ('orphans', 'partials', 'provisional', 'trash', 'installers', 'images', 'folders', 'relaxed', 'dryrun'):
            self.assertFalse(getattr(a, name), name)

    def test_the_stage_switches_work_in_both_spellings(self):
        for name in ('orphans', 'partials', 'provisional'):
            single, double = args_for('clean', 'dir', '-' + name), args_for('clean', 'dir', '--' + name)
            self.assertTrue(getattr(single, name) and getattr(double, name), name)
            self.assertEqual(vars(single), vars(double), name)

    def test_trash_takes_its_refinements(self):
        a = args_for('clean', 'dir', '-trash', '-installers', '-images', '-folders', '-relaxed', '-dryrun')
        self.assertTrue(all(getattr(a, n) for n in ('trash', 'installers', 'images', 'folders', 'relaxed', 'dryrun')))

    def test_orphans_and_trash_in_one_run_are_refused_before_anything_happens(self):
        message = fails_with('clean', 'dir', '-orphans', '-trash')
        self.assertIn('-orphans and -trash cannot be used in the same run', message)
        self.assertIn('clean -trash', message)

    def test_the_refinements_are_refused_without_trash(self):
        for name in ('installers', 'images', 'folders', 'relaxed'):
            message = fails_with('clean', 'dir', '-' + name)
            self.assertIn('-%s can only be used together with -trash' % name, message)
        self.assertIn('-installers, -folders can only be used together with -trash', fails_with('clean', 'dir', '-installers', '-folders'))
        self.assertIn('can only be used together with -trash', fails_with('clean', 'dir', '-partials', '-relaxed'))

    def test_the_old_commands_still_parse_with_their_old_options(self):
        a = args_for('trash', 'dir', '-installersonly', '-folders', '-images', '-relaxed', '-dryrun')
        self.assertEqual((a.gamedir, a.installersonly, a.folders, a.images, a.relaxed, a.dryrun), ('dir', True, True, True, True, True))
        self.assertTrue(args_for('clear_partial_downloads', 'dir', '-dryrun').dryrun)

    def test_the_old_commands_do_not_get_the_new_checks(self):
        # trash -folders is what it always was; only `clean` has the rule that refinements need -trash
        self.assertTrue(args_for('trash', 'dir', '-folders').folders)

    def test_the_folder_of_clean_is_called_gamedir_like_in_the_other_commands(self):
        self.assertFalse(hasattr(args_for('clean', 'dir'), 'cleandir'))


class StageSelectionTests(unittest.TestCase):
    """Which functions run, and in which order (the functions themselves are replaced here)."""
    def run_stages(self, **chosen):
        flags = dict(orphans=False, partials=False, provisional=False, trash=False, installers=False, images=False, folders=False,
                     relaxed=False, dryrun=False)
        flags.update(chosen)
        calls = []
        patches = {'cmd_clean': lambda d, dry, items=None: calls.append(('orphans', d, dry)),
                   'load_manifest': lambda: [object()],
                   'clean_manifest_problem': lambda d, items: None,
                   'clean_target_problem': lambda d, items: None,
                   'cmd_clear_partial_downloads': lambda d, dry: calls.append(('partials', d, dry)),
                   'cmd_clear_provisional': lambda d, dry: calls.append(('provisional', d, dry)),
                   'cmd_trash': lambda d, i, im, f, r, dry: calls.append(('trash', d, (i, im, f, r), dry))}
        with contextlib.ExitStack() as stack:
            for name, fake in patches.items():
                stack.enter_context(mock.patch.object(g, name, fake))
            g.cmd_clean_stages('lib', flags['orphans'], flags['partials'], flags['provisional'], flags['trash'], flags['installers'],
                               flags['images'], flags['folders'], flags['relaxed'], flags['dryrun'])
        return calls

    def test_no_switch_runs_only_the_orphans_stage(self):
        self.assertEqual(self.run_stages(), [('orphans', 'lib', False)])

    def test_orphans_alone_is_the_same_as_no_switch(self):
        self.assertEqual(self.run_stages(orphans=True), self.run_stages())

    def test_partials_alone_does_not_run_the_orphans_stage(self):
        self.assertEqual(self.run_stages(partials=True), [('partials', 'lib', False)])

    def test_provisional_alone_does_not_touch_the_unfinished_downloads(self):
        self.assertEqual(self.run_stages(provisional=True), [('provisional', 'lib', False)])

    def test_trash_alone_does_not_move_anything_to_the_orphan_folder(self):
        self.assertEqual(self.run_stages(trash=True, folders=True, relaxed=True, dryrun=True),
                         [('trash', 'lib', (False, False, True, True), True)])

    def test_the_stages_run_in_a_fixed_order(self):
        every = self.run_stages(partials=True, provisional=True, orphans=True)
        self.assertEqual([c[0] for c in every], ['partials', 'provisional', 'orphans'])
        later = self.run_stages(partials=True, provisional=True, trash=True)
        self.assertEqual([c[0] for c in later], ['partials', 'provisional', 'trash'])

    def test_the_dry_run_reaches_every_stage(self):
        calls = self.run_stages(partials=True, provisional=True, orphans=True, dryrun=True)
        self.assertTrue(all(c[-1] is True or c[2] is True for c in calls), calls)


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset()
        self.lib = os.path.join(self.dir, 'lib')
        os.makedirs(self.lib)

    def make(self, *parts, data=None):
        path = os.path.join(self.lib, *parts)
        if data is None:
            os.makedirs(path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
        return path

    def exists(self, *parts):
        return os.path.exists(os.path.join(self.lib, *parts))

    def library_with_unfinished_work(self):
        self.make(DOWNLOADING, 'game_a', 'x.part', data=b'1')
        self.make(DOWNLOADING, 'game_b', 'y.part', data=b'2')
        self.make(DOWNLOADING, PROVISIONAL, 'game_c', 'done.bin', data=b'3')
        self.make(DOWNLOADING, PROVISIONAL, 'loose.bin', data=b'44')


class PartialsTests(FolderTests):
    def test_partials_deletes_the_unfinished_game_folders_and_keeps_the_provisional_files(self):
        self.library_with_unfinished_work()
        g.cmd_clear_partial_downloads(self.lib, False)
        self.assertFalse(self.exists(DOWNLOADING, 'game_a'))
        self.assertFalse(self.exists(DOWNLOADING, 'game_b'))
        self.assertTrue(self.exists(DOWNLOADING, PROVISIONAL, 'game_c', 'done.bin'))
        self.assertTrue(self.exists(DOWNLOADING, PROVISIONAL, 'loose.bin'))
        self.assertEqual(g.run_report.counts['partial download folders deleted'][0], 2)

    def test_a_dry_run_deletes_and_counts_nothing(self):
        self.library_with_unfinished_work()
        g.cmd_clear_partial_downloads(self.lib, True)
        self.assertTrue(self.exists(DOWNLOADING, 'game_a') and self.exists(DOWNLOADING, 'game_b'))
        self.assertEqual(g.run_report.counts, {})

    def test_a_library_without_a_downloading_folder_is_not_an_error(self):
        # used to end with FileNotFoundError
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_clear_partial_downloads(self.lib, False)
        self.assertIn('no partial downloads to delete', '\n'.join(logs.output))
        self.assertEqual(g.run_report.failures, [])
        self.assertEqual(g.run_report.exit_status(), 0)


class ProvisionalTests(FolderTests):
    def test_provisional_deletes_folders_and_loose_files_but_keeps_the_folder_itself(self):
        self.library_with_unfinished_work()
        g.cmd_clear_provisional(self.lib, False)
        self.assertEqual(os.listdir(os.path.join(self.lib, DOWNLOADING, PROVISIONAL)), [])
        self.assertEqual(g.run_report.counts['provisional folders deleted'][0], 1)
        self.assertEqual(g.run_report.counts['provisional files deleted'], [1, 2])
        self.assertEqual(g.run_report.failures, [])

    def test_provisional_leaves_the_unfinished_downloads_alone(self):
        self.library_with_unfinished_work()
        g.cmd_clear_provisional(self.lib, False)
        self.assertTrue(self.exists(DOWNLOADING, 'game_a', 'x.part'))
        self.assertTrue(self.exists(DOWNLOADING, 'game_b', 'y.part'))

    def test_the_old_bug_provisional_folders_survived_clear_partial_downloads(self):
        # The old command looked for the !provisional folders inside !downloading, so they were never deleted. -partials still does
        # not touch them (that is -provisional's job), and -provisional really does.
        self.library_with_unfinished_work()
        g.cmd_clear_partial_downloads(self.lib, False)
        self.assertTrue(self.exists(DOWNLOADING, PROVISIONAL, 'game_c'))
        g.cmd_clear_provisional(self.lib, False)
        self.assertFalse(self.exists(DOWNLOADING, PROVISIONAL, 'game_c'))

    def test_a_dry_run_deletes_and_counts_nothing(self):
        self.library_with_unfinished_work()
        g.cmd_clear_provisional(self.lib, True)
        self.assertTrue(self.exists(DOWNLOADING, PROVISIONAL, 'game_c', 'done.bin'))
        self.assertTrue(self.exists(DOWNLOADING, PROVISIONAL, 'loose.bin'))
        self.assertEqual(g.run_report.counts, {})

    def test_a_library_without_the_folder_is_not_an_error(self):
        self.make(DOWNLOADING, 'game_a', 'x.part', data=b'1')        # !downloading exists, !provisional does not
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_clear_provisional(self.lib, False)
        self.assertIn('no finished files are waiting', '\n'.join(logs.output))
        self.assertEqual(g.run_report.exit_status(), 0)
        self.assertTrue(self.exists(DOWNLOADING, 'game_a'))

    def test_what_cannot_be_deleted_is_a_failure_not_a_crash(self):
        self.library_with_unfinished_work()
        with mock.patch.object(g.shutil, 'rmtree', side_effect=OSError('in use')), \
                mock.patch.object(g.os, 'remove', side_effect=OSError('locked')):
            g.cmd_clear_provisional(self.lib, False)
        reasons = ' '.join(why for _, why in g.run_report.failures)
        self.assertEqual(len(g.run_report.failures), 2)
        self.assertIn('in use', reasons)
        self.assertIn('locked', reasons)
        self.assertEqual(g.run_report.exit_status(), 1)


class TrashTests(FolderTests):
    def test_a_library_without_an_orphaned_folder_is_not_an_error(self):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_trash(self.lib, True, True, True, True, False)
        self.assertIn('nothing to trash', '\n'.join(logs.output))
        self.assertEqual(g.run_report.counts, {})
        self.assertEqual(g.run_report.exit_status(), 0)

    def test_trash_stage_deletes_a_strict_duplicate_and_keeps_a_different_file(self):
        self.make('game', 'a.bin', data=b'same')
        self.make('game', 'b.bin', data=b'new')
        self.make(ORPHANED, 'game', 'a.bin', data=b'same')
        self.make(ORPHANED, 'game', 'b.bin', data=b'old')
        g.cmd_clean_stages(self.lib, False, False, False, True, False, False, False, False, False)
        self.assertFalse(self.exists(ORPHANED, 'game', 'a.bin'))
        self.assertTrue(self.exists(ORPHANED, 'game', 'b.bin'))
        self.assertTrue(self.exists('game', 'a.bin'))

    def test_the_trash_stage_does_not_move_files_into_the_orphan_folder(self):
        self.make('game', 'known.bin', data=b'k')
        g.cmd_clean_stages(self.lib, False, False, False, True, False, False, False, False, False)
        self.assertFalse(self.exists(ORPHANED))


class CommandTests(FolderTests):
    """Through main(), the way the command line reaches the code."""
    def run_main(self, *argv):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            status = g.main(args_for(*argv))
        return status, '\n'.join(r.levelname + ' ' + r.getMessage() for r in logs.records)

    def test_clean_with_partials_runs_without_a_manifest(self):
        # only the orphans stage needs the manifest; there is none in this folder
        self.library_with_unfinished_work()
        status, log = self.run_main('clean', self.lib, '-partials')
        self.assertEqual(status, 0, log)
        self.assertFalse(self.exists(DOWNLOADING, 'game_a'))
        self.assertTrue(self.exists(DOWNLOADING, PROVISIONAL, 'game_c'))
        self.assertNotIn('manifest', log.lower().replace('gog-manifest', ''))

    def test_clean_with_provisional_and_partials_empties_everything_unfinished(self):
        self.library_with_unfinished_work()
        status, log = self.run_main('clean', self.lib, '-partials', '-provisional')
        self.assertEqual(status, 0, log)
        self.assertEqual(os.listdir(os.path.join(self.lib, DOWNLOADING)), [PROVISIONAL])
        self.assertEqual(os.listdir(os.path.join(self.lib, DOWNLOADING, PROVISIONAL)), [])

    def test_clean_with_trash_runs_without_a_manifest_and_deletes_folders(self):
        self.make('game', 'a.bin', data=b'x')
        self.make(ORPHANED, 'game', 'old.bin', data=b'o')
        status, log = self.run_main('clean', self.lib, '-trash', '-folders')
        self.assertEqual(status, 0, log)
        self.assertFalse(self.exists(ORPHANED, 'game'))

    def test_a_dry_run_through_main_changes_nothing(self):
        self.library_with_unfinished_work()
        self.make('game', 'a.bin', data=b'x')
        self.make(ORPHANED, 'game', 'old.bin', data=b'o')
        before = sorted(os.path.join(r, f) for r, _, fs in os.walk(self.lib) for f in fs)
        for argv in (('-partials', '-provisional'), ('-trash', '-folders', '-relaxed', '-installers')):
            status, log = self.run_main('clean', self.lib, '-dryrun', *argv)
            self.assertEqual(status, 0, log)
        after = sorted(os.path.join(r, f) for r, _, fs in os.walk(self.lib) for f in fs)
        self.assertEqual(before, after)

    def test_the_old_clear_partial_downloads_command_warns_and_still_works(self):
        self.library_with_unfinished_work()
        status, log = self.run_main('clear_partial_downloads', self.lib)
        self.assertEqual(status, 0, log)
        self.assertIn('WARNING the command clear_partial_downloads is deprecated', log)
        self.assertIn('clean -partials', log)
        self.assertFalse(self.exists(DOWNLOADING, 'game_a'))
        self.assertTrue(self.exists(DOWNLOADING, PROVISIONAL, 'game_c'))      # as before: finished files are not touched

    def test_the_old_trash_command_warns_and_still_works(self):
        self.make('game', 'a.bin', data=b'same')
        self.make(ORPHANED, 'game', 'a.bin', data=b'same')
        status, log = self.run_main('trash', self.lib, '-installersonly')
        self.assertEqual(status, 0, log)
        self.assertIn('WARNING the command trash is deprecated', log)
        self.assertIn('clean -trash', log)
        self.assertFalse(self.exists(ORPHANED, 'game', 'a.bin'))


if __name__ == '__main__':
    unittest.main()
