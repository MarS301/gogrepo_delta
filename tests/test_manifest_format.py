"""Manifest file formats (readable, fast JSON and the original text format), migration, and the export command."""
import contextlib
import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g


def sample_items(count=3):
    items = []
    for i in range(count):
        download = g.AttrDict(name='setup_%d.exe' % i, desc='Installer', version='1.2', size=1234567 + i, href='https://www.gog.com/downloads/g/%d' % i, md5='%032x' % i,
                              lang='English', os_type='windows', updated='2020-01-01T00:00:00+00:00', unreleased=False, force_change=False, prev_verified=True,
                              gog_data=g.AttrDict(md5_xml=g.AttrDict(text='<file name="setup_%d.exe"/>' % i), size='1 MB'))
        items.append(g.AttrDict(id=1000 + i, title='game_%d' % i, long_title='Ünïcödé: the long title %d' % i, genre='RPG', store_url='/game/g%d' % i, rating=45,
                                changelog='it\'s "quoted"; {braces} and\nnew lines\tand tabs', serials=g.AttrDict(key='AAAA-BBBB'), has_updates=False, serial='',
                                downloads=[download], galaxyDownloads=[], sharedDownloads=[],
                                extras=[g.AttrDict(name='manual.pdf', desc='Manual', size=999, md5=None, updated='2020', unreleased=False)], folder_name='game_%d' % i))
    return items


class TempDirTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)

    def text(self, path=g.MANIFEST_FILENAME):
        with open(path, encoding='utf-8') as f:
            return f.read()

    def save_as(self, fmt, items, path=g.MANIFEST_FILENAME):
        with mock.patch.object(g, 'MANIFEST_FORMAT', fmt):
            g.save_manifest(items, path)


class JsonFormatTests(TempDirTests):
    def test_round_trip_gives_identical_items(self):
        items = sample_items()
        self.save_as('json', items)
        self.assertEqual(g.load_manifest(), items)

    def test_the_file_is_readable_text(self):
        self.save_as('json', sample_items(1))
        text = self.text()
        self.assertTrue(text.startswith('{'))
        self.assertIn('"title": "game_0"', text)
        self.assertIn('Ünïcödé', text)                      # special characters are not escaped
        self.assertGreater(text.count('\n'), 40)              # one field per line, not one long line
        self.assertEqual(json.loads(text)['games'], 1)        # a normal JSON file, any tool can read it

    def test_loaded_items_support_attribute_access_at_every_level(self):
        self.save_as('json', sample_items(1))
        item = g.load_manifest()[0]
        self.assertEqual(item.downloads[0].gog_data.md5_xml.text, '<file name="setup_0.exe"/>')
        self.assertEqual(item.serials.key, 'AAAA-BBBB')
        self.assertIsInstance(item.downloads[0], g.AttrDict)

    def test_special_characters_survive(self):
        items = sample_items(1)
        items[0].changelog = 'braces {} "quotes" \'single\' \\ backslash \u2603 \U0001F600 </script>'
        self.save_as('json', items)
        self.assertEqual(g.load_manifest()[0].changelog, items[0].changelog)

    def test_braces_in_titles_survive(self):
        # the old text loader misreads braces outside changelogs; JSON does not care
        items = sample_items(1)
        items[0].title = 'Game {Special} Edition'
        items[0].long_title = '{{nested}} and } alone'
        self.save_as('json', items)
        self.assertEqual(g.load_manifest(), items)

    def test_a_key_named_self_works(self):
        items = [g.AttrDict(id=1, title='t', downloads=[], extras=[])]
        items[0]['self'] = 'x'
        self.save_as('json', items)
        self.assertEqual(g.load_manifest()[0]['self'], 'x')

    def test_empty_manifest(self):
        self.save_as('json', [])
        self.assertEqual(g.load_manifest(), [])

    def test_keys_are_sorted_like_the_old_format(self):
        self.save_as('json', sample_items(1))
        keys = list(json.loads(self.text())['items'][0])
        self.assertEqual(keys, sorted(keys))


