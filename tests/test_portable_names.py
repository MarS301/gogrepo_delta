"""Entry 0.5.90: a file name that is not portable (Linux, Windows and macOS alike) is made portable where `update` stores it, a manifest that already holds such names is
migrated by `update`, and every place that joins a manifest name to a folder refuses a name that is still not portable.

portable_file_name: every refused character becomes '_', a trailing space or dot is dropped, a device name gets a '_' in front, a name over 251 bytes is shortened to 240.
The old name is kept in old_name (so the existing rename handling moves the file) and in name_from_server (only when it differs from the stored name)."""
import glob
import hashlib
import logging
import os
import random
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g
import test_run_summary as trs
from test_file_name_safety import create_file_named, path_in


class Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def warnings(self):
        return [r.getMessage() for r in self.records if r.levelname == 'WARNING']


class LogCase(unittest.TestCase):
    def setUp(self):
        self.handler = Capture()
        g.rootLogger.addHandler(self.handler)
        self.addCleanup(g.rootLogger.removeHandler, self.handler)
        g.run_report.reset()
        self.addCleanup(g.run_report.reset)


class PortableFileNameTests(unittest.TestCase):
    CASES = {'setup:2.exe': 'setup_2.exe', 'what?.pdf': 'what_.pdf', 'a<b>c|d"e*f.zip': 'a_b_c_d_e_f.zip', '../../x.exe': '.._.._x.exe', 'sub/a.exe': 'sub_a.exe',
             'sub\\a.exe': 'sub_a.exe', 'a\x00b\x1fc\x7fd.bin': 'a_b_c_d.bin', 'name.': 'name', 'name. . ': 'name', 'CON': '_CON', 'con.txt': '_con.txt', 'NUL.tar.gz': '_NUL.tar.gz',
             'COM1.exe': '_COM1.exe', 'LPT\u00b2': '_LPT\u00b2', '': '_', '.': '_', '..': '_', '...': '_', ' ': '_', 'ok.exe': 'ok.exe', 'console.exe': 'console.exe',
             'the.art.of.playing.(2014).1080p.mp4': 'the.art.of.playing.(2014).1080p.mp4', '.hidden': '.hidden', 'n\u00e4me \u4e2d\u6587.pdf': 'n\u00e4me \u4e2d\u6587.pdf'}

    def test_known_names(self):
        for name, expected in self.CASES.items():
            with self.subTest(name=name):
                self.assertEqual(g.portable_file_name(name), expected)

    def test_a_name_that_is_fine_is_returned_as_it_is(self):
        for name in ('setup_a.exe', 'a b.zip', ' lead.zip', 'a..b', 'x.con', 'COM0', 'COM10.txt'):
            self.assertEqual(g.portable_file_name(name), name)

    def test_the_result_is_always_portable_and_a_second_run_changes_nothing(self):
        rng = random.Random(20261124)
        pieces = list('abAB.. :/\\<>"|?*\x00\x1f\x7f-_()[]~') + ['\u00e4', '\u4e2d', '\U0001f600', '\u00b9', 'CON', 'con', 'NUL', 'COM1', '.zip', '.exe', 'x' * 30]
        for _ in range(20000):
            name = ''.join(rng.choice(pieces) for _ in range(rng.choice([0, 1, 2, 3, 5, 10, 40, 150, 400])))
            portable = g.portable_file_name(name)
            self.assertIsNone(g.unsafe_file_name_reason(portable), repr(name))
            self.assertEqual(g.portable_file_name(portable), portable, repr(name))
            if g.unsafe_file_name_reason(name) is None:
                self.assertEqual(portable, name)


