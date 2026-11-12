"""Entry 0.5.59: before a folder is deleted by `clean -trash` (-all, -folders, -images) its contents are listed: all of it in a dry run, a
capped list (20 entries per folder, 200 lines in all) otherwise."""
import os
import shutil
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
import test_clean_stages as base

ORPHANED = g.ORPHAN_DIR_NAME
IND = g.LISTING_INDENT


class FakeStdin(object):
    def isatty(self):
        return True


class Listing(base.FolderTests):
    def contents(self, folder, full=False, budget=None):
        return g.folder_contents_lines(os.path.join(self.lib, folder), full, budget if budget is not None else [g.TRASH_LIST_TOTAL])

    def logged(self, fn, *args):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            fn(*args)
        return [r.getMessage() for r in logs.records]

    def fill(self, folder, count, prefix='f'):
        for number in range(count):
            self.make(folder, '%s%02d.bin' % (prefix, number), data=b'x' * (number + 1))


class HelperTests(Listing):
    def test_the_direct_contents_with_sizes_and_a_subfolder_summarised(self):
        self.make('d', 'a.bin', data=b'12345')
        self.make('d', 'sub', 'x.bin', data=b'123')
        self.make('d', 'sub', 'deeper', 'y.bin', data=b'12')
        lines = self.contents('d')
        self.assertEqual(lines, [IND + 'a.bin   %s' % g.pretty_size(5), IND + 'sub%s (2 files, %s)' % (os.sep, g.pretty_size(5))])

    def test_an_empty_folder_says_so(self):
        self.make('d')
        self.assertEqual(self.contents('d'), [IND + '(empty)'])
        self.assertEqual(self.contents('d', full=True), [IND + '(empty)'])

    def test_a_folder_that_cannot_be_read_says_so(self):
        self.make('d', 'a.bin', data=b'1')
        with mock.patch.object(g.os, 'listdir', side_effect=OSError('denied')):
            self.assertEqual(self.contents('d'), [IND + '(contents cannot be listed)'])

    def test_twenty_entries_per_folder_and_the_rest_counted(self):
        self.fill('d', 25)
        lines = self.contents('d')
        self.assertEqual(len(lines), 21)
        self.assertEqual(lines[-1], IND + '... and 5 more items (-dryrun lists everything)')
        self.fill('one', 21)
        self.assertEqual(self.contents('one')[-1], IND + '... and 1 more item (-dryrun lists everything)')

    def test_exactly_twenty_entries_have_no_more_line(self):
        self.fill('d', 20)
        self.assertEqual(len(self.contents('d')), 20)
        self.assertFalse(any('more item' in l for l in self.contents('d')))

    def test_two_hundred_lines_in_all_for_folders_that_share_a_budget(self):
        budget = [g.TRASH_LIST_TOTAL]
        shown = 0
        notes = []
        for number in range(15):
            self.fill('d%02d' % number, 20)
            lines = self.contents('d%02d' % number, budget=budget)
            shown += len([l for l in lines if 'not listed' not in l and 'more item' not in l])
            notes += [l for l in lines if 'not listed' in l]
        self.assertEqual(shown, 200)
        self.assertEqual(budget[0], 0)
        self.assertEqual(len(notes), 5)
        self.assertIn('the limit of 200 lines was reached', notes[0])

    def test_a_dry_run_lists_every_file_below_with_its_path_and_size_and_empty_folders(self):
        self.make('d', 'a.bin', data=b'12345')
        self.make('d', 'sub', 'x.bin', data=b'123')
        self.make('d', 'sub', 'deeper', 'y.bin', data=b'12')
        self.make('d', 'hollow')
        lines = self.contents('d', full=True)
        self.assertEqual(lines, [IND + 'a.bin   %s' % g.pretty_size(5), IND + 'hollow%s (empty)' % os.sep,
                                 IND + 'sub%sx.bin   %s' % (os.sep, g.pretty_size(3)),
                                 IND + 'sub%sdeeper%sy.bin   %s' % (os.sep, os.sep, g.pretty_size(2))])

    def test_a_dry_run_has_no_limit(self):
        self.fill('d', 300)
        self.assertEqual(len(self.contents('d', full=True, budget=[0])), 300)

    def test_a_dry_run_has_no_limit_for_nested_folders_either(self):
        for sub in range(30):
            self.fill(os.path.join('d', 'sub%02d' % sub), 10)
        lines = self.contents('d', full=True, budget=[0])
        self.assertEqual(len(lines), 300)
        self.assertFalse(any('more item' in l or 'not listed' in l for l in lines))

    def test_links_are_shown_as_links_and_not_followed(self):
        outside = self.make('outside', 'secret.bin', data=b'x')
        self.make('d', 'a.bin', data=b'1')
        try:
            os.symlink(os.path.dirname(outside), os.path.join(self.lib, 'd', 'link'), target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('links cannot be created here')
        for full in (False, True):
            lines = self.contents('d', full=full)
            self.assertIn(IND + 'link (link)', lines)
            self.assertFalse(any('secret' in l for l in lines))


class TrashAllListingTests(Listing):
    def setUp(self):
        super().setUp()
        self.make(ORPHANED, 'loose.txt', data=b'12345')
        self.make(ORPHANED, 'old_game', 'a.bin', data=b'12')
        self.make(ORPHANED, 'old_game', 'sub', 'b.bin', data=b'123')

    def trash_all(self, dryrun=False, answer='n', tty=True):
        order = []
        class Collect(__import__('logging').Handler):
            def emit(self, record):
                order.append(record.getMessage())
        handler = Collect()
        logger = __import__('logging').getLogger('gogrepoc')
        logger.addHandler(handler)
        logger.setLevel(10)
        def asked(question):
            order.append('PROMPT: ' + question)
            return answer
        try:
            with mock.patch.object(g.sys, 'stdin', FakeStdin() if tty else None), mock.patch('builtins.input', asked):
                g.cmd_trash_all(self.lib, dryrun, False)
        finally:
            logger.removeHandler(handler)
        return order

    def test_a_folder_is_followed_by_its_contents_and_everything_comes_before_the_question(self):
        log = self.trash_all()
        folder = [i for i, m in enumerate(log) if m.startswith('   old_game' + os.sep)][0]
        self.assertEqual(log[folder + 1], IND + 'a.bin   %s' % g.pretty_size(2))
        self.assertEqual(log[folder + 2], IND + 'sub%s (1 file, %s)' % (os.sep, g.pretty_size(3)))
        prompt = [i for i, m in enumerate(log) if m.startswith('PROMPT: ')][0]
        self.assertLess(folder + 2, prompt)

    def test_a_loose_file_has_no_contents_lines(self):
        log = self.trash_all()
        index = [i for i, m in enumerate(log) if m.startswith('   loose.txt')][0]
        self.assertFalse(log[index + 1].startswith(IND))

    def test_a_dry_run_lists_everything_inside_with_paths(self):
        log = self.trash_all(dryrun=True)
        self.assertIn(IND + 'sub%sb.bin   %s' % (os.sep, g.pretty_size(3)), log)
        self.assertFalse(any(m.startswith('PROMPT') for m in log))

    def test_nothing_is_deleted_by_the_listing(self):
        before = sorted(os.path.join(r, n) for r, ds, fs in os.walk(self.lib) for n in ds + fs)
        self.trash_all()
        self.trash_all(dryrun=True)
        self.assertEqual(sorted(os.path.join(r, n) for r, ds, fs in os.walk(self.lib) for n in ds + fs), before)

    def test_the_lines_of_a_whole_run_are_limited_when_asking_but_not_in_a_dry_run(self):
        shutil.rmtree(os.path.join(self.lib, ORPHANED))
        for number in range(12):
            self.fill(os.path.join(ORPHANED, 'game%02d' % number), 20)
        asking = self.trash_all()
        children = [m for m in asking if m.startswith(IND) and 'not listed' not in m]
        self.assertEqual(len(children), 200)
        self.assertTrue(any('the limit of 200 lines was reached' in m for m in asking))
        full = self.trash_all(dryrun=True)
        self.assertEqual(len([m for m in full if m.startswith(IND)]), 240)

    def test_a_dry_run_lists_every_top_level_entry(self):
        shutil.rmtree(os.path.join(self.lib, ORPHANED))
        for number in range(25):
            self.make(ORPHANED, 'item%02d.txt' % number, data=b'x')
        self.assertEqual(len([m for m in self.trash_all(dryrun=True) if m.startswith('   item')]), 25)
        self.assertEqual(len([m for m in self.trash_all() if m.startswith('   item')]), 20)


class FoldersAndImagesTests(Listing):
    def trash(self, dryrun=False, **switches):
        return self.logged(g.cmd_trash, self.lib, switches.get('installers', False), switches.get('images', False),
                           switches.get('folders', False), switches.get('relaxed', False), dryrun)

    def test_folders_lists_the_contents_after_the_deleting_line_and_deletes_the_folder(self):
        self.make('stargunner', 'keep.bin', data=b'k')
        self.make(ORPHANED, 'stargunner', 'a.bin', data=b'12345')
        self.make(ORPHANED, 'stargunner', 'sub', 'b.bin', data=b'123')
        log = self.trash(folders=True)
        index = [i for i, m in enumerate(log) if m.startswith('Deleting ') and m.endswith('stargunner')][0]
        self.assertEqual(log[index + 1], IND + 'a.bin   %s' % g.pretty_size(5))
        self.assertEqual(log[index + 2], IND + 'sub%s (1 file, %s)' % (os.sep, g.pretty_size(3)))
        self.assertFalse(self.exists(ORPHANED, 'stargunner'))

    def test_a_dry_run_with_folders_lists_everything_and_deletes_nothing(self):
        self.make('stargunner', 'keep.bin', data=b'k')
        self.make(ORPHANED, 'stargunner', 'sub', 'b.bin', data=b'123')
        log = self.trash(dryrun=True, folders=True)
        self.assertIn(IND + 'sub%sb.bin   %s' % (os.sep, g.pretty_size(3)), log)
        self.assertTrue(self.exists(ORPHANED, 'stargunner', 'sub', 'b.bin'))

    def test_a_long_folder_is_capped_when_it_is_really_deleted(self):
        self.make('stargunner', 'keep.bin', data=b'k')
        self.fill(os.path.join(ORPHANED, 'stargunner'), 25)
        log = self.trash(folders=True)
        self.assertEqual(len([m for m in log if m.startswith(IND + 'f')]), 20)
        self.assertIn(IND + '... and 5 more items (-dryrun lists everything)', log)

    def test_the_images_folder_is_listed_too(self):
        self.make('stargunner', g.IMAGES_DIR_NAME, 'keep.png', data=b'k')
        self.make(ORPHANED, 'stargunner', g.IMAGES_DIR_NAME, 'bg.jpg', data=b'12345')
        log = self.trash(images=True)
        index = [i for i, m in enumerate(log) if m.startswith('Deleting ') and m.endswith(g.IMAGES_DIR_NAME)][0]
        self.assertEqual(log[index + 1], IND + 'bg.jpg   %s' % g.pretty_size(5))
        self.assertFalse(self.exists(ORPHANED, 'stargunner', g.IMAGES_DIR_NAME))

    def test_a_folder_that_cannot_be_deleted_is_not_listed_as_deleted(self):
        self.make('stargunner', 'keep.bin', data=b'k')
        self.make(ORPHANED, 'stargunner', 'a.bin', data=b'1')
        with mock.patch.object(g, 'rmtree_force', side_effect=OSError('in use')):
            log = self.trash(folders=True)
        self.assertFalse(any(m.startswith('Deleting ') for m in log))
        self.assertFalse(any(m.startswith(IND + 'a.bin') for m in log))
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_deleting_duplicate_files_still_prints_one_line_each_and_no_contents(self):
        self.make('stargunner', 'm.zip', data=b'm')
        self.make(ORPHANED, 'stargunner', 'm.zip', data=b'm')
        log = self.trash()
        self.assertTrue(any(m.startswith('Deleting ') and m.endswith('m.zip') for m in log))
        self.assertFalse(any(m.startswith(IND) for m in log))


if __name__ == '__main__':
    unittest.main()
