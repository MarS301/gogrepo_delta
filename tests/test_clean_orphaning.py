"""Entry 75: `clean` moves a file to the orphan folder in one place (before: two copies of the code), and a dry run counts a file that is
marked for change like any other (it printed `nothing to clean. nice and tidy!` after `orphaning file ... as it has been marked for change`)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

MARKED = ' as it has been marked for change.'


def entry(name, **extra):
    values = dict(name=name, force_change=False, updated=None, old_updated=None)
    values.update(extra)
    return g.AttrDict(**values)


class OrphaningTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp(prefix='cleanorph_')
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self.cwd)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.library = os.path.join(self.dir, 'library')
        self.game_dir = os.path.join(self.library, 'Game')
        self.orphans = os.path.join(self.library, g.ORPHAN_DIR_NAME, 'Game')
        os.makedirs(self.game_dir)
        g.run_report.reset()
        self.saved = []
        patch = mock.patch.object(g, 'save_manifest', lambda items: self.saved.append(items))
        patch.start()
        self.addCleanup(patch.stop)

    def put(self, name, size=10):
        with open(os.path.join(self.game_dir, name), 'wb') as w:
            w.write(b'x' * size)

    def game(self, *downloads, **kw):
        return g.AttrDict(title='Game', folder_name='Game', downloads=list(downloads), galaxyDownloads=[], sharedDownloads=[],
                          extras=kw.get('extras', []))

    def clean(self, game, dryrun=False):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_clean(self.library, dryrun, [game])
        return '\n'.join(logs.output)

    def in_game(self):
        return sorted(os.listdir(self.game_dir))

    def in_orphans(self):
        return sorted(os.listdir(self.orphans)) if os.path.isdir(self.orphans) else []

    # --- the bug of the handover (open item 7)
    def test_a_dry_run_counts_a_file_marked_for_change(self):
        self.put('a.exe', 2048)
        log = self.clean(self.game(entry('a.exe', force_change=True)), dryrun=True)
        self.assertIn("orphaning file '%s'%s" % (os.path.join('Game', 'a.exe'), MARKED), log)
        self.assertIn('total size of newly orphaned files: 2.00KB', log)
        self.assertNotIn('nothing to clean', log)
        self.assertNotIn('orphaned items moved to', log)
        self.assertEqual(['a.exe'], self.in_game())          # a dry run moves nothing
        self.assertEqual([], self.saved)                     # and saves nothing
        self.assertEqual({}, g.run_report.counts)

    def test_a_dry_run_and_a_real_run_report_the_same_size(self):
        for dryrun in (True, False):
            with self.subTest(dryrun=dryrun):
                shutil.rmtree(self.game_dir, ignore_errors=True)
                shutil.rmtree(os.path.join(self.library, g.ORPHAN_DIR_NAME), ignore_errors=True)
                os.makedirs(self.game_dir)
                self.put('changed.exe', 3000)
                self.put('stray.bin', 1000)
                self.put('same.exe', 5000)
                log = self.clean(self.game(entry('changed.exe', force_change=True), entry('same.exe')), dryrun=dryrun)
                self.assertIn('total size of newly orphaned files: 3.91KB', log)

    # --- both kinds of file
    def test_a_real_run_moves_an_unknown_file_and_a_file_marked_for_change_and_nothing_else(self):
        self.put('changed.exe', 300)
        self.put('stray.bin', 100)
        self.put('same.exe', 500)
        log = self.clean(self.game(entry('changed.exe', force_change=True), entry('same.exe')))
        self.assertEqual(['same.exe'], self.in_game())
        self.assertEqual(['changed.exe', 'stray.bin'], self.in_orphans())
        self.assertIn("orphaning file '%s'" % os.path.join('Game', 'stray.bin'), log)
        self.assertIn('total size of newly orphaned files: 400B', log)
        self.assertIn('orphaned items moved to', log)
        self.assertEqual(1, len(self.saved))
        self.assertEqual([2, 400], g.run_report.counts['files moved to the orphan folder'])
        self.assertEqual([], g.run_report.failures)

    def test_only_the_marked_file_is_called_marked(self):
        self.put('changed.exe')
        self.put('stray.bin')
        log = self.clean(self.game(entry('changed.exe', force_change=True)), dryrun=True)
        lines = [l for l in log.splitlines() if 'orphaning file' in l]
        self.assertEqual(2, len(lines))
        self.assertEqual(1, sum(MARKED in l for l in lines))
        self.assertTrue(all((MARKED in l) == ('changed.exe' in l) for l in lines))

    def test_a_marked_file_is_orphaned_even_when_a_filename_in_the_manifest_is_unknown(self):
        self.put('changed.exe')
        self.put('stray.bin')
        log = self.clean(self.game(entry('changed.exe', force_change=True), entry(None)))
        self.assertEqual(['stray.bin'], self.in_game())      # an unknown filename protects the unrecognised file ...
        self.assertEqual(['changed.exe'], self.in_orphans())  # ... not the one that is to be fetched again
        self.assertIn('Not orphaning unrecognized files', log)

    def test_an_unmarked_known_file_a_subfolder_and_excluded_names_stay(self):
        self.put('same.exe')
        os.makedirs(os.path.join(self.game_dir, 'sub'))
        for name in g.ORPHAN_FILE_EXCLUDE_LIST:
            self.put(name)
        log = self.clean(self.game(entry('same.exe')))
        self.assertIn('nothing to clean. nice and tidy!', log)
        self.assertEqual(sorted(['same.exe', 'sub'] + list(g.ORPHAN_FILE_EXCLUDE_LIST)), self.in_game())
        self.assertEqual([], self.saved)

    def test_a_file_that_is_in_the_manifest_twice_is_moved_once(self):
        self.put('changed.exe')
        log = self.clean(self.game(entry('changed.exe', force_change=True), entry('changed.exe', force_change=True)))
        self.assertEqual(['changed.exe'], self.in_orphans())
        self.assertEqual(1, log.count("orphaning file '%s'" % os.path.join('Game', 'changed.exe')))

    # --- a file that cannot be moved
    def test_a_move_that_fails_is_reported_and_is_not_nothing_to_clean(self):
        for kind, entries in (('unknown', [entry('same.exe')]), ('marked', [entry('stray.bin', force_change=True), entry('same.exe')])):
            with self.subTest(kind=kind):
                g.run_report.reset()
                self.saved[:] = []
                self.put('stray.bin')
                self.put('same.exe')
                with mock.patch.object(g, 'move_with_increment_on_clash', side_effect=OSError('disk full')):
                    log = self.clean(self.game(*entries))
                self.assertIn('disk full', log)
                self.assertIn('could not move to destination', log)
                self.assertIn('nothing could be moved to the orphan folder: see the errors above.', log)
                self.assertNotIn('nothing to clean', log)
                self.assertNotIn('total size', log)
                self.assertEqual([], self.saved)
                self.assertEqual(1, len(g.run_report.failures))
                self.assertIn('could not be moved to the orphan folder: disk full', g.run_report.failures[0][1])
                self.assertEqual(1, g.run_report.exit_status())
                self.assertEqual(['same.exe', 'stray.bin'], self.in_game())

    def test_one_failure_does_not_stop_the_others_and_only_what_moved_is_counted(self):
        self.put('a.bin', 100)
        self.put('b.bin', 200)
        real = g.move_with_increment_on_clash

        def flaky(source, target):
            if os.path.basename(source) == 'a.bin':
                raise OSError('locked')
            return real(source, target)
        with mock.patch.object(g, 'move_with_increment_on_clash', flaky):
            log = self.clean(self.game())
        self.assertEqual(['a.bin'], self.in_game())
        self.assertEqual(['b.bin'], self.in_orphans())
        self.assertIn('total size of newly orphaned files: 200B', log)
        self.assertEqual(1, len(self.saved))
        self.assertEqual([1, 200], g.run_report.counts['files moved to the orphan folder'])
        self.assertEqual(1, len(g.run_report.failures))

    def test_an_orphan_folder_that_cannot_be_made_is_reported_not_a_crash(self):
        self.put('stray.bin')
        os.makedirs(os.path.dirname(self.orphans), exist_ok=True)
        with open(self.orphans, 'w') as w:                    # a file where the folder should be
            w.write('in the way')
        log = self.clean(self.game())
        self.assertIn('could not move to destination', log)
        self.assertEqual(['stray.bin'], self.in_game())
        self.assertEqual(1, len(g.run_report.failures))

    def test_a_dry_run_with_a_file_that_vanishes_is_a_warning_not_a_failure(self):
        self.put('stray.bin')
        with mock.patch.object(g.os.path, 'getsize', side_effect=OSError('gone')):
            log = self.clean(self.game(), dryrun=True)
        self.assertIn("could not look at '%s': gone" % os.path.join('Game', 'stray.bin'), log)
        self.assertEqual([], g.run_report.failures)

    # --- items of an old manifest
    def test_items_without_the_newer_attributes_get_their_defaults(self):
        self.put('same.exe')
        old_entry = g.AttrDict(name='same.exe')
        old_game = g.AttrDict(title='Game', downloads=[old_entry], galaxyDownloads=[], sharedDownloads=[], extras=[])
        log = self.clean(old_game)
        self.assertIn('nothing to clean', log)
        self.assertEqual('Game', old_game.folder_name)
        self.assertEqual((False, None, None), (old_entry.force_change, old_entry.updated, old_entry.old_updated))


class EnsureAttributeTests(unittest.TestCase):
    def test_it_sets_a_missing_attribute_and_returns_it(self):
        item = g.AttrDict()
        self.assertEqual('x', g.ensure_attribute(item, 'folder_name', 'x'))
        self.assertEqual('x', item.folder_name)

    def test_it_never_replaces_a_value_even_a_false_one(self):
        item = g.AttrDict(force_change=False, updated=0, old_updated=None, folder_name='')
        for name, default in (('force_change', True), ('updated', 5), ('old_updated', 'x'), ('folder_name', 'y')):
            with self.subTest(name=name):
                self.assertEqual(item[name], g.ensure_attribute(item, name, default))
        self.assertEqual((False, 0, None, ''), (item.force_change, item.updated, item.old_updated, item.folder_name))

    def test_it_works_on_plain_objects_too(self):
        class Plain(object):
            pass
        obj = Plain()
        self.assertEqual(3, g.ensure_attribute(obj, 'n', 3))
        self.assertEqual(3, g.ensure_attribute(obj, 'n', 9))


if __name__ == '__main__':
    unittest.main()