class LongNameTests(unittest.TestCase):
    def test_the_limits(self):
        self.assertIsNone(g.unsafe_file_name_reason('a' * 247 + '.exe'))        # 251 bytes
        self.assertIn('longer than 251 bytes', g.unsafe_file_name_reason('a' * 248 + '.exe'))
        # bytes count, not characters:
        self.assertIsNone(g.unsafe_file_name_reason('\u00e4' * 124 + '.ab'))          # 124 * 2 + 3 = 251 bytes, 127 characters
        self.assertIn('longer than', g.unsafe_file_name_reason('\u4e2d' * 84))         # 84 * 3 = 252 bytes, 84 characters

    def test_names_up_to_251_bytes_are_kept_and_longer_ones_get_240(self):
        keep = 'a' * 247 + '.exe'
        self.assertEqual(g.portable_file_name(keep), keep)
        short = g.portable_file_name('a' * 248 + '.exe')
        self.assertEqual(len(short.encode()), 240)

    def test_extension_is_kept_and_a_character_is_never_cut(self):
        name = '\u4e2d\u6587' * 100 + '.zip'
        short = g.portable_file_name(name)
        self.assertTrue(short.endswith('.zip'))
        self.assertLessEqual(len(short.encode()), 240)
        short.encode('utf-8')                                            # would raise on a cut character
        self.assertNotIn('\ufffd', short)

    def test_a_very_long_extension_is_not_kept(self):
        name = 'a.' + 'e' * 300
        short = g.portable_file_name(name)
        self.assertEqual(len(short.encode()), 240)
        self.assertIsNone(g.unsafe_file_name_reason(short))

    def test_long_names_that_start_alike_stay_different(self):
        a, b = g.portable_file_name('x' * 300 + '_1.exe'), g.portable_file_name('x' * 300 + '_2.exe')
        self.assertNotEqual(a, b)
        self.assertEqual(g.portable_file_name('x' * 300 + '_1.exe'), a)        # the same name always gives the same result

    def test_the_hash_part_is_the_documented_one(self):
        name = 'q' * 300 + '.bin'
        self.assertIn('~' + hashlib.sha1(name.encode()).hexdigest()[:8] + '.bin', g.portable_file_name(name))


class UniqueNameTests(unittest.TestCase):
    def test_free_name_is_kept_and_taken_names_get_a_number(self):
        self.assertEqual(g._unique_portable_name('a.exe', set()), 'a.exe')
        self.assertEqual(g._unique_portable_name('a.exe', {'a.exe'}), 'a(1).exe')
        self.assertEqual(g._unique_portable_name('a.exe', {'a.exe', 'a(1).exe'}), 'a(2).exe')
        self.assertEqual(g._unique_portable_name('A.EXE', {'a.exe'}), 'A(1).EXE')                # case is ignored
        self.assertEqual(g._unique_portable_name('A.EXE', {'a.exe', 'a(1).exe'}), 'A(2).EXE')     # also for the numbered names
        self.assertEqual(g._unique_portable_name('s-1.bin', {'s-1.bin'}), 's(1)-1.bin')           # the rule for GOG's .bin sets


def game(*downloads, **lists):
    entry = g.AttrDict(id=1, title='alpha', folder_name='alpha', downloads=list(downloads), galaxyDownloads=[], sharedDownloads=[], extras=[])
    entry.update(lists)
    return entry


def item(name, **kw):
    return g.AttrDict(name=name, desc=name, size=10, md5=None, old_name=None, **kw)


