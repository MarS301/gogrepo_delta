import logging
import unittest
import _bootstrap  # noqa: F401
from gogrepo_delta import AttrDict
from gogrepo_delta import (item_checkdb, makeDeDuplicateName, deDuplicateName,
                      deDuplicateList, handle_game_updates, numbered_name, move_with_increment_on_clash)

T1 = '2020-01-01T00:00:00+00:00'
T2 = '2021-06-01T12:00:00+00:00'


def dl(name='setup.exe', md5='m1', size=100, lang='en', updated=T1, **extra):
    d = AttrDict(name=name, md5=md5, size=size, lang=lang, updated=updated, unreleased=False)
    d.update(extra)
    return d


def extra_file(name='manual.pdf', md5='e1', size=10, updated=T1, **extra):
    d = AttrDict(name=name, md5=md5, size=size, updated=updated, unreleased=False)
    d.update(extra)
    return d


def game(downloads=(), extras=(), **over):
    g = AttrDict(title='Game', long_title='Game: Long', changelog='', has_updates=False, serial='',
                 downloads=list(downloads), galaxyDownloads=[], sharedDownloads=[], extras=list(extras))
    g.update(over)
    return g


class ItemCheckdbTests(unittest.TestCase):
    def test_returns_index_of_matching_id(self):
        db = [AttrDict(id=1), AttrDict(id=5), AttrDict(id=9)]
        self.assertEqual(item_checkdb(5, db), 1)
        self.assertEqual(item_checkdb(9, db), 2)

    def test_unknown_id_and_empty_db(self):
        self.assertIsNone(item_checkdb(2, [AttrDict(id=1)]))
        self.assertIsNone(item_checkdb(1, []))


class MakeDeDuplicateNameTests(unittest.TestCase):
    def test_counter_goes_before_the_extension(self):
        self.assertEqual(makeDeDuplicateName('setup.exe', 1), 'setup(1).exe')
        self.assertEqual(makeDeDuplicateName('setup.exe', 3), 'setup(3).exe')

    def test_only_the_last_extension_is_used(self):
        self.assertEqual(makeDeDuplicateName('archive.tar.gz', 1), 'archive.tar(1).gz')

    def test_bin_parts_keep_their_part_number_last(self):
        self.assertEqual(makeDeDuplicateName('setup-1.bin', 2), 'setup(2)-1.bin')

    def test_names_without_extension_do_not_raise(self):
        self.assertEqual(makeDeDuplicateName('README', 1), 'README(1)')
        self.assertEqual(makeDeDuplicateName('checksums', 3), 'checksums(3)')

    def test_dotfiles_keep_their_name_and_get_the_counter_at_the_end(self):
        self.assertEqual(makeDeDuplicateName('.hidden', 1), '.hidden(1)')

    def test_bin_without_part_number_is_treated_like_other_files(self):
        self.assertEqual(makeDeDuplicateName('data.bin', 1), 'data(1).bin')
        self.assertEqual(makeDeDuplicateName('my-game.bin', 1), 'my-game(1).bin')   # '-' belongs to the name


class NumberedNameTests(unittest.TestCase):
    def test_plain_files(self):
        self.assertEqual(numbered_name('setup', '.exe', 2), 'setup(2).exe')

    def test_no_extension(self):
        self.assertEqual(numbered_name('README', '', 1), 'README(1)')

    def test_bin_part_numbers_stay_last(self):
        self.assertEqual(numbered_name('setup-1', '.bin', 2), 'setup(2)-1.bin')

    def test_bin_with_dash_in_name_but_no_part_number(self):
        self.assertEqual(numbered_name('my-game', '.bin', 1), 'my-game(1).bin')

    def test_numeric_bin_root_without_dash(self):
        self.assertEqual(numbered_name('123', '.bin', 1), '123(1).bin')