class OldFormatTests(TempDirTests):
    def test_the_old_format_can_still_be_written_and_read(self):
        items = sample_items()
        self.save_as('legacy', items)
        self.assertTrue(self.text().startswith('# 3 games'))
        self.assertEqual(g.load_manifest(), items)

    def test_both_formats_load_to_the_same_items(self):
        items = sample_items()
        self.save_as('legacy', items, 'old.dat')
        self.save_as('json', items, 'new.dat')
        self.assertEqual(g.load_manifest('old.dat'), g.load_manifest('new.dat'))

    def test_a_hand_made_old_format_file_with_python2_integers_loads(self):
        with open('gog-manifest.dat', 'w', encoding='utf-8') as f:
            f.write("# 1 games\n[{'id': 7, 'title': 't', 'size': 12L, 'downloads': [], 'extras': []}]\n")
        self.assertEqual(g.load_manifest()[0].size, 12)


class MigrationTests(TempDirTests):
    def test_first_json_save_keeps_a_copy_of_the_old_file(self):
        items = sample_items()
        self.save_as('legacy', items)
        original = self.text()
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            self.save_as('json', items)
        self.assertTrue(self.text().startswith('{'))
        self.assertEqual(self.text(g.MANIFEST_FILENAME + '.legacy'), original)
        self.assertTrue(any('old-format file was kept' in m for m in logs.output))

    def test_the_copy_is_made_only_once_and_never_overwritten(self):
        self.save_as('legacy', sample_items(2))
        original = self.text()
        self.save_as('json', sample_items(3))
        self.save_as('json', sample_items(4))
        self.assertEqual(self.text(g.MANIFEST_FILENAME + '.legacy'), original)

    def test_no_copy_when_the_file_is_already_json(self):
        self.save_as('json', sample_items())
        self.save_as('json', sample_items())
        self.assertFalse(os.path.exists(g.MANIFEST_FILENAME + '.legacy'))

    def test_previous_version_stays_available_as_bak(self):
        self.save_as('legacy', sample_items(2))
        old_text = self.text()
        self.save_as('json', sample_items(3))
        self.assertEqual(self.text(g.MANIFEST_FILENAME + '.bak'), old_text)

    def test_a_failed_backup_means_no_switch(self):
        items = sample_items()
        self.save_as('legacy', items)
        real_copyfile = shutil.copyfile

        def copyfile_failing_for_the_legacy_copy(src, dst, *a, **k):
            if dst.endswith(g.LEGACY_BACKUP_EXT):
                raise OSError('disk full')
            return real_copyfile(src, dst, *a, **k)
        with mock.patch.object(g.shutil, 'copyfile', copyfile_failing_for_the_legacy_copy), self.assertLogs('gogrepoc', level='WARNING') as logs:
            self.save_as('json', items)
        self.assertTrue(self.text().startswith('# 3 games'))
        self.assertTrue(any('not switching to the JSON format' in m for m in logs.output))
        self.assertEqual(g.load_manifest(), items)

    def test_switching_back_to_the_old_format(self):
        items = sample_items()
        self.save_as('json', items)
        self.save_as('legacy', items)
        self.assertTrue(self.text().startswith('# 3 games'))
        self.assertEqual(g.load_manifest(), items)