class MigrationTests(LogCase):
    def test_unsafe_names_are_replaced_and_the_old_name_is_kept_twice(self):
        bad, good = item('setup:2.exe'), item('setup_a.exe')
        self.assertEqual(g.migrate_unsafe_file_names([game(bad, good)]), 1)
        self.assertEqual((bad.name, bad.old_name, bad.name_from_server), ('setup_2.exe', 'setup:2.exe', 'setup:2.exe'))
        self.assertEqual((good.name, good.old_name), ('setup_a.exe', None))
        self.assertNotIn('name_from_server', good)                # only when it differs from the stored name

    def test_all_four_lists_are_covered_and_old_entries_without_lists_do_not_fail(self):
        a, b, c, d = item('a:1.exe'), item('b?.exe'), item('c|.exe'), item('d*.pdf')
        full = game(a, galaxyDownloads=[b], sharedDownloads=[c], extras=[d])
        old = g.AttrDict(id=2, title='old', downloads=[item('e<.exe')])                 # no galaxyDownloads, sharedDownloads, extras
        self.assertEqual(g.migrate_unsafe_file_names([full, old]), 5)
        self.assertEqual([x.name for x in (a, b, c, d)], ['a_1.exe', 'b_.exe', 'c_.exe', 'd_.pdf'])
        self.assertEqual(old.downloads[0].name, 'e_.exe')

    def test_a_second_run_finds_nothing(self):
        games = [game(item('a:b.exe'), item('CON.txt'))]
        self.assertEqual(g.migrate_unsafe_file_names(games), 2)
        self.assertEqual(g.migrate_unsafe_file_names(games), 0)

    def test_items_without_a_name_are_left_alone(self):
        coming_soon = g.AttrDict(name=None, desc='soon', old_name=None)
        self.assertEqual(g.migrate_unsafe_file_names([game(coming_soon)]), 0)
        self.assertIsNone(coming_soon.name)

    def test_a_name_that_another_file_has_already_gets_a_number(self):
        existing, bad, bad2 = item('a_b.exe'), item('a:b.exe'), item('a?b.exe')
        g.migrate_unsafe_file_names([game(existing, bad, bad2)])
        self.assertEqual(existing.name, 'a_b.exe')                                       # the file that was fine keeps its name
        self.assertEqual(sorted([bad.name, bad2.name]), ['a_b(1).exe', 'a_b(2).exe'])
        self.assertEqual(len(set(x.name.lower() for x in (existing, bad, bad2))), 3)

    def test_the_clash_check_ignores_case(self):
        existing, bad = item('A_B.EXE'), item('a:b.exe')
        g.migrate_unsafe_file_names([game(existing, bad)])
        self.assertEqual(bad.name, 'a_b(1).exe')

    def test_a_rename_that_is_already_waiting_keeps_its_older_source(self):
        bad = item('x:y.exe')
        bad.old_name = 'older.exe'
        g.migrate_unsafe_file_names([game(bad)])
        self.assertEqual((bad.name, bad.old_name), ('x_y.exe', 'older.exe'))

    def test_one_log_line_per_file(self):
        g.migrate_unsafe_file_names([game(item('a:b.exe'), item('c?.exe'))])
        lines = [r.getMessage() for r in self.handler.records if 'not portable' in r.getMessage()]
        self.assertEqual(len(lines), 2)


class FetchFileInfoTests(LogCase):
    def fetch(self, url):
        entry = g.AttrDict(href='http://x/d', gog_data=g.AttrDict(), name=None, size=None, updated='2020-01-01T00:00:00+00:00')
        response = SimpleNamespace(url=url, headers={'Content-Length': '123'})
        with mock.patch.object(g, 'request_head', lambda session, href, *a, **k: response):
            g.fetch_file_info(entry, False, False, None)
        return entry

    def test_a_name_from_the_address_is_stored_portable_with_the_original_kept(self):
        entry = self.fetch('http://cdn.test/path/..%2F..%2Fevil%3A1.exe?token=1')
        self.assertEqual(entry.name, '.._.._evil_1.exe')
        self.assertEqual(entry.name_from_server, '../../evil:1.exe')
        self.assertEqual(entry.size, 123)
        self.assertEqual(len([m for m in self.handler.warnings() if 'not portable' in m]), 1)

    def test_a_good_name_gets_no_extra_field_and_no_warning(self):
        entry = self.fetch('http://cdn.test/path/setup_a.exe')
        self.assertEqual(entry.name, 'setup_a.exe')
        self.assertNotIn('name_from_server', entry)
        self.assertEqual([m for m in self.handler.warnings() if 'not portable' in m], [])

    def test_a_stale_field_is_removed_when_the_name_is_fine_now(self):
        entry = g.AttrDict(href='http://x/d', gog_data=g.AttrDict(), name_from_server='old:name.exe', updated='2020-01-01T00:00:00+00:00')
        response = SimpleNamespace(url='http://cdn.test/path/new.exe', headers={'Content-Length': '1'})
        with mock.patch.object(g, 'request_head', lambda session, href, *a, **k: response):
            g.fetch_file_info(entry, False, False, None)
        self.assertNotIn('name_from_server', entry)