class DeDuplicateNameTests(unittest.TestCase):
    def item(self, name='a.exe', size=1, md5='m1'):
        return AttrDict(name=name, size=size, md5=md5)

    def test_first_item_keeps_its_name(self):
        clash = {}
        self.assertEqual(deDuplicateName(self.item(), clash, False), 'a.exe')
        self.assertEqual(clash, {'a.exe': {1: ['m1']}})

    def test_same_size_and_md5_is_a_duplicate(self):
        clash = {}
        deDuplicateName(self.item(), clash, False)
        self.assertIsNone(deDuplicateName(self.item(), clash, False))

    def test_different_md5_is_renamed(self):
        clash = {}
        deDuplicateName(self.item(md5='m1'), clash, False)
        self.assertEqual(deDuplicateName(self.item(md5='m2'), clash, False), 'a(1).exe')

    def test_different_size_is_renamed_with_running_count(self):
        clash = {}
        deDuplicateName(self.item(md5='m1'), clash, False)
        deDuplicateName(self.item(md5='m2'), clash, False)
        self.assertEqual(deDuplicateName(self.item(size=2, md5='m3'), clash, False), 'a(2).exe')

    def test_unknown_md5_matches_by_size_unless_strict(self):
        clash = {}
        deDuplicateName(self.item(md5='m1'), clash, False)
        self.assertIsNone(deDuplicateName(self.item(md5=None), clash, False))
        strict_clash = {}
        deDuplicateName(self.item(md5='m1'), strict_clash, True)
        self.assertEqual(deDuplicateName(self.item(md5=None), strict_clash, True), 'a(1).exe')


class DeDuplicateListTests(unittest.TestCase):
    def test_exact_duplicate_is_dropped_and_logged(self):
        items = [AttrDict(name='a.exe', size=1, md5='m'), AttrDict(name='a.exe', size=1, md5='m')]
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            result = deDuplicateList(items, {}, False)
        self.assertEqual(len(result), 1)
        self.assertTrue(any('same size/md5' in m for m in logs.output))

    def test_clash_with_different_content_is_renamed_in_place_and_logged(self):
        first, second = AttrDict(name='a.exe', size=1, md5='m1'), AttrDict(name='a.exe', size=1, md5='m2')
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            result = deDuplicateList([first, second], {}, False)
        self.assertEqual([i.name for i in result], ['a.exe', 'a(1).exe'])
        self.assertEqual(second.name, 'a(1).exe')
        self.assertTrue(any('renamed to a(1).exe' in m for m in logs.output))

    def test_placeholder_without_name_passes_through(self):
        placeholder = AttrDict(name=None, size=None, md5=None)
        self.assertEqual(deDuplicateList([placeholder], {}, False), [placeholder])

    def test_existing_items_are_taken_into_account(self):
        existing = {}
        deDuplicateList([AttrDict(name='a.exe', size=1, md5='m')], existing, False)
        with self.assertLogs('gogrepoc', level='INFO'):
            self.assertEqual(deDuplicateList([AttrDict(name='a.exe', size=1, md5='m')], existing, False), [])


