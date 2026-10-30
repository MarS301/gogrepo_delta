"""Behaviour of cmd_download, checked against explicit expectations (not against another version).

Each scenario starts a local fake GOG server (tests/download_rig/rig.py), runs cmd_download against a
temporary folder and looks at the result. Needs no network. Takes about a minute."""
import functools
import os
import sys
import unittest
import _bootstrap  # noqa: F401
import gogrepo_delta as gogrepoc

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'download_rig'))
import rig  # noqa: E402


@functools.lru_cache(maxsize=None)
def result(name):
    return rig.run(gogrepoc, name)


def files(r):
    return {k: v for k, v in r['tree'].items() if v is not None}


def game_files(r):
    """Files in the game folders (not in !downloading, !orphaned)."""
    return {k: v for k, v in files(r).items() if not k.startswith('!')}


def messages(r, level=None):
    return [m for lvl, m in r['logs'] if level is None or lvl == level]


class Checks(unittest.TestCase):
    def assertServed(self, r, relpath):
        """The file exists and has exactly the bytes the server delivered."""
        self.assertIn(relpath, files(r), relpath)
        self.assertEqual(files(r)[relpath][1], r['served'][os.path.basename(relpath)], relpath)

    def assertAbsent(self, r, relpath):
        self.assertNotIn(relpath, files(r), relpath)

    def assertLogged(self, r, text, level=None):
        self.assertTrue(any(text in m for m in messages(r, level)), 'not logged: %r' % text)

    def assertNotLogged(self, r, text):
        self.assertFalse(any(text in m for m in messages(r)), 'unexpectedly logged: %r' % text)


STANDARD_FILES = ['alpha/setup_alpha.exe', 'alpha/setup_alpha-1.bin', 'alpha/setup_alpha_linux.sh', 'alpha/setup_alpha_de.exe',
                  'alpha/galaxy_alpha.exe', 'alpha/shared_alpha.exe', 'alpha/manual.pdf', 'alpha/soundtrack.zip',
                  'Beta Game/setup_beta.exe', 'Beta Game/extra_beta.exe']


class DryRunTests(Checks):
    def test_dry_run_writes_no_files_and_reports_what_is_left(self):
        r = result('dryrun_fresh')
        self.assertEqual(files(r), {})
        self.assertLogged(r, 'left to download')

    def test_dry_run_lists_but_does_not_remove_outdated_work_files(self):
        r = result('cleanup_dirs_dryrun')
        self.assertLogged(r, 'Removing outdated directory')
        self.assertIn('!downloading/old_game/file.bin', files(r))


class FreshDownloadTests(Checks):
    def test_every_file_arrives_intact(self):
        r = result('fresh_download')
        for relpath in STANDARD_FILES:
            self.assertServed(r, relpath)

    def test_info_and_serial_files_are_written(self):
        r = result('fresh_download')
        for relpath in ('alpha/!info.txt', 'alpha/!serial.txt', 'Beta Game/!info.txt', 'Beta Game/!serial.txt'):
            self.assertIn(relpath, files(r))

    def test_work_folders_are_left_clean(self):
        r = result('fresh_download')
        self.assertEqual([k for k in files(r) if k.startswith('!downloading')], [])
        self.assertEqual([k for k in r['tree'] if k.startswith('!downloading') and k.endswith('/')], ['!downloading/', '!downloading/!provisional/'])

    def test_combined_md5_url_notice_is_reported_when_the_download_ends(self):
        # The fake server's URLs have no 'prefix' parameter, like GOG's newer CDN URLs. The notice is combined into
        # one warning and is logged by cmd_download itself, not only at interpreter exit (after "exiting...").
        r = result('fresh_download')
        notices = [m for m in messages(r, 'WARNING') if "no 'prefix' query parameter" in m]
        self.assertEqual(len(notices), 1)
        self.assertIn('file(s)', notices[0])

    def test_all_files_are_reported_as_downloaded(self):
        r = result('fresh_download')
        self.assertEqual(len([m for m in messages(r) if m.startswith('     download   ')]), len(STANDARD_FILES))


