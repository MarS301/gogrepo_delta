import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as app
from gogrepo_delta import AttrDict


class GameRenameTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = self.tempdir.name
        self.game_dir = os.path.join(self.root, 'Game')
        os.makedirs(self.game_dir)

    def tearDown(self):
        self.tempdir.cleanup()

    def write(self, name, content):
        path = os.path.join(self.game_dir, name)
        with open(path, 'wb') as stream:
            stream.write(content)
        return path

    def item(self, old_name, name, content):
        return AttrDict(old_name=old_name, name=name, size=len(content),
                        md5=hashlib.md5(content).hexdigest(), prev_verified=True)

    def game(self, downloads, **kwargs):
        values = dict(id=1, title='Game', folder_name='Game', old_folder_name=None,
                      downloads=downloads, galaxyDownloads=[], sharedDownloads=[], extras=[])
        values.update(kwargs)
        return AttrDict(**values)

    def test_file_rename_clears_old_name_and_reports_manifest_change(self):
        content = b'installer bytes'
        self.write('old.exe', content)
        download = self.item('old.exe', 'new.exe', content)

        changed = app.handle_game_renames(self.root, [self.game([download])], False)

        self.assertTrue(changed)
        self.assertIsNone(download.old_name)
        with open(os.path.join(self.game_dir, 'new.exe'), 'rb') as stream:
            self.assertEqual(stream.read(), content)
        self.assertFalse(os.path.exists(os.path.join(self.game_dir, 'old.exe')))

    def test_correct_destination_is_recognized_without_orphaning_it(self):
        content = b'correct destination'
        self.write('old.exe', b'old source')
        self.write('new.exe', content)
        download = self.item('old.exe', 'new.exe', content)

        changed = app.handle_game_renames(self.root, [self.game([download])], False)

        self.assertTrue(changed)
        self.assertIsNone(download.old_name)
        self.assertTrue(os.path.isfile(os.path.join(self.game_dir, 'old.exe')))
        with open(os.path.join(self.game_dir, 'new.exe'), 'rb') as stream:
            self.assertEqual(stream.read(), content)
        self.assertFalse(os.path.exists(os.path.join(self.root, app.ORPHAN_DIR_NAME)))

    def test_two_file_circular_rename_swaps_files_without_losing_either(self):
        content_a = b'content originally named A'
        content_b = b'content originally named B'
        self.write('A.bin', content_a)
        self.write('B.bin', content_b)
        # Each destination is occupied by the other file, and neither has the
        # expected checksum for that destination.
        item_a = self.item('A.bin', 'B.bin', content_a)
        item_b = self.item('B.bin', 'A.bin', content_b)

        changed = app.handle_game_renames(self.root, [self.game([item_a, item_b])], False)

        self.assertTrue(changed)
        self.assertIsNone(item_a.old_name)
        self.assertIsNone(item_b.old_name)
        with open(os.path.join(self.game_dir, 'A.bin'), 'rb') as stream:
            self.assertEqual(stream.read(), content_b)
        with open(os.path.join(self.game_dir, 'B.bin'), 'rb') as stream:
            self.assertEqual(stream.read(), content_a)
        self.assertFalse([name for name in os.listdir(self.game_dir) if name.startswith('.gogrepo-rename-')])

    def test_three_file_circular_rename_keeps_all_payloads(self):
        contents = {name: ("payload-" + name).encode("ascii") for name in ("A", "B", "C")}
        for name, content in contents.items():
            self.write(name + ".bin", content)
        items = [self.item("A.bin", "B.bin", contents["A"]),
                 self.item("B.bin", "C.bin", contents["B"]),
                 self.item("C.bin", "A.bin", contents["C"])]

        changed = app.handle_game_renames(self.root, [self.game(items)], False)

        self.assertTrue(changed)
        for item in items:
            self.assertIsNone(item.old_name)
        expected = {"A.bin": contents["C"], "B.bin": contents["A"], "C.bin": contents["B"]}
        for name, content in expected.items():
            with open(os.path.join(self.game_dir, name), "rb") as stream:
                self.assertEqual(stream.read(), content)

    def test_failed_staging_keeps_old_name_and_source_for_retry(self):
        content = b'installer'
        source = self.write('old.exe', content)
        download = self.item('old.exe', 'new.exe', content)
        with mock.patch.object(app.shutil, 'move', side_effect=OSError('simulated rename failure')):
            changed = app.handle_game_renames(self.root, [self.game([download])], False)

        self.assertTrue(changed)  # prev_verified was invalidated and must be saved
        self.assertEqual(download.old_name, 'old.exe')
        self.assertFalse(download.prev_verified)
        self.assertTrue(os.path.isfile(source))
        self.assertFalse(os.path.exists(os.path.join(self.game_dir, 'new.exe')))

    def test_partial_staging_failure_rolls_back_the_whole_cycle(self):
        content_a = b"payload A"
        content_b = b"payload B"
        source_a = self.write("A.bin", content_a)
        source_b = self.write("B.bin", content_b)
        item_a = self.item("A.bin", "B.bin", content_a)
        item_b = self.item("B.bin", "A.bin", content_b)
        real_move = shutil.move
        calls = {"count": 0}

        def fail_second_stage(src, dst):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("simulated second-stage failure")
            return real_move(src, dst)

        with mock.patch.object(app.shutil, "move", side_effect=fail_second_stage):
            changed = app.handle_game_renames(self.root, [self.game([item_a, item_b])], False)

        self.assertTrue(changed)
        self.assertEqual(item_a.old_name, "A.bin")
        self.assertEqual(item_b.old_name, "B.bin")
        self.assertFalse(item_b.prev_verified)
        for path, expected in ((source_a, content_a), (source_b, content_b)):
            with open(path, "rb") as stream:
                self.assertEqual(stream.read(), expected)
        self.assertFalse(os.path.exists(os.path.join(self.root, app.ORPHAN_DIR_NAME)))

    def test_dry_run_does_not_create_orphan_directory_or_change_manifest(self):
        content = b'installer'
        self.write('old.exe', content)
        self.write('new.exe', b'different destination')
        download = self.item('old.exe', 'new.exe', content)

        changed = app.handle_game_renames(self.root, [self.game([download])], True)

        self.assertFalse(changed)
        self.assertEqual(download.old_name, 'old.exe')
        self.assertFalse(os.path.exists(os.path.join(self.root, app.ORPHAN_DIR_NAME)))
        self.assertTrue(os.path.isfile(os.path.join(self.game_dir, 'old.exe')))

    def test_folder_rename_clears_old_folder_name_only_after_success(self):
        old_dir = os.path.join(self.root, 'Old Game')
        os.rename(self.game_dir, old_dir)
        game = self.game([], folder_name='Game', old_folder_name='Old Game')

        changed = app.handle_game_renames(self.root, [game], False)

        self.assertTrue(changed)
        self.assertIsNone(game.old_folder_name)
        self.assertTrue(os.path.isdir(self.game_dir))
        self.assertFalse(os.path.exists(old_dir))

    def test_rename_helper_saves_the_complete_manifest_not_the_selected_subset(self):
        selected = [self.game([])]
        complete = [self.game([]), self.game([], title='Other', folder_name='Other')]
        with mock.patch.object(app, 'handle_game_renames', return_value=True), \
             mock.patch.object(app, 'save_manifest') as save:
            self.assertTrue(app._handle_game_renames_and_save(self.root, selected, False,
                                                               manifest_items=complete))
        save.assert_called_once_with(complete)

    def test_failed_folder_rename_keeps_old_folder_name(self):
        old_dir = os.path.join(self.root, 'Old Game')
        os.rename(self.game_dir, old_dir)
        game = self.game([], folder_name='Game', old_folder_name='Old Game')
        with mock.patch.object(app.shutil, 'move', side_effect=OSError('simulated failure')):
            changed = app.handle_game_renames(self.root, [game], False)
        self.assertFalse(changed)
        self.assertEqual(game.old_folder_name, 'Old Game')
        self.assertTrue(os.path.isdir(old_dir))


    def make_folder_game(self, old_name, new_name, game_id):
        return self.game([], id=game_id, title=new_name, folder_name=new_name,
                         old_folder_name=old_name)

    def test_two_game_directory_cycle_swaps_folders_without_orphaning(self):
        a = os.path.join(self.root, 'A')
        b = os.path.join(self.root, 'B')
        os.makedirs(a)
        os.makedirs(b)
        with open(os.path.join(a, 'payload'), 'wb') as stream:
            stream.write(b'from A')
        with open(os.path.join(b, 'payload'), 'wb') as stream:
            stream.write(b'from B')
        games = [self.make_folder_game('A', 'B', 1),
                 self.make_folder_game('B', 'A', 2)]

        changed = app.handle_game_renames(self.root, games, False)

        self.assertTrue(changed)
        self.assertTrue(all(game.old_folder_name is None for game in games))
        with open(os.path.join(a, 'payload'), 'rb') as stream:
            self.assertEqual(stream.read(), b'from B')
        with open(os.path.join(b, 'payload'), 'rb') as stream:
            self.assertEqual(stream.read(), b'from A')
        self.assertFalse(os.path.exists(os.path.join(self.root, app.ORPHAN_DIR_NAME)))
        self.assertFalse(any(name.startswith('.gogrepo-dir-rename-') for name in os.listdir(self.root)))

    def test_three_game_directory_cycle_preserves_all_folder_contents(self):
        payloads = {'A': b'payload A', 'B': b'payload B', 'C': b'payload C'}
        for name, payload in payloads.items():
            folder = os.path.join(self.root, name)
            os.makedirs(folder)
            with open(os.path.join(folder, 'data'), 'wb') as stream:
                stream.write(payload)
        games = [self.make_folder_game('A', 'B', 1),
                 self.make_folder_game('B', 'C', 2),
                 self.make_folder_game('C', 'A', 3)]

        changed = app.handle_game_renames(self.root, games, False)

        self.assertTrue(changed)
        expected = {'A': b'payload C', 'B': b'payload A', 'C': b'payload B'}
        for name, payload in expected.items():
            with open(os.path.join(self.root, name, 'data'), 'rb') as stream:
                self.assertEqual(stream.read(), payload)
        self.assertTrue(all(game.old_folder_name is None for game in games))

    def test_directory_rename_orphans_only_a_non_cycle_destination_clash(self):
        old = os.path.join(self.root, 'Old')
        new = os.path.join(self.root, 'New')
        os.makedirs(old)
        os.makedirs(new)
        with open(os.path.join(old, 'installer'), 'wb') as stream:
            stream.write(b'current game')
        with open(os.path.join(new, 'keep'), 'wb') as stream:
            stream.write(b'pre-existing destination')
        game = self.make_folder_game('Old', 'New', 1)

        changed = app.handle_game_renames(self.root, [game], False)

        self.assertTrue(changed)
        self.assertIsNone(game.old_folder_name)
        with open(os.path.join(new, 'installer'), 'rb') as stream:
            self.assertEqual(stream.read(), b'current game')
        orphan_root = os.path.join(self.root, app.ORPHAN_DIR_NAME, 'New')
        orphaned = [os.path.join(orphan_root, name) for name in os.listdir(orphan_root)]
        self.assertEqual(len(orphaned), 1)
        with open(os.path.join(orphaned[0], 'keep'), 'rb') as stream:
            self.assertEqual(stream.read(), b'pre-existing destination')

    def test_directory_staging_failure_restores_every_source_and_keeps_markers(self):
        for name in ('A', 'B'):
            folder = os.path.join(self.root, name)
            os.makedirs(folder)
            with open(os.path.join(folder, 'payload'), 'wb') as stream:
                stream.write(name.encode('ascii'))
        games = [self.make_folder_game('A', 'B', 1),
                 self.make_folder_game('B', 'A', 2)]
        real_move = shutil.move
        calls = {'count': 0}

        def fail_second_move(src, dst, *args, **kwargs):
            calls['count'] += 1
            if calls['count'] == 2:
                raise OSError('simulated directory staging failure')
            return real_move(src, dst, *args, **kwargs)

        with mock.patch.object(app.shutil, 'move', side_effect=fail_second_move):
            changed = app.handle_game_renames(self.root, games, False)

        self.assertFalse(changed)
        self.assertEqual([game.old_folder_name for game in games], ['A', 'B'])
        for name in ('A', 'B'):
            with open(os.path.join(self.root, name, 'payload'), 'rb') as stream:
                self.assertEqual(stream.read(), name.encode('ascii'))
        self.assertFalse(any(name.startswith('.gogrepo-dir-rename-') for name in os.listdir(self.root)))

    def test_directory_commit_failure_rolls_back_all_staged_folders(self):
        for name in ('A', 'B'):
            folder = os.path.join(self.root, name)
            os.makedirs(folder)
            with open(os.path.join(folder, 'payload'), 'wb') as stream:
                stream.write(name.encode('ascii'))
        games = [self.make_folder_game('A', 'B', 1),
                 self.make_folder_game('B', 'A', 2)]
        real_move = shutil.move
        calls = {'count': 0}

        def fail_first_commit(src, dst, *args, **kwargs):
            calls['count'] += 1
            if calls['count'] == 3:
                raise OSError('simulated directory commit failure')
            return real_move(src, dst, *args, **kwargs)

        with mock.patch.object(app.shutil, 'move', side_effect=fail_first_commit):
            changed = app.handle_game_renames(self.root, games, False)

        self.assertFalse(changed)
        self.assertEqual([game.old_folder_name for game in games], ['A', 'B'])
        for name in ('A', 'B'):
            with open(os.path.join(self.root, name, 'payload'), 'rb') as stream:
                self.assertEqual(stream.read(), name.encode('ascii'))
        self.assertFalse(any(name.startswith('.gogrepo-dir-rename-') for name in os.listdir(self.root)))

    def test_directory_dry_run_does_not_stage_or_change_anything(self):
        old = os.path.join(self.root, 'Old')
        os.makedirs(old)
        with open(os.path.join(old, 'payload'), 'wb') as stream:
            stream.write(b'unchanged')
        game = self.make_folder_game('Old', 'New', 1)

        changed = app.handle_game_renames(self.root, [game], True)

        self.assertFalse(changed)
        self.assertEqual(game.old_folder_name, 'Old')
        self.assertTrue(os.path.isdir(old))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'New')))
        self.assertFalse(any(name.startswith('.gogrepo-dir-rename-') for name in os.listdir(self.root)))

    def test_selected_download_uses_complete_manifest_for_directory_cycles(self):
        for name in ('A', 'B'):
            folder = os.path.join(self.root, name)
            os.makedirs(folder)
            with open(os.path.join(folder, 'payload'), 'wb') as stream:
                stream.write(name.encode('ascii'))
        game_a = self.make_folder_game('A', 'B', 1)
        game_b = self.make_folder_game('B', 'A', 2)
        selected = [game_a]
        complete_manifest = [game_a, game_b]

        with mock.patch.object(app, 'save_manifest') as save:
            changed = app._handle_game_renames_and_save(
                self.root, selected, False, manifest_items=complete_manifest)

        self.assertTrue(changed)
        save.assert_called_once_with(complete_manifest)
        with open(os.path.join(self.root, 'A', 'payload'), 'rb') as stream:
            self.assertEqual(stream.read(), b'B')
        with open(os.path.join(self.root, 'B', 'payload'), 'rb') as stream:
            self.assertEqual(stream.read(), b'A')

    def test_duplicate_directory_destinations_are_skipped_as_ambiguous(self):
        for name in ('A', 'B'):
            os.makedirs(os.path.join(self.root, name))
        games = [self.make_folder_game('A', 'C', 1),
                 self.make_folder_game('B', 'C', 2)]

        changed = app.handle_game_renames(self.root, games, False)

        self.assertFalse(changed)
        self.assertEqual([game.old_folder_name for game in games], ['A', 'B'])
        self.assertTrue(os.path.isdir(os.path.join(self.root, 'A')))
        self.assertTrue(os.path.isdir(os.path.join(self.root, 'B')))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'C')))



if __name__ == '__main__':
    unittest.main()
