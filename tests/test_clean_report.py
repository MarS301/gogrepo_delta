"""Entry 0.5.56: every stage of `clean` says what it looked at and why things were kept; `-trash -all` deletes everything in !orphaned
after showing it and asking (or with -yes); read-only files and folders no longer stop a deletion."""
import os
import shutil
import stat
import sys
import unittest
import warnings
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
import test_clean_stages as base

ORPHANED = g.ORPHAN_DIR_NAME
DOWNLOADING = g.DOWNLOADING_DIR_NAME
PROVISIONAL = g.PROVISIONAL_DIR_NAME


class FakeStdin(object):
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class Reports(base.FolderTests):
    def run_logged(self, fn, *args):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            fn(*args)
        return [r.getMessage() for r in logs.records]

    def said(self, messages, words):
        return any(words in m for m in messages)

    def trash(self, dryrun=False, **switches):
        return self.run_logged(g.cmd_trash, self.lib, switches.get('installers', False), switches.get('images', False),
                               switches.get('folders', False), switches.get('relaxed', False), dryrun)

    def orphaned_tree(self):
        top = os.path.join(self.lib, ORPHANED)
        return sorted(os.path.relpath(os.path.join(r, n), top).replace(os.sep, '/') for r, ds, fs in os.walk(top) for n in ds + fs)


class PartialsReportTests(Reports):
    def test_a_loose_file_is_reported_as_not_touched_and_no_unfinished_downloads_are_named(self):
        self.make(DOWNLOADING, 'loose.txt', data=b'x')
        log = self.run_logged(g.cmd_clear_partial_downloads, self.lib, False)
        self.assertTrue(self.said(log, 'partials: no unfinished downloads'))
        self.assertTrue(self.said(log, 'not touched: 1 loose file directly'))
        self.assertTrue(self.exists(DOWNLOADING, 'loose.txt'))

    def test_the_game_folders_are_counted_and_a_dry_run_says_would(self):
        self.make(DOWNLOADING, 'a', 'x.part', data=b'1')
        self.make(DOWNLOADING, 'b', 'y.part', data=b'2')
        log = self.run_logged(g.cmd_clear_partial_downloads, self.lib, True)
        self.assertTrue(self.said(log, 'partials: 2 unfinished download folders would be deleted'))
        self.assertTrue(self.exists(DOWNLOADING, 'a') and self.exists(DOWNLOADING, 'b'))
        log = self.run_logged(g.cmd_clear_partial_downloads, self.lib, False)
        self.assertTrue(self.said(log, 'partials: 2 unfinished download folders deleted'))
        self.assertFalse(self.said(log, 'loose file'))

    def test_one_folder_is_singular(self):
        self.make(DOWNLOADING, 'a', 'x.part', data=b'1')
        log = self.run_logged(g.cmd_clear_partial_downloads, self.lib, False)
        self.assertTrue(self.said(log, 'partials: 1 unfinished download folder deleted'))

    def test_provisional_nothing_waiting_and_what_was_deleted(self):
        self.make(DOWNLOADING, PROVISIONAL)
        log = self.run_logged(g.cmd_clear_provisional, self.lib, False)
        self.assertTrue(self.said(log, 'provisional: nothing is waiting'))
        self.make(DOWNLOADING, PROVISIONAL, 'game', 'a.bin', data=b'1')
        self.make(DOWNLOADING, PROVISIONAL, 'loose.bin', data=b'2')
        log = self.run_logged(g.cmd_clear_provisional, self.lib, True)
        self.assertTrue(self.said(log, 'provisional: 2 items would be deleted'))
        log = self.run_logged(g.cmd_clear_provisional, self.lib, False)
        self.assertTrue(self.said(log, 'provisional: 2 items deleted'))