class FilterTests(Checks):
    def test_os_and_language_filters(self):
        r = result('filter_os_lang')      # linux only, English only
        self.assertServed(r, 'alpha/setup_alpha_linux.sh')
        for relpath in ('alpha/setup_alpha.exe', 'alpha/setup_alpha_de.exe', 'alpha/galaxy_alpha.exe', 'Beta Game/setup_beta.exe'):
            self.assertAbsent(r, relpath)
        self.assertServed(r, 'alpha/manual.pdf')          # extras are not filtered by os

    def test_language_filter_german(self):
        r = result('filter_de_only')
        self.assertServed(r, 'alpha/setup_alpha_de.exe')
        self.assertAbsent(r, 'alpha/setup_alpha.exe')

    def test_skip_flags(self):
        r = result('skip_flags')
        for relpath in ('alpha/manual.pdf', 'alpha/galaxy_alpha.exe', 'alpha/shared_alpha.exe', 'Beta Game/extra_beta.exe'):
            self.assertAbsent(r, relpath)
        self.assertServed(r, 'alpha/setup_alpha.exe')

    def test_skip_standalone(self):
        r = result('skip_standalone')
        self.assertAbsent(r, 'alpha/setup_alpha.exe')
        self.assertServed(r, 'alpha/galaxy_alpha.exe')

    def test_skipfiles_patterns(self):
        r = result('skipfiles')
        self.assertAbsent(r, 'alpha/manual.pdf')
        self.assertAbsent(r, 'alpha/setup_alpha-1.bin')
        self.assertServed(r, 'alpha/setup_alpha.exe')
        self.assertLogged(r, 'skip       manual.pdf (matches "*.pdf")')

    def test_ids_select_by_title(self):
        r = result('ids_by_title_and_id')
        self.assertServed(r, 'alpha/setup_alpha.exe')
        self.assertAbsent(r, 'Beta Game/setup_beta.exe')

    def test_skipids(self):
        r = result('skipids')
        self.assertAbsent(r, 'alpha/setup_alpha.exe')
        self.assertServed(r, 'Beta Game/setup_beta.exe')

    def test_unknown_id_exits_with_an_error(self):
        r = result('ids_not_found')
        self.assertEqual(r['exc'], ('SystemExit', '1'))
        self.assertLogged(r, 'no game with id in', 'ERROR')

    def test_ids_and_skipids_that_leave_nothing_exit(self):
        self.assertEqual(result('ids_and_skipids_empty')['exc'], ('SystemExit', '1'))
        self.assertEqual(result('skipids_only_empty')['exc'], ('SystemExit', '1'))

    def test_empty_manifest_exits(self):
        r = result('empty_manifest')
        self.assertEqual(r['exc'], ('SystemExit', '1'))
        self.assertLogged(r, 'no game found', 'ERROR')

    def test_download_limit_is_respected(self):
        # limit 6000 bytes; games are processed in folder order ("Beta Game" before "alpha"), each file is
        # taken if it still fits: 2100 + 1100 + 2500 = 5700, everything after that would exceed the limit.
        r = result('download_limit')
        for relpath in ('Beta Game/setup_beta.exe', 'Beta Game/extra_beta.exe', 'alpha/setup_alpha.exe'):
            self.assertServed(r, relpath)
        for relpath in ('alpha/setup_alpha-1.bin', 'alpha/setup_alpha_linux.sh', 'alpha/galaxy_alpha.exe', 'alpha/manual.pdf'):
            self.assertAbsent(r, relpath)
        self.assertLogged(r, 'skip       setup_alpha-1.bin (size 0.0MB would exceed download limit')


class ExistingFileTests(Checks):
    def test_correct_file_is_kept_and_wrong_sizes_are_replaced(self):
        r = result('existing_files')
        self.assertLogged(r, 'pass       setup_alpha.exe')
        self.assertLogged(r, 'setup_alpha_de.exe has incorrect size', 'WARNING')
        self.assertLogged(r, 'setup_alpha_linux.sh has incorrect size', 'WARNING')
        for relpath in ('alpha/setup_alpha.exe', 'alpha/setup_alpha_de.exe', 'alpha/setup_alpha_linux.sh'):
            self.assertServed(r, relpath)

    def test_marked_for_change_is_downloaded_again_and_flags_are_reset(self):
        r = result('existing_files')
        self.assertLogged(r, 'galaxy_alpha.exe has been marked for change', 'WARNING')
        entry = r['manifest_obj'][0]['galaxyDownloads'][0]
        self.assertFalse(entry['force_change'])
        self.assertFalse(entry['prev_verified'])
        self.assertEqual(entry['old_updated'], entry['updated'])

    def test_force_change_flags_reset_for_everything_downloaded(self):
        r = result('force_change_flags')
        for game in r['manifest_obj']:
            for entry in game['downloads'] + game['extras']:
                self.assertFalse(entry['force_change'], entry['name'])
                self.assertFalse(entry['prev_verified'], entry['name'])

    def test_nothing_to_download_when_everything_is_current(self):
        r = result('all_up_to_date')
        self.assertLogged(r, 'nothing to download')
        self.assertEqual(r['hits'].get(('GET', 'alpha__setup_alpha.exe')), None)