class UpdateMigrationTests(trs.TempDirTests):
    """The whole way: a manifest with a name from before 0.5.90, update, then the next command renames the file."""
    def update(self):
        with mock.patch.object(g, 'request', trs.games_api()), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})):
            g.cmd_update(['windows'], ['en'], True, True, True, [], [], False, 'both', 'resume', False, False, False, False, False, False, False)

    def test_update_migrates_the_names_saves_the_manifest_and_reports_it(self):
        self.library({'setup:2.exe': b'a' * 50, 'ok.exe': b'b' * 60})
        self.update()
        entries = {e.name: e for e in g.load_manifest()[0].downloads}
        self.assertEqual(sorted(entries), ['ok.exe', 'setup_2.exe'])
        self.assertEqual((entries['setup_2.exe'].old_name, entries['setup_2.exe'].name_from_server), ('setup:2.exe', 'setup:2.exe'))
        self.assertIsNone(entries['ok.exe'].old_name)
        self.assertNotIn('name_from_server', entries['ok.exe'])
        self.assertEqual(g.run_report.counts['file names made portable'][0], 1)

    def test_the_next_rename_run_moves_the_file_on_disk(self):
        self.library({'setup:2.exe': b'a' * 50})
        if not create_file_named(path_in(os.path.join(self.dir, 'alpha'), 'setup:2.exe'), b'a' * 50):
            self.skipTest('this file system does not keep a colon in a file name (NTFS makes it a stream of the file "setup")')
        self.update()
        items = g.load_manifest()
        g._handle_game_renames_and_save(self.dir, items, False)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, 'alpha'))), ['setup_2.exe'])
        self.assertIsNone(g.load_manifest()[0].downloads[0].old_name)
        self.assertEqual(g.load_manifest()[0].downloads[0].name_from_server, 'setup:2.exe')   # stays, as the record of what the server sent

    def test_the_migrated_manifest_is_saved_at_once_not_only_at_the_end_of_update(self):
        self.library({'setup:2.exe': b'a' * 50})
        with mock.patch.object(g, 'makeGOGSession', side_effect=RuntimeError('stop right after the migration')):
            with self.assertRaises(RuntimeError):
                g.cmd_update(['windows'], ['en'], True, True, True, [], [], False, 'both', 'resume', False, False, False, False, False, False, False)
        self.assertEqual([e.name for e in g.load_manifest()[0].downloads], ['setup_2.exe'])

    def test_a_manifest_that_needs_nothing_is_not_touched(self):
        self.library({'a.exe': b'a' * 50})
        self.update()
        self.assertNotIn('file names made portable', g.run_report.counts)