class TrashReportTests(Reports):
    def setUp(self):
        super().setUp()
        self.make('stargunner', 'manual.zip', data=b'manual-v1')
        self.make('stargunner', 'setup.sh', data=b'setup')

    def test_an_empty_orphaned_folder_is_named(self):
        self.make(ORPHANED)
        log = self.trash()
        self.assertTrue(self.said(log, "is empty: nothing to trash"))

    def test_loose_files_are_reported_as_not_looked_at_with_the_way_to_delete_them(self):
        self.make(ORPHANED, 'loose.txt', data=b'x')
        log = self.trash()
        self.assertTrue(self.said(log, "looked at 0 folders in '!orphaned'; 0 duplicate files deleted"))
        self.assertTrue(self.said(log, "not looked at: 1 loose file directly in '!orphaned'"))
        self.assertTrue(self.said(log, 'clean -trash -all'))
        self.assertTrue(self.exists(ORPHANED, 'loose.txt'))

    def test_a_duplicate_is_deleted_and_counted_and_nothing_left_means_no_hint(self):
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'manual-v1')
        log = self.trash()
        self.assertTrue(self.said(log, "looked at 1 folder in '!orphaned'; 1 duplicate file deleted"))
        self.assertFalse(self.said(log, 'kept'))
        self.assertFalse(self.said(log, 'clean -trash -all'))
        self.assertFalse(self.exists(ORPHANED, 'stargunner'))

    def test_a_dry_run_says_would_and_keeps_the_file(self):
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'manual-v1')
        log = self.trash(dryrun=True)
        self.assertTrue(self.said(log, '1 duplicate file would be deleted'))
        self.assertTrue(self.exists(ORPHANED, 'stargunner', 'manual.zip'))

    def test_two_duplicates_are_plural(self):
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'manual-v1')
        self.make(ORPHANED, 'stargunner', 'setup.sh', data=b'setup')
        self.assertTrue(self.said(self.trash(), '2 duplicate files deleted'))

    def test_a_file_that_differs_is_kept_and_the_reason_is_given(self):
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'manual-v2')
        log = self.trash()
        self.assertTrue(self.said(log, 'kept 1 file: size or content differs from the game file of the same name'))
        self.assertTrue(self.said(log, 'clean -trash -all'))
        self.assertTrue(self.exists(ORPHANED, 'stargunner', 'manual.zip'))

    def test_a_file_without_a_partner_is_kept_even_if_the_content_is_a_duplicate_of_another_game_file(self):
        self.make(ORPHANED, 'stargunner', 'copy_of_manual.zip', data=b'manual-v1')
        log = self.trash()
        self.assertTrue(self.said(log, 'kept 1 file: the game folder of the same name has no file of that name'))
        self.assertTrue(self.exists(ORPHANED, 'stargunner', 'copy_of_manual.zip'))

    def test_a_folder_without_a_game_folder_is_listed_by_name(self):
        self.make(ORPHANED, 'old_game', 'a.bin', data=b'1')
        log = self.trash()
        self.assertTrue(self.said(log, "kept 1 folder without a game folder of that name (not looked into): old_game"))
        self.assertTrue(self.said(log, "Reference directory does not exist"))

    def test_many_such_folders_are_listed_up_to_five(self):
        for number in range(7):
            self.make(ORPHANED, 'old%d' % number, 'a.bin', data=b'1')
        log = self.trash()
        line = [m for m in log if 'kept 7 folders' in m][0]
        self.assertIn('old0, old1, old2, old3, old4, ...', line)
        self.assertNotIn('old5', line)

    def test_subfolders_are_reported_as_not_looked_at(self):
        self.make(ORPHANED, 'stargunner', 'sub', 'manual.zip', data=b'manual-v1')
        log = self.trash()
        self.assertTrue(self.said(log, 'not looked at: 1 subfolder inside these folders'))
        self.assertTrue(self.exists(ORPHANED, 'stargunner', 'sub', 'manual.zip'))

    def test_a_folder_in_orphaned_that_is_a_file_in_the_game_folder_does_not_crash(self):
        self.make(ORPHANED, 'stargunner', 'manual.zip', 'inner.bin', data=b'1')       # a folder named like the game's file
        log = self.trash()
        self.assertTrue(self.said(log, 'not looked at: 1 subfolder'))
        self.assertTrue(self.exists(ORPHANED, 'stargunner', 'manual.zip', 'inner.bin'))

    def test_relaxed_deletes_a_differing_file_and_reports_it_as_deleted(self):
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'manual-v2')
        log = self.trash(relaxed=True)
        self.assertTrue(self.said(log, '1 duplicate file deleted'))
        self.assertFalse(self.said(log, 'differs'))
        self.assertFalse(self.exists(ORPHANED, 'stargunner'))

    def test_the_strict_run_leaves_everything_but_the_duplicate(self):
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'manual-v1')
        self.make(ORPHANED, 'stargunner', 'other.zip', data=b'o')
        self.make(ORPHANED, 'old_game', 'a.bin', data=b'1')
        self.make(ORPHANED, 'loose.txt', data=b'x')
        self.trash()
        self.assertEqual(self.orphaned_tree(), ['loose.txt', 'old_game', 'old_game/a.bin', 'stargunner', 'stargunner/other.zip'])

    def test_folders_and_relaxed_still_delete_a_folder_without_a_game_folder(self):
        self.make(ORPHANED, 'old_game', 'a.bin', data=b'1')
        self.trash(folders=True, relaxed=True)
        self.assertFalse(self.exists(ORPHANED, 'old_game'))
        self.assertEqual(g.run_report.counts['folders deleted'][0], 1)