class ResumeTests(Checks):
    def test_partial_downloads_with_corrupt_chunks_are_repaired(self):
        r = result('resume_chunk_repair')
        self.assertServed(r, 'alpha/setup_alpha.exe')
        self.assertServed(r, 'Beta Game/setup_beta.exe')

    def test_partial_download_without_md5_data_is_completed(self):
        self.assertServed(result('resume_without_chunks'), 'alpha/setup_alpha-1.bin')

    def test_oversized_partial_file_is_truncated_and_completed(self):
        self.assertServed(result('resume_oversized_partial'), 'alpha/setup_alpha.exe')

    def test_files_left_in_provisional_folder_are_moved_into_place(self):
        r = result('provisional_files')
        self.assertServed(r, 'alpha/manual.pdf')
        self.assertServed(r, 'Beta Game/extra_beta.exe')
        self.assertEqual([k for k in files(r) if k.startswith('!downloading')], [])

    def test_provisional_and_final_file_both_present_is_reported(self):
        r = result('provisional_and_dest')
        self.assertLogged(r, 'has both provisional and destination file', 'WARNING')


class CleanupTests(Checks):
    def test_outdated_work_files_and_folders_are_removed(self):
        r = result('cleanup_dirs')
        for relpath in ('!downloading/old_game/file.bin', '!downloading/alpha/stale.bin', '!downloading/!provisional/old_game2/f.bin',
                        '!downloading/!provisional/alpha/stale2.bin'):
            self.assertAbsent(r, relpath)
        self.assertFalse([k for k in r['tree'] if k.startswith('!downloading/alpha/sub')])


class FailureTests(Checks):
    def test_failing_files_do_not_stop_the_others(self):
        r = result('faults')
        self.assertServed(r, 'faulty/good.exe')
        self.assertAbsent(r, 'faulty/missing.exe')
        self.assertLogged(r, '! ', 'ERROR')

    def test_unexpected_content_range_is_an_error(self):
        r = result('faults')
        self.assertLogged(r, 'chunk request has unexpected Content-Range', 'ERROR')

    def test_files_that_keep_failing_are_not_moved_into_place(self):
        r = result('faults_large_truncate')
        self.assertAbsent(r, 'bigfaults/trunc_big.exe')
        self.assertAbsent(r, 'bigfaults/trunc_big_nochunk.bin')
        self.assertLogged(r, 'not moving uncompleted download')

    def test_a_flaky_response_is_retried(self):
        r = result('faults_large_truncate')
        self.assertServed(r, 'bigfaults/flaky_big.exe')
        self.assertServed(r, 'bigfaults/flaky_big_nochunk.bin')
        self.assertServed(r, 'bigfaults/fine_big.exe')

    def test_bad_md5_data_is_reported_and_skipped(self):
        r = result('bad_xml')
        self.assertLogged(r, 'XML verification data size does not match manifest size', 'WARNING')
        self.assertLogged(r, 'XML verification chunk data for', 'WARNING')
        self.assertLogged(r, 'is not md5. skipping', 'WARNING')

    def test_entries_without_name_or_size_are_skipped(self):
        r = result('odd_entries')
        self.assertLogged(r, 'nosize.exe has no size info', 'WARNING')
        self.assertServed(r, 'alpha/noupdated.exe')