class SafetyFallbackTests(TempDirTests):
    def assertFallsBack(self, items):
        with self.assertLogs('gogrepoc', level='WARNING') as logs:
            self.save_as('json', items)
        self.assertTrue(self.text().startswith('# '), 'the old format must be used')
        self.assertTrue(any('old format for this save' in m for m in logs.output))

    def test_tuples_would_change_so_the_old_format_is_used(self):
        items = sample_items(1)
        items[0].pair = (1, 2)
        self.assertFallsBack(items)
        self.assertEqual(g.load_manifest()[0].pair, (1, 2))     # and nothing is lost

    def test_non_text_keys_use_the_old_format(self):
        items = sample_items(1)
        items[0].mapping = {1: 'a', 2: 'b'}
        self.assertFallsBack(items)

    def test_values_json_cannot_hold_use_the_old_format(self):
        for bad in (float('nan'), float('inf'), {1, 2}, b'bytes'):
            items = sample_items(1)
            items[0].value = bad
            self.assertIsNone(g.manifest_to_json(items, 1), repr(bad))

    def test_a_good_manifest_is_not_reported(self):
        self.assertIsNotNone(g.manifest_to_json(sample_items(), 3))

    def test_a_damaged_json_file_gives_a_clear_message_and_exits(self):
        self.save_as('json', sample_items())
        damaged = self.text()[:-40]
        with open(g.MANIFEST_FILENAME, 'w', encoding='utf-8') as f:
            f.write(damaged)
        with self.assertLogs('gogrepoc', level='ERROR') as logs, self.assertRaises(SystemExit):
            g.load_manifest()
        text = '\n'.join(logs.output)
        self.assertIn('is damaged', text)
        self.assertIn('no backup copy', text.lower().replace('there is no backup copy', 'no backup copy'))
        self.assertIn('.bak', text)

    def test_interrupting_a_json_save_keeps_the_previous_manifest(self):
        self.save_as('json', sample_items(2))
        before = self.text()
        with mock.patch.object(g.json, 'dumps', side_effect=KeyboardInterrupt()), self.assertRaises(KeyboardInterrupt):
            self.save_as('json', sample_items(5))
        self.assertEqual(self.text(), before)
        self.assertEqual([f for f in os.listdir('.') if f.endswith('.tmp')], [])


class ResumeManifestTests(TempDirTests):
    def resume_items(self):
        return sample_items(2) + [g.AttrDict(complete=False, os_list=['windows'], lang_list=['de'], lang_fallback='en', installers='standalone')]

    def test_resume_manifest_round_trip_and_game_count(self):
        items = self.resume_items()
        with mock.patch.object(g, 'MANIFEST_FORMAT', 'json'):
            g.save_resume_manifest(items)
        self.assertEqual(g.load_resume_manifest(), items)
        self.assertEqual(json.loads(self.text(g.RESUME_MANIFEST_FILENAME))['games'], 2)    # the properties entry is not a game

    def test_an_old_format_resume_file_loads(self):
        items = self.resume_items()
        for item in items[:2]:
            item.changelog = 'plain changelog text'        # the old resume loader misreads braces in any text; JSON does not
        with mock.patch.object(g, 'MANIFEST_FORMAT', 'legacy'):
            g.save_resume_manifest(items)
        self.assertEqual(g.load_resume_manifest(), items)


class OptionTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, g, 'MANIFEST_FORMAT', g.MANIFEST_FORMAT)

    def parse(self, *argv):
        return g.process_argv(['gogrepo_delta.py'] + list(argv) + ['-nolog'])

    def test_default_is_json_for_every_command(self):
        for argv in (['update'], ['download', 'd'], ['verify', 'd'], ['clean', 'd'], ['export'], ['import', 's', 'd'], ['backup', 's', 'd']):
            self.assertEqual(self.parse(*argv).manifestformat, 'json', argv)

    def test_legacy_can_be_chosen_in_both_spellings(self):
        self.assertEqual(self.parse('update', '-manifestformat', 'legacy').manifestformat, 'legacy')
        self.assertEqual(self.parse('update', '--manifestformat', 'legacy').manifestformat, 'legacy')

    def test_unknown_formats_are_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse('update', '-manifestformat', 'xml')

    def test_main_applies_the_choice(self):
        args = self.parse('clean', 'somedir', '-manifestformat', 'legacy')
        with mock.patch.object(g, 'cmd_clean'):
            g.main(args)
        self.assertEqual(g.MANIFEST_FORMAT, 'legacy')