class TrashAllTests(Reports):
    def setUp(self):
        super().setUp()
        self.make(ORPHANED, 'loose.txt', data=b'12345')
        self.make(ORPHANED, 'game_a', 'sub', 'deep.bin', data=b'1234567890')
        self.make(ORPHANED, 'game_a', 'top.bin', data=b'1')
        self.make(ORPHANED, 'old_game', 'x.bin', data=b'12')
        self.make('stargunner', 'manual.zip', data=b'm')
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'm')

    def trash_all(self, tty=True, answer=None, assume_yes=False, dryrun=False):
        ask = mock.Mock(return_value=answer if answer is not None else '')
        if isinstance(answer, type) and issubclass(answer, BaseException):
            ask = mock.Mock(side_effect=answer())
        with mock.patch.object(g.sys, 'stdin', FakeStdin(tty)), mock.patch('builtins.input', ask):
            log = self.run_logged(g.cmd_trash_all, self.lib, dryrun, assume_yes)
        return log, ask

    def test_the_listing_shows_the_totals_and_every_entry_with_its_size(self):
        log, ask = self.trash_all(dryrun=True)
        size = g.pretty_size
        self.assertTrue(self.said(log, "'!orphaned' holds 4 items: 5 files, %s" % size(19)))
        for line in ('loose.txt   1 file, %s' % size(5), 'game_a' + os.sep + '   2 files, %s' % size(11), 'old_game' + os.sep + '   1 file, %s' % size(2)):
            self.assertTrue(self.said(log, line), line)

    def test_a_dry_run_deletes_nothing_and_never_asks(self):
        before = self.orphaned_tree()
        log, ask = self.trash_all(dryrun=True)
        self.assertTrue(self.said(log, 'dry run: nothing was deleted'))
        ask.assert_not_called()
        self.assertEqual(self.orphaned_tree(), before)

    def test_yes_in_any_accepted_form_deletes_everything_but_the_orphaned_folder(self):
        for answer in ('y', 'Y', 'yes', ' YES ', 'j', 'ja'):
            with self.subTest(answer=answer):
                self.make(ORPHANED, 'again', 'a.bin', data=b'1')
                self.make(ORPHANED, 'again.txt', data=b'1')
                log, ask = self.trash_all(answer=answer)
                self.assertEqual(os.listdir(os.path.join(self.lib, ORPHANED)), [])
                self.assertTrue(self.said(log, "confirmed: deleting everything in '!orphaned'"))

    def test_anything_else_cancels_and_deletes_nothing(self):
        for answer in ('', 'n', 'no', 'N', 'maybe', 'yess', 'y es'):
            with self.subTest(answer=answer):
                before = self.orphaned_tree()
                g.run_report.reset()
                log, ask = self.trash_all(answer=answer)
                self.assertTrue(self.said(log, 'cancelled: nothing was deleted'))
                self.assertEqual(self.orphaned_tree(), before)
                self.assertEqual(g.run_report.exit_status(), 0)

    def test_a_closed_input_means_no(self):
        before = self.orphaned_tree()
        log, ask = self.trash_all(answer=EOFError)
        self.assertTrue(self.said(log, 'cancelled'))
        self.assertEqual(self.orphaned_tree(), before)

    def test_the_question_names_the_number_and_size_and_the_default(self):
        log, ask = self.trash_all(answer='n')
        question = ask.call_args[0][0]
        self.assertIn("Delete all 4 items (%s) from '!orphaned' for good?" % g.pretty_size(19), question)
        self.assertTrue(question.endswith('[y/N] '))

    def test_without_a_terminal_it_refuses_and_says_how_to_run_it_unattended(self):
        before = self.orphaned_tree()
        log, ask = self.trash_all(tty=False)
        ask.assert_not_called()
        self.assertTrue(self.said(log, 'no terminal to ask on'))
        self.assertTrue(self.said(log, 'add -yes'))
        self.assertEqual(self.orphaned_tree(), before)
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertIn('no terminal', g.run_report.failures[0][1])

    def test_a_missing_standard_input_counts_as_no_terminal(self):
        before = self.orphaned_tree()
        with mock.patch.object(g.sys, 'stdin', None), mock.patch('builtins.input', side_effect=AssertionError('no asking')):
            self.run_logged(g.cmd_trash_all, self.lib, False, False)
        self.assertEqual(self.orphaned_tree(), before)
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_yes_deletes_without_a_terminal_and_without_asking(self):
        log, ask = self.trash_all(tty=False, assume_yes=True)
        ask.assert_not_called()
        self.assertEqual(os.listdir(os.path.join(self.lib, ORPHANED)), [])
        self.assertTrue(self.said(log, '-yes given'))
        self.assertEqual(g.run_report.exit_status(), 0)

    def test_yes_with_a_terminal_does_not_ask_either(self):
        log, ask = self.trash_all(tty=True, assume_yes=True)
        ask.assert_not_called()
        self.assertEqual(os.listdir(os.path.join(self.lib, ORPHANED)), [])

    def test_the_counts_for_the_summary(self):
        self.trash_all(assume_yes=True)
        self.assertEqual(g.run_report.counts['orphaned files deleted'], [1, 5])
        self.assertEqual(g.run_report.counts['orphaned folders deleted'][0], 3)
        self.assertEqual(g.run_report.counts['orphaned folders deleted'][1], 11 + 2 + 1)

    def test_an_empty_or_missing_orphaned_folder_does_not_ask(self):
        shutil.rmtree(os.path.join(self.lib, ORPHANED))
        log, ask = self.trash_all()
        self.assertTrue(self.said(log, 'nothing to trash'))
        self.make(ORPHANED)
        log, ask = self.trash_all()
        self.assertTrue(self.said(log, 'is empty'))
        ask.assert_not_called()

    def test_a_long_list_is_cut_after_twenty_entries_when_asking_but_a_dry_run_lists_all(self):
        shutil.rmtree(os.path.join(self.lib, ORPHANED))
        for number in range(25):
            self.make(ORPHANED, 'item%02d.txt' % number, data=b'x')
        log, ask = self.trash_all(answer='n')
        self.assertEqual(len([m for m in log if m.startswith('   item')]), 20)
        self.assertTrue(self.said(log, '... and 5 more items'))
        self.assertTrue(self.said(log, 'holds 25 items'))
        log, ask = self.trash_all(dryrun=True)
        self.assertEqual(len([m for m in log if m.startswith('   item')]), 25)
        self.assertFalse(self.said(log, 'more item'))

    def test_one_entry_that_cannot_be_deleted_does_not_stop_the_others(self):
        real = g.rmtree_force
        def fussy(path):
            if os.path.basename(path) == 'game_a':
                raise OSError('in use')
            real(path)
        with mock.patch.object(g, 'rmtree_force', fussy):
            self.trash_all(assume_yes=True)
        self.assertEqual(self.orphaned_tree(), ['game_a', 'game_a/sub', 'game_a/sub/deep.bin', 'game_a/top.bin'])
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertIn('in use', g.run_report.failures[0][1])

    def test_a_link_is_removed_and_not_followed(self):
        outside = os.path.join(self.dir, 'outside')
        os.makedirs(outside)
        open(os.path.join(outside, 'keep.txt'), 'w').close()
        try:
            os.symlink(outside, os.path.join(self.lib, ORPHANED, 'link'), target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('links cannot be created here')
        self.trash_all(assume_yes=True)
        self.assertEqual(os.listdir(os.path.join(self.lib, ORPHANED)), [])
        self.assertTrue(os.path.exists(os.path.join(outside, 'keep.txt')))
        self.assertEqual(g.run_report.counts['orphaned links deleted'][0], 1)


class ReadOnlyTests(Reports):
    def test_the_handler_makes_the_path_writable_and_retries(self):
        target = self.make('ro', 'file.txt', data=b'x')
        os.chmod(target, stat.S_IREAD)
        def fake_rmtree(path, **kw):
            handler = kw.get('onexc') or kw.get('onerror')
            exc = PermissionError(13, 'denied')
            handler(os.remove, target, exc if 'onexc' in kw else (PermissionError, exc, None))
        with mock.patch.object(g.shutil, 'rmtree', fake_rmtree), mock.patch.object(g.os, 'chmod', wraps=os.chmod) as chmod:
            g.rmtree_force(os.path.join(self.lib, 'ro'))
        self.assertFalse(os.path.exists(target))
        self.assertIn(mock.call(target, stat.S_IRWXU), chmod.call_args_list)

    def test_the_keyword_for_the_error_handler_is_the_one_of_the_python_version(self):
        # onerror is deprecated from 3.12 (onexc replaces it); older versions only know onerror
        seen = {}
        with mock.patch.object(g.shutil, 'rmtree', lambda path, **kw: seen.update(kw)):
            g.rmtree_force(os.path.join(self.lib, 'x'))
        self.assertEqual(sorted(seen), ['onexc'] if sys.version_info >= (3, 12) else ['onerror'])

    def test_a_failure_that_is_not_a_permission_problem_is_raised(self):
        def fake_rmtree(path, **kw):
            handler = kw.get('onexc') or kw.get('onerror')
            exc = FileNotFoundError(2, 'gone')
            handler(os.remove, path, exc if 'onexc' in kw else (FileNotFoundError, exc, None))
        with mock.patch.object(g.shutil, 'rmtree', fake_rmtree):
            with self.assertRaises(FileNotFoundError):
                g.rmtree_force(os.path.join(self.lib, 'x'))

    def test_a_normal_folder_is_removed_without_a_deprecation_warning(self):
        folder = self.make('plain', 'a', 'b.txt', data=b'x')
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            g.rmtree_force(os.path.join(self.lib, 'plain'))
        self.assertFalse(self.exists('plain'))

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'the root user ignores file permissions')
    def test_read_only_files_and_folders_are_really_deleted(self):
        nested = os.path.dirname(self.make('git', 'objects', 'pack', 'x.pack', data=b'x'))
        os.chmod(os.path.join(nested, 'x.pack'), stat.S_IREAD)           # the attribute Git sets; Windows refuses to delete such a file
        if os.name != 'nt':
            os.chmod(nested, stat.S_IRUSR | stat.S_IXUSR)                 # POSIX: a folder without write permission
        g.rmtree_force(os.path.join(self.lib, 'git'))
        self.assertFalse(self.exists('git'))

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'the root user ignores file permissions')
    def test_trash_all_deletes_a_read_only_git_folder_in_orphaned(self):
        pack = self.make(ORPHANED, '.git', 'objects', 'x.pack', data=b'x')
        os.chmod(pack, stat.S_IREAD)
        if os.name != 'nt':
            os.chmod(os.path.dirname(pack), stat.S_IRUSR | stat.S_IXUSR)
        g.cmd_trash_all(self.lib, False, True)
        self.assertEqual(os.listdir(os.path.join(self.lib, ORPHANED)), [])
        self.assertEqual(g.run_report.exit_status(), 0)