class PreallocationTests(Checks):
    def calls(self, name):
        return result(name)['calls']

    def test_linux_uses_posix_fallocate_on_supported_file_systems(self):
        self.assertTrue(any(c.startswith("('posix_fallocate'") for c in self.calls('prealloc_linux_ext4')))

    def test_linux_skips_unsupported_file_systems_and_the_skip_option(self):
        for name in ('prealloc_linux_unlisted_fs', 'prealloc_linux_skip'):
            self.assertFalse(any(c.startswith("('posix_fallocate'") for c in self.calls(name)), name)

    def test_failed_posix_preallocation_only_warns(self):
        r = result('prealloc_linux_fallocate_fails')
        self.assertLogged(r, 'posix preallocation failed', 'WARNING')
        self.assertServed(r, 'alpha/setup_alpha.exe')

    def disposition(self, calls, filename):
        """CreateFileW creation disposition used for a file: 1 = CREATE_NEW, 3 = OPEN_EXISTING."""
        found = [c for c in calls if c.startswith("('CreateFileW'") and ('/' + filename + "'") in c.replace('\\\\', '/')]
        self.assertEqual(len(found), 1, filename)
        return int(found[0].rstrip(')').rsplit(', ', 1)[1])

    def test_windows_creates_new_files_and_grows_existing_ones(self):
        calls = self.calls('prealloc_windows_ntfs')
        self.assertEqual(self.disposition(calls, 'setup_alpha-1.bin'), 1)     # nothing there yet: CREATE_NEW
        self.assertEqual(self.disposition(calls, 'manual.pdf'), 1)
        self.assertEqual(self.disposition(calls, 'setup_alpha.exe'), 3)       # smaller partial download: OPEN_EXISTING
        self.assertEqual(self.disposition(calls, 'setup_alpha_linux.sh'), 3)  # too small final file moved back: OPEN_EXISTING
        self.assertTrue(any(c.startswith("('SetEndOfFile'") for c in calls))

    def test_windows_skips_unsupported_file_systems_and_the_skip_option(self):
        for name in ('prealloc_windows_unlisted_fs', 'prealloc_windows_skip'):
            self.assertFalse(any(c.startswith("('CreateFileW'") for c in self.calls(name)), name)

    def test_windows_failures_only_warn_and_the_download_still_completes(self):
        for name in ('prealloc_windows_createfile_fails', 'prealloc_windows_late_failure', 'prealloc_windows_createfile_raises'):
            r = result(name)
            self.assertLogged(r, 'preallocation failed', 'WARNING')
            self.assertServed(r, 'alpha/setup_alpha.exe')
            self.assertServed(r, 'alpha/setup_alpha_linux.sh')

    def test_a_failure_after_the_handle_was_opened_closes_the_handle(self):
        r = result('prealloc_windows_late_failure')
        self.assertLogged(r, 'failed - closing outstanding handle', 'WARNING')
        self.assertTrue(any(c.startswith("('CloseHandle'") for c in r['calls']))

    def test_macos_does_not_preallocate(self):
        calls = self.calls('prealloc_darwin')
        self.assertFalse(any(c.startswith(("('posix_fallocate'", "('CreateFileW'")) for c in calls))


class ImageTests(Checks):
    def test_cover_and_background_images_are_downloaded(self):
        r = result('images')
        names = [k for k in files(r) if '/!images/' in k]
        self.assertTrue(any('/image_url/' in k for k in names))
        self.assertTrue(any('/bg_urls/1920/' in k for k in names))
        self.assertTrue(any('/bg_url/' in k for k in names))

    def test_only_the_requested_kinds_are_downloaded(self):
        covers = [k for k in files(result('images_covers_only')) if '/!images/' in k]
        backgrounds = [k for k in files(result('images_backgrounds_only')) if '/!images/' in k]
        self.assertTrue(covers and all('/image_url/' in k for k in covers))
        self.assertTrue(backgrounds and not any('/image_url/' in k for k in backgrounds))

    def test_old_images_are_moved_to_orphaned_when_cleaning(self):
        r = result('images_replace_old')
        self.assertTrue(any(k.startswith('!orphaned/') and k.endswith('old.jpg') for k in files(r)))

    def test_old_images_are_deleted_without_cleaning(self):
        r = result('images_replace_old_noclean')
        self.assertFalse(any(k.endswith('old.jpg') for k in files(r)))

    def test_missing_images_only_warn(self):
        r = result('images_missing_on_server')
        self.assertLogged(r, 'Could not download cover image', 'WARNING')
        self.assertServed(r, 'alpha/setup_alpha.exe')

    def test_ctrl_c_during_image_download_propagates(self):
        for name in ('images_interrupt_cover', 'images_interrupt_bg_urls', 'images_interrupt_bg_url'):
            self.assertEqual(result(name)['exc'][0], 'KeyboardInterrupt', name)


if __name__ == '__main__':
    unittest.main()