class RefusalEverywhereTests(trs.TempDirTests):
    """A manifest that was not migrated yet (update not run): no command joins an unsafe name to a folder."""
    def setUp(self):
        super().setUp()
        self.src, self.dest = os.path.join(self.dir, 'src'), os.path.join(self.dir, 'dest')
        self.handler = Capture()
        g.rootLogger.addHandler(self.handler)
        self.addCleanup(g.rootLogger.removeHandler, self.handler)

    def outside(self, folder, name='evil.exe'):
        return os.path.join(folder, name)                       # where 'alpha/../evil.exe' ends up

    def test_verify_refuses_and_touches_nothing(self):
        self.library({'../evil.exe': b'a' * 50, 'a:b.exe': b'b' * 50, 'ok.exe': b'c' * 50})
        self.write(self.dir, 'ok.exe', b'c' * 50)
        with open(self.outside(self.dir), 'wb') as f:
            f.write(b'z' * 50)                                      # would be "verified" through alpha/../evil.exe
        g.cmd_verify(self.dir, False, [], True, True, False, False, False, [], ['windows'], ['en'], False, False, False, [], False, False, False, 0)
        reasons = {what: why for what, why in g.run_report.failures}
        self.assertEqual(sorted(reasons), ['alpha/../evil.exe', 'alpha/a:b.exe'])
        self.assertTrue(all(why.startswith('refused, ') for why in reasons.values()))
        with open(self.outside(self.dir), 'rb') as f:
            self.assertEqual(f.read(), b'z' * 50)

    def test_backup_refuses_and_copies_nothing_outside(self):
        self.library({'../evil.exe': b'a' * 50, 'ok.exe': b'c' * 50})
        self.write(self.src, 'ok.exe', b'c' * 50)
        with open(self.outside(self.src), 'wb') as f:
            f.write(b'a' * 50)
        g.cmd_backup(self.src, self.dest, False, ['windows'], ['en'], [], [], False, False, False)
        self.assertFalse(os.path.exists(self.outside(self.dest)))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, 'alpha', 'ok.exe')))
        self.assertEqual([what for what, why in g.run_report.failures], ['alpha/../evil.exe'])

    def test_import_refuses_and_writes_nothing_outside(self):
        self.library({'../evil.exe': b'a' * 50, 'ok.exe': b'c' * 50})
        self.write(self.src, 'x.exe', b'a' * 50)                   # matches the entry with the bad name by size and md5
        self.write(self.src, 'ok.exe', b'c' * 50)
        g.cmd_import(self.src, self.dest, ['windows'], ['en'], False, [], [], False, False, False, False)
        self.assertFalse(os.path.exists(self.outside(self.dest)))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, 'alpha', 'ok.exe')))
        self.assertEqual([what for what, why in g.run_report.failures], ['alpha/../evil.exe'])

    def test_rename_handling_refuses_a_bad_new_name_and_forgets_a_bad_old_name(self):
        os.makedirs(os.path.join(self.dir, 'alpha'))
        bad_new, bad_old = item('a:b.exe'), item('fine.exe')
        bad_new.old_name, bad_old.old_name = 'before.exe', '../../before.exe'
        for name in ('before.exe', 'fine.exe'):
            with open(os.path.join(self.dir, 'alpha', name), 'wb') as f:
                f.write(b'x')
        games = [game(bad_new, bad_old)]
        self.assertTrue(g.handle_game_renames(self.dir, games, False))
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, 'alpha'))), ['before.exe', 'fine.exe'])      # nothing moved
        self.assertEqual(bad_new.old_name, 'before.exe')                                                    # waits for update
        self.assertIsNone(bad_old.old_name)                                                                 # nothing to wait for
        self.assertEqual([what for what, why in g.run_report.failures], ['alpha/a:b.exe'])

    def test_rename_handling_in_a_dry_run_keeps_the_markers(self):
        os.makedirs(os.path.join(self.dir, 'alpha'))
        bad_old = item('fine.exe')
        bad_old.old_name = '../x.exe'
        g.handle_game_renames(self.dir, [game(bad_old)], True)
        self.assertEqual(bad_old.old_name, '../x.exe')

    def test_md5_xml_files_are_not_written_for_unsafe_names(self):
        def entry(name):
            e = item(name, lang='English', os_type='windows')
            e.gog_data = g.AttrDict(md5_xml=g.AttrDict(text='<file/>'))
            e.provisional_name = None
            return e
        extras = [entry('../evil.pdf'), entry('manual.pdf')]
        g.save_manifest([game(entry('../evil.exe'), entry('good.exe'), entry('a:b.exe'), extras=extras)], update_md5_xml=True)
        root = os.path.join(g.MD5_DIR_NAME, 'alpha')
        folder = os.path.join(root, 'downloads', 'windows')
        self.assertTrue(os.path.isfile(os.path.join(folder, 'English', 'good.exe.xml')))
        self.assertTrue(os.path.isfile(os.path.join(root, 'extras', 'manual.pdf.xml')))
        self.assertEqual(sorted(glob.glob(os.path.join(g.MD5_DIR_NAME, '**', '*evil*'), recursive=True)), [])      # nowhere in the MD5 folder, also not one folder up
        self.assertFalse(os.path.exists(path_in(os.path.join(folder, 'English'), 'a:b.exe.xml')))
        g.flush_summarised()
        notes = [m for m in self.handler.warnings() if 'MD5 XML data of 3 file(s) was not saved' in m]
        self.assertEqual(len(notes), 1, self.handler.warnings())

    def test_the_multi_part_zip_lookup_escapes_the_name(self):
        folder = os.path.join(self.dir, 'z')
        os.makedirs(folder)
        for part in ('x [1].zip.001', 'x [1].zip.002', 'x 1.zip.003'):
            with open(os.path.join(folder, part), 'wb') as f:
                f.write(b'x')
        found = g._multi_zip_parts('x [1].zip.001', os.path.join(folder, 'x [1].zip.001'))
        self.assertEqual(sorted(found), ['x [1].zip.001', 'x [1].zip.002'])


if __name__ == '__main__':
    unittest.main()