class OptionTests(unittest.TestCase):
    def parse(self, *argv):
        return g.process_argv(['gogrepo_delta.py', 'clean', 'dir'] + list(argv) + ['-nolog'])

    def refused(self, *argv):
        import io
        import contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch.object(g, 'error'):
            with self.assertRaises(SystemExit) as raised:
                self.parse(*argv)
        self.assertEqual(raised.exception.code, 2)
        return err.getvalue()

    def test_all_and_yes_are_off_by_default_and_parse(self):
        plain = self.parse('-trash')
        self.assertFalse(plain.all)
        self.assertFalse(plain.yes)
        both = self.parse('-trash', '-all', '-yes')
        self.assertTrue(both.all and both.yes)
        self.assertTrue(self.parse('--trash', '--all').all)

    def test_all_needs_trash(self):
        self.assertIn('-all can only be used together with -trash', self.refused('-all'))

    def test_all_cannot_be_mixed_with_the_refinements(self):
        for name in ('installers', 'images', 'folders', 'relaxed'):
            message = self.refused('-trash', '-all', '-' + name)
            self.assertIn('-all deletes everything', message)
            self.assertIn('-' + name, message)

    def test_yes_needs_trash_and_all(self):
        self.assertIn('-yes can only be used together with -trash -all', self.refused('-yes'))
        self.assertIn('-yes can only be used together with -trash -all', self.refused('-trash', '-yes'))

    def test_all_cannot_be_used_in_the_run_that_makes_orphans(self):
        self.assertIn('-orphans and -trash cannot be used in the same run', self.refused('-orphans', '-trash', '-all'))