class ExportTests(TempDirTests):
    def make_library(self):
        items = sample_items(2)
        items[1].downloads.append(g.AttrDict(name='odd; name "x".exe', desc='d', version='', size=None, md5=None, lang='Deutsch', os_type='linux', updated='2021'))
        items[1].extras.append(g.AttrDict(name=None, desc='unnamed', size=5, md5=None, updated='2021', unreleased=True))
        self.save_as('json', items)
        return items

    def rows(self, path='gog-library.csv', delimiter=','):
        with open(path, encoding='utf-8-sig', newline='') as f:
            return list(csv.reader(f, delimiter=delimiter))

    def test_one_row_per_file_with_readable_columns(self):
        self.make_library()
        g.cmd_export('gog-library.csv', None, ',')
        rows = self.rows()
        self.assertEqual(rows[0][:6], ['game id', 'title', 'folder', 'kind', 'file', 'operating system'])
        self.assertEqual(len(rows), 1 + 2 + 4)           # header, game_0: installer + manual, game_1: 2 installers + 2 extras (one unnamed)
        first = rows[1]
        self.assertEqual((first[1], first[3], first[4], first[5], first[6]), ('game_0', 'standalone', 'setup_0.exe', 'windows', 'English'))
        self.assertEqual(first[8:10], ['1234567', '1.18MB'])

    def test_extras_have_no_system_or_language(self):
        self.make_library()
        g.cmd_export('gog-library.csv', None, ',')
        extras = [r for r in self.rows() if r[3] == 'extra']
        self.assertTrue(extras)
        for row in extras:
            self.assertEqual((row[5], row[6]), ('', ''))

    def test_special_characters_and_missing_values_are_handled(self):
        self.make_library()
        g.cmd_export('gog-library.csv', None, ';')
        rows = self.rows(delimiter=';')
        odd = [r for r in rows if r[4] == 'odd; name "x".exe'][0]
        self.assertEqual((odd[5], odd[6], odd[8], odd[9]), ('linux', 'Deutsch', '', ''))
        self.assertTrue(any(r[4] == '' and r[3] == 'extra' for r in rows))

    def test_the_file_starts_with_a_byte_order_mark_for_excel(self):
        self.make_library()
        g.cmd_export('gog-library.csv', None, ',')
        with open('gog-library.csv', 'rb') as f:
            self.assertEqual(f.read(3), b'\xef\xbb\xbf')

    def test_on_disk_column(self):
        items = self.make_library()
        os.makedirs('lib/game_0')
        with open('lib/game_0/setup_0.exe', 'wb') as f:
            f.write(b'x' * (1234567 + 0))                  # right size
        with open('lib/game_0/manual.pdf', 'wb') as f:
            f.write(b'x')                                  # wrong size
        g.cmd_export('gog-library.csv', 'lib', ',')
        rows = {(r[1], r[4]): r[12] for r in self.rows()[1:]}
        self.assertEqual(rows[('game_0', 'setup_0.exe')], 'yes')
        self.assertEqual(rows[('game_0', 'manual.pdf')], 'wrong size')
        self.assertEqual(rows[('game_1', 'setup_1.exe')], 'no')
        self.assertEqual(rows[('game_1', '')], '')       # unnamed entries cannot be checked
        self.assertEqual(self.rows()[0][-1], 'on disk')

    def test_without_a_game_directory_there_is_no_disk_column(self):
        self.make_library()
        g.cmd_export('gog-library.csv', None, ',')
        self.assertNotIn('on disk', self.rows()[0])

    def test_default_separator_depends_on_the_language(self):
        for lang, expected in (('de', ';'), ('fr', ';'), ('pl', ';'), ('en', ','), ('jp', ','), ('cn', ',')):
            with mock.patch.object(g, 'detect_lang', return_value=(lang, 'test')):
                self.assertEqual(g.default_csv_delimiter(), expected, lang)

    def test_an_explicit_separator_wins(self):
        self.make_library()
        with mock.patch.object(g, 'detect_lang', return_value=('de', 'test')):
            g.cmd_export('gog-library.csv', None, '\t')
        self.assertIn('\t', self.text('gog-library.csv'))

    def test_the_command_is_wired_up(self):
        args = g.process_argv(['gogrepo_delta.py', 'export', '-output', 'x.csv', '-savedir', 'lib', '-delimiter', ',', '-nolog'])
        with mock.patch.object(g, 'cmd_export') as called:
            g.main(args)
        called.assert_called_once_with('x.csv', 'lib', ',')

    def test_export_does_not_change_the_manifest(self):
        self.make_library()
        before = self.text()
        g.cmd_export('gog-library.csv', None, ',')
        self.assertEqual(self.text(), before)


if __name__ == '__main__':
    unittest.main()