class HandleGameUpdatesTests(unittest.TestCase):
    def update(self, old, new, strict=False, downloads_strict=False, extras_strict=False):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            logging.getLogger('gogrepoc').info('(marker so assertLogs never fails on silence)')
            handle_game_updates(old, new, strict, downloads_strict, extras_strict)
        return [m for m in logs.output if 'marker' not in m]

    # ---- game level -------------------------------------------------
    def test_missing_attributes_on_old_item_get_defaults(self):
        old = AttrDict(title='Game', long_title='x', changelog='', serial='', downloads=[], extras=[])
        new = game()
        self.update(old, new)
        self.assertEqual((old.galaxyDownloads, old.sharedDownloads, old.folder_name), ([], [], 'Game'))

    def test_title_change_is_logged_and_remembered(self):
        old, new = game(title='Old'), game(title='New')
        messages = self.update(old, new)
        self.assertEqual(new.old_title, 'Old')
        self.assertTrue(any('title has changed' in m for m in messages))

    def test_folder_name_change_is_remembered(self):
        old, new = game(folder_name='a'), game(folder_name='b')
        self.update(old, new)
        self.assertEqual(new.old_folder_name, 'a')

    def test_gog_update_flag_and_changelog_are_logged(self):
        old, new = game(changelog='v1'), game(changelog='v2', has_updates=True)
        messages = ' '.join(self.update(old, new))
        self.assertIn('gog flagged this game as updated', messages)
        self.assertIn('changelog was updated', messages)

    def test_empty_new_changelog_is_not_reported(self):
        messages = ' '.join(self.update(game(changelog='v1'), game(changelog='')))
        self.assertNotIn('changelog was updated', messages)

    def test_serial_changes_are_logged(self):
        messages = ' '.join(self.update(game(serials={'k': 1}), game(serials={'k': 2})))
        self.assertIn('serial key(s) have changed', messages)

    # ---- downloads --------------------------------------------------
    def test_new_download_is_marked_for_change(self):
        new = game(downloads=[dl()])
        self.update(game(), new)
        self.assertTrue(new.downloads[0].force_change)

    def test_identical_download_is_not_marked_and_keeps_verified_state(self):
        old = game(downloads=[dl(prev_verified=True)])
        new = game(downloads=[dl(updated=T2)])
        self.update(old, new)
        d = new.downloads[0]
        self.assertFalse(d.force_change)
        self.assertTrue(d.prev_verified)
        self.assertEqual(d.updated, d.old_updated)       # matching md5 means the new timestamp does not matter

    def test_renamed_download_with_same_md5_is_tracked_not_changed(self):
        old, new = game(downloads=[dl(name='old.exe')]), game(downloads=[dl(name='new.exe')])
        messages = ' '.join(self.update(old, new))
        d = new.downloads[0]
        self.assertEqual(d.old_name, 'old.exe')
        self.assertFalse(d.force_change)
        self.assertIn('a download has changed name', messages)

    def test_download_with_new_md5_counts_as_a_new_file(self):
        old, new = game(downloads=[dl(md5='a')]), game(downloads=[dl(md5='b')])
        self.update(old, new)
        self.assertTrue(new.downloads[0].force_change)

    def test_download_matching_is_per_language(self):
        old, new = game(downloads=[dl(lang='en')]), game(downloads=[dl(lang='de')])
        self.update(old, new)
        self.assertTrue(new.downloads[0].force_change)

    def test_unknown_old_md5_matches_by_name_and_size(self):
        old = game(downloads=[dl(md5=None, prev_verified=True)])
        new = game(downloads=[dl(md5='a')])
        self.update(old, new)
        self.assertFalse(new.downloads[0].force_change)
        self.assertTrue(new.downloads[0].prev_verified)

    def test_strict_clears_previous_verification_for_unknown_md5(self):
        old = game(downloads=[dl(md5=None, prev_verified=True)])
        new = game(downloads=[dl(md5='a')])
        self.update(old, new, strict=True)
        self.assertFalse(new.downloads[0].prev_verified)

    def test_strict_downloads_update_marks_newer_download_for_change(self):
        old = game(downloads=[dl(md5=None, updated=T1, old_updated=T1)])
        new = game(downloads=[dl(md5=None, updated=T2)])
        messages = ' '.join(self.update(old, new, downloads_strict=True))
        self.assertTrue(new.downloads[0].force_change)
        self.assertIn('has probably been updated', messages)

    def test_without_strict_downloads_update_a_newer_timestamp_is_ignored(self):
        old = game(downloads=[dl(md5=None, updated=T1, old_updated=T1)])
        new = game(downloads=[dl(md5=None, updated=T2)])
        self.update(old, new, downloads_strict=False)
        self.assertFalse(new.downloads[0].force_change)

    def test_strict_downloads_update_ignores_an_older_timestamp(self):
        old = game(downloads=[dl(md5=None, updated=T2, old_updated=T2)])
        new = game(downloads=[dl(md5=None, updated=T1)])
        self.update(old, new, downloads_strict=True)
        self.assertFalse(new.downloads[0].force_change)

    def test_galaxy_and_shared_downloads_are_matched_too(self):
        old = game(galaxyDownloads=[dl(name='g.exe')], sharedDownloads=[dl(name='s.exe', md5='s')])
        new = game(galaxyDownloads=[dl(name='g.exe')], sharedDownloads=[dl(name='s.exe', md5='s')])
        self.update(old, new)
        self.assertFalse(new.galaxyDownloads[0].force_change)
        self.assertFalse(new.sharedDownloads[0].force_change)

    # ---- extras -----------------------------------------------------
    def test_new_extra_is_marked_for_change(self):
        new = game(extras=[extra_file()])
        self.update(game(), new)
        self.assertTrue(new.extras[0].force_change)

    def test_identical_extra_is_left_alone(self):
        old = game(extras=[extra_file(prev_verified=True)])
        new = game(extras=[extra_file()])
        self.update(old, new)
        self.assertFalse(new.extras[0].force_change)
        self.assertTrue(new.extras[0].prev_verified)

    def test_renamed_extra_is_tracked(self):
        old, new = game(extras=[extra_file(name='a.pdf')]), game(extras=[extra_file(name='b.pdf')])
        messages = ' '.join(self.update(old, new))
        self.assertEqual(new.extras[0].old_name, 'a.pdf')
        self.assertIn('an extra has changed name', messages)

    def test_strict_extras_update_marks_newer_extra(self):
        old = game(extras=[extra_file(md5=None, updated=T1, old_updated=T1)])
        new = game(extras=[extra_file(md5=None, updated=T2)])
        self.update(old, new, extras_strict=True)
        self.assertTrue(new.extras[0].force_change)


if __name__ == '__main__':
    unittest.main()