class StageAndCommandTests(Reports):
    def test_the_trash_stage_chooses_between_strict_and_all(self):
        calls = []
        with mock.patch.object(g, 'cmd_trash', lambda *a: calls.append(('strict',) + a)), \
                mock.patch.object(g, 'cmd_trash_all', lambda *a: calls.append(('all',) + a)):
            g.cmd_clean_stages(self.lib, False, False, False, True, False, False, False, False, True)
            g.cmd_clean_stages(self.lib, False, False, False, True, False, False, False, False, False, True, True)
        self.assertEqual(calls, [('strict', self.lib, False, False, False, False, True), ('all', self.lib, False, True)])

    def run_main(self, *argv):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            status = g.main(g.process_argv(['gogrepo_delta.py', 'clean', self.lib] + list(argv) + ['-nolog']))
        return status, [r.getMessage() for r in logs.records]

    def fill_orphaned(self):
        self.make(ORPHANED, 'loose.txt', data=b'x')
        self.make(ORPHANED, 'old_game', 'a.bin', data=b'1')

    def test_through_main_yes_deletes_everything_with_no_manifest_and_no_terminal(self):
        self.fill_orphaned()
        with mock.patch.object(g.sys, 'stdin', FakeStdin(False)):
            status, log = self.run_main('-trash', '-all', '-yes')
        self.assertEqual(status, 0, log)
        self.assertEqual(os.listdir(os.path.join(self.lib, ORPHANED)), [])

    def test_through_main_without_a_terminal_and_without_yes_nothing_is_deleted(self):
        self.fill_orphaned()
        with mock.patch.object(g.sys, 'stdin', FakeStdin(False)):
            status, log = self.run_main('-trash', '-all')
        self.assertEqual(status, 1)
        self.assertEqual(self.orphaned_tree(), ['loose.txt', 'old_game', 'old_game/a.bin'])

    def test_through_main_at_a_terminal_the_answer_decides(self):
        self.fill_orphaned()
        with mock.patch.object(g.sys, 'stdin', FakeStdin(True)), mock.patch('builtins.input', return_value='n'):
            status, log = self.run_main('-trash', '-all')
        self.assertEqual(status, 0)
        self.assertEqual(self.orphaned_tree(), ['loose.txt', 'old_game', 'old_game/a.bin'])
        with mock.patch.object(g.sys, 'stdin', FakeStdin(True)), mock.patch('builtins.input', return_value='y'):
            status, log = self.run_main('-trash', '-all')
        self.assertEqual(status, 0)
        self.assertEqual(self.orphaned_tree(), [])

    def test_plain_trash_never_asks_and_stays_strict(self):
        self.make('stargunner', 'manual.zip', data=b'm')
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'm')
        self.fill_orphaned()
        with mock.patch.object(g.sys, 'stdin', FakeStdin(True)), mock.patch('builtins.input', side_effect=AssertionError('no asking')):
            status, log = self.run_main('-trash')
        self.assertEqual(status, 0, log)
        self.assertEqual(self.orphaned_tree(), ['loose.txt', 'old_game', 'old_game/a.bin'])

    def test_the_old_trash_command_is_unchanged_and_never_asks(self):
        self.make('stargunner', 'manual.zip', data=b'm')
        self.make(ORPHANED, 'stargunner', 'manual.zip', data=b'm')
        self.fill_orphaned()
        with mock.patch.object(g.sys, 'stdin', FakeStdin(True)), mock.patch('builtins.input', side_effect=AssertionError('no asking')), \
                self.assertLogs('gogrepoc', level='INFO'):
            status = g.main(g.process_argv(['gogrepo_delta.py', 'trash', self.lib, '-nolog']))
        self.assertEqual(status, 0)
        self.assertEqual(self.orphaned_tree(), ['loose.txt', 'old_game', 'old_game/a.bin'])

    def test_a_dry_run_through_main_lists_and_changes_nothing(self):
        self.fill_orphaned()
        with mock.patch.object(g.sys, 'stdin', FakeStdin(True)), mock.patch('builtins.input', side_effect=AssertionError('no asking')):
            status, log = self.run_main('-trash', '-all', '-dryrun')
        self.assertEqual(status, 0)
        self.assertTrue(any('dry run: nothing was deleted' in m for m in log))
        self.assertEqual(self.orphaned_tree(), ['loose.txt', 'old_game', 'old_game/a.bin'])


if __name__ == '__main__':
    unittest.main()
