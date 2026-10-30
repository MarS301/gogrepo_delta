"""A manifest that is missing or damaged: ask whether to use gog-manifest.dat.bak instead; never carry on with an empty list."""
import builtins
import contextlib
import csv
import glob
import os
import shutil
import tempfile
import unittest
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_manifest_format import sample_items

MANIFEST, BACKUP = g.MANIFEST_FILENAME, g.MANIFEST_FILENAME + g.BACKUP_EXT


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset()                         # no command: the question about a new manifest is allowed
        self.old_items, self.new_items = sample_items(2), sample_items(4)
        g.save_manifest(self.old_items)
        g.save_manifest(self.new_items)               # the second save leaves the first version as the .bak
        self.backup_text = self.text(BACKUP)

    def text(self, path):
        with open(path, encoding='utf-8') as f:
            return f.read()

    @contextlib.contextmanager
    def terminal(self, answer='y', interactive=True, answers=None):
        """Pretend to run in a terminal and type `answer` at every question (or the `answers` one after the other).
        The yielded mock records the questions."""
        typed = {'side_effect': list(answers)} if answers is not None else {'return_value': answer}
        with mock.patch.object(g, '_stdin_is_interactive', return_value=interactive), mock.patch.object(builtins, 'input', **typed) as asked:
            yield asked

    def load(self, **kw):
        with self.terminal(**kw) as asked:
            return g.load_manifest(), asked

    def remove_manifest(self):
        os.remove(MANIFEST)

    def damage_manifest(self, content='{ "items": [ broken'):
        with open(MANIFEST, 'w', encoding='utf-8') as f:
            f.write(content)


class MissingManifestTests(RecoveryTests):
    def test_without_manifest_and_backup_it_is_the_first_run(self):
        os.remove(MANIFEST)
        os.remove(BACKUP)
        with self.terminal() as asked:
            self.assertEqual(g.load_manifest(), [])
        asked.assert_not_called()

    def test_the_user_is_told_what_is_missing_and_asked_about_the_backup(self):
        self.remove_manifest()
        with self.assertLogs('gogrepoc', level='ERROR') as logs:
            items, asked = self.load()
        text = '\n'.join(logs.output)
        self.assertIn("The manifest file 'gog-manifest.dat' was not found", text)
        self.assertIn("A backup copy exists: 'gog-manifest.dat.bak'", text)
        self.assertIn('before the last save', text)
        self.assertIn("Use the backup copy 'gog-manifest.dat.bak' instead? [y/N]", asked.call_args[0][0])

    def test_yes_restores_the_backup_and_uses_it(self):
        self.remove_manifest()
        items, _ = self.load(answer='y')
        self.assertEqual(items, self.old_items)
        self.assertEqual(self.text(MANIFEST), self.backup_text)       # the manifest file is back, from the backup
        self.assertEqual(self.text(BACKUP), self.backup_text)         # and the backup itself is untouched
        self.assertEqual(g.load_manifest(), self.old_items)           # the next run simply finds it

    def test_yes_in_several_spellings(self):
        for answer in ('y', 'Y', 'yes', 'YES', ' yes ', 'j', 'ja', 'Ja'):
            if os.path.exists(MANIFEST):
                self.remove_manifest()
            items, _ = self.load(answer=answer)
            self.assertEqual(items, self.old_items, repr(answer))

    def test_anything_else_stops_the_program_and_changes_nothing(self):
        for answer in ('n', 'N', 'no', '', '   ', 'maybe', 'x'):
            self.remove_manifest() if os.path.exists(MANIFEST) else None
            with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
                self.load(answer=answer)
            self.assertEqual(raised.exception.code, 1, repr(answer))
            self.assertIn('Not starting a new manifest either, stopping', '\n'.join(logs.output))
            self.assertFalse(os.path.exists(MANIFEST), 'no empty manifest must appear')
            self.assertEqual(self.text(BACKUP), self.backup_text)

    def test_a_run_without_a_terminal_does_not_ask_and_stops(self):
        self.remove_manifest()
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
            with self.terminal(interactive=False) as asked:
                g.load_manifest()
        self.assertEqual(raised.exception.code, 1)
        asked.assert_not_called()
        text = '\n'.join(logs.output)
        self.assertIn('not interactive', text)
        self.assertIn("copy 'gog-manifest.dat.bak' over 'gog-manifest.dat'", text)
        self.assertFalse(os.path.exists(MANIFEST))

    def test_closed_input_counts_as_no(self):
        self.remove_manifest()
        with self.assertRaises(SystemExit), self.assertLogs('gogrepoc', level='ERROR'):
            with mock.patch.object(g, '_stdin_is_interactive', return_value=True), mock.patch.object(builtins, 'input', side_effect=EOFError()):
                g.load_manifest()
        self.assertFalse(os.path.exists(MANIFEST))

    def test_an_old_format_backup_is_restored_too(self):
        with mock.patch.object(g, 'MANIFEST_FORMAT', 'legacy'):
            g.save_manifest(self.old_items)
            g.save_manifest(self.new_items)
        self.remove_manifest()
        items, _ = self.load()
        self.assertEqual(items, self.old_items)

    def test_the_commands_use_it_too(self):
        self.remove_manifest()
        with self.terminal():
            g.cmd_export('out.csv', None, ',')
        with open('out.csv', encoding='utf-8-sig', newline='') as f:
            self.assertEqual(len(list(csv.reader(f))) - 1, 2 * 2)      # the two games of the backup, 2 files each

    def test_saving_afterwards_works_normally(self):
        self.remove_manifest()
        self.load()
        g.save_manifest(self.new_items)
        self.assertEqual(g.load_manifest(), self.new_items)


class DamagedManifestTests(RecoveryTests):
    def test_damaged_json_is_reported_and_the_backup_offered(self):
        self.damage_manifest()
        with self.assertLogs('gogrepoc', level='ERROR') as logs:
            items, asked = self.load()
        self.assertIn("The manifest file 'gog-manifest.dat' is damaged", '\n'.join(logs.output))
        self.assertEqual(items, self.old_items)
        self.assertEqual(self.text(MANIFEST), self.backup_text)

    def test_the_damaged_file_is_kept(self):
        self.damage_manifest('this is damaged')
        self.load()
        self.assertEqual(self.text(MANIFEST + '.damaged'), 'this is damaged')

    def test_an_earlier_damaged_copy_is_never_overwritten(self):
        self.damage_manifest('first damage')
        self.load()
        self.damage_manifest('second damage')
        self.load()
        copies = sorted(glob.glob(MANIFEST + '.damaged*'))
        self.assertEqual(len(copies), 2)
        self.assertEqual(sorted(self.text(c) for c in copies), ['first damage', 'second damage'])

    def test_a_damaged_old_format_file_is_handled_the_same_way(self):
        self.damage_manifest("# 1 games\n[{'id': 1, 'title': ")
        items, _ = self.load()
        self.assertEqual(items, self.old_items)

    def test_bytes_that_are_not_utf8_count_as_damaged(self):
        with open(MANIFEST, 'wb') as f:
            f.write(b'{"items": [\xff\xfe\xfd]}')
        items, _ = self.load()
        self.assertEqual(items, self.old_items)

    def test_a_declined_backup_leaves_the_damaged_file_alone(self):
        self.damage_manifest('still here')
        with self.assertRaises(SystemExit), self.assertLogs('gogrepoc', level='ERROR'):
            self.load(answer='n')
        self.assertEqual(self.text(MANIFEST), 'still here')
        self.assertFalse(os.path.exists(MANIFEST + '.damaged'))

    def test_damaged_without_a_backup_stops_with_a_clear_message(self):
        os.remove(BACKUP)
        self.damage_manifest()
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
            self.load(answer='n')
        self.assertEqual(raised.exception.code, 1)
        text = '\n'.join(logs.output)
        self.assertIn('is damaged', text)
        self.assertIn("There is no backup copy ('gog-manifest.dat.bak')", text)
        self.assertIn("delete or move 'gog-manifest.dat'", text)
        self.assertNotIn('use the backup yourself', text)                   # there is no backup to point to

    def test_a_damaged_backup_is_not_used_and_nothing_is_changed(self):
        self.damage_manifest('main damaged')
        with open(BACKUP, 'w', encoding='utf-8') as f:
            f.write('backup damaged')
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
            self.load()
        self.assertEqual(raised.exception.code, 1)
        self.assertIn('not usable either', '\n'.join(logs.output))
        self.assertEqual(self.text(MANIFEST), 'main damaged')
        self.assertEqual(self.text(BACKUP), 'backup damaged')
        self.assertFalse(os.path.exists(MANIFEST + '.damaged'))


class OtherReadProblemTests(RecoveryTests):
    def test_a_file_that_cannot_be_read_is_not_mistaken_for_an_empty_library(self):
        before = self.text(MANIFEST)
        real_open = builtins.open

        def locked(path, *args, **kwargs):
            if os.path.basename(str(path)) == MANIFEST:
                raise PermissionError(13, 'Permission denied')
            return real_open(path, *args, **kwargs)
        with mock.patch.object(builtins, 'open', locked), self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
            g.load_manifest()
        self.assertEqual(raised.exception.code, 1)
        self.assertIn('cannot be read', '\n'.join(logs.output))
        self.assertEqual(self.text(MANIFEST), before)                       # and nothing was overwritten
        self.assertEqual(g.load_manifest(), self.new_items)

    def test_a_missing_resume_file_is_normal_and_never_asks(self):
        g.save_resume_manifest(self.old_items + [g.AttrDict(complete=False)])
        g.save_resume_manifest(self.old_items + [g.AttrDict(complete=True)])      # leaves a resume .bak
        os.remove(g.RESUME_MANIFEST_FILENAME)
        with self.terminal() as asked:
            self.assertEqual(g.load_resume_manifest(), [])
        asked.assert_not_called()


class StartNewManifestTests(RecoveryTests):
    """After 'no' to the backup there is a second question: start a new, empty manifest?"""
    def test_declining_the_backup_leads_to_a_second_question(self):
        self.remove_manifest()
        with self.assertRaises(SystemExit), self.assertLogs('gogrepoc', level='ERROR'):
            with self.terminal(answers=['n', 'n']) as asked:
                g.load_manifest()
        questions = [call[0][0] for call in asked.call_args_list]
        self.assertEqual(len(questions), 2)
        self.assertIn("Use the backup copy 'gog-manifest.dat.bak' instead?", questions[0])
        self.assertIn("Start a new, empty manifest 'gog-manifest.dat' instead?", questions[1])
        self.assertTrue(all(q.endswith('[y/N] ') or '[y/N]' in q for q in questions))

    def test_the_manual_instructions_appear_only_after_both_answers(self):
        self.remove_manifest()
        seen = []

        def answer(prompt):
            seen.append((prompt, [m for m in (r.getMessage() for r in cm.records)]))
            return 'n'
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as cm:
            with mock.patch.object(g, '_stdin_is_interactive', return_value=True), mock.patch.object(builtins, 'input', side_effect=answer):
                g.load_manifest()
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(len(seen), 2)
        for prompt, messages_so_far in seen:
            self.assertFalse(any('yourself' in m for m in messages_so_far), 'instructions shown before the question: ' + prompt)
        final = [r.getMessage() for r in cm.records]
        self.assertIn("To use the backup yourself: copy 'gog-manifest.dat.bak' over 'gog-manifest.dat'.", final)
        self.assertTrue(any("delete or move 'gog-manifest.dat' and 'gog-manifest.dat.bak'" in m for m in final))
        self.assertTrue(any('Not starting a new manifest either' in m for m in final))

    def test_yes_to_the_second_question_starts_a_new_manifest_without_instructions(self):
        self.remove_manifest()
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            with self.terminal(answers=['n', 'y']):
                items = g.load_manifest()
        self.assertEqual(items, [])
        text = '\n'.join(logs.output)
        self.assertIn("starting a new manifest 'gog-manifest.dat'", text)
        self.assertIn('the next update has to fetch every game again', text)
        self.assertNotIn('yourself', text)
        self.assertFalse(os.path.exists(MANIFEST), 'nothing is written before the first save')

    def test_the_old_backup_is_kept_because_later_saves_overwrite_it(self):
        self.remove_manifest()
        with self.terminal(answers=['n', 'y']):
            g.load_manifest()
        self.assertEqual(self.text(MANIFEST + '.oldbackup'), self.backup_text)
        g.save_manifest(sample_items(1))
        g.save_manifest(sample_items(3))                                     # the second save replaces the .bak
        self.assertNotEqual(self.text(BACKUP), self.backup_text)
        self.assertEqual(self.text(MANIFEST + '.oldbackup'), self.backup_text)
        self.assertEqual(g.load_manifest(), sample_items(3))

    def test_a_damaged_file_is_kept_too(self):
        self.damage_manifest('damaged content')
        with self.terminal(answers=['n', 'y']):
            items = g.load_manifest()
        self.assertEqual(items, [])
        self.assertEqual(self.text(MANIFEST + '.damaged'), 'damaged content')
        self.assertEqual(self.text(MANIFEST + '.oldbackup'), self.backup_text)

    def test_without_a_backup_only_the_new_manifest_question_is_asked(self):
        os.remove(BACKUP)
        self.damage_manifest('damaged content')
        with self.terminal(answers=['y']) as asked:
            items = g.load_manifest()
        self.assertEqual(items, [])
        self.assertEqual(asked.call_count, 1)
        self.assertIn('Start a new, empty manifest', asked.call_args[0][0])
        self.assertEqual(self.text(MANIFEST + '.damaged'), 'damaged content')
        self.assertFalse(os.path.exists(MANIFEST + '.oldbackup'))

    def test_yes_to_the_backup_never_asks_the_second_question(self):
        self.remove_manifest()
        with self.terminal(answers=['y']) as asked:
            self.assertEqual(g.load_manifest(), self.old_items)
        self.assertEqual(asked.call_count, 1)

    def test_a_scheduled_run_asks_nothing_and_explains(self):
        self.remove_manifest()
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
            with self.terminal(interactive=False) as asked:
                g.load_manifest()
        self.assertEqual(raised.exception.code, 1)
        asked.assert_not_called()
        text = '\n'.join(logs.output)
        self.assertIn('not interactive', text)
        self.assertIn("To use the backup yourself: copy 'gog-manifest.dat.bak' over 'gog-manifest.dat'", text)
        self.assertIn('delete or move', text)

    def test_only_update_offers_a_new_manifest(self):
        for command in ('clean', 'trash', 'download', 'verify', 'backup', 'import', 'export'):
            self.remove_manifest() if os.path.exists(MANIFEST) else None
            g.run_report.reset(command)
            with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
                with self.terminal(answers=['n']) as asked:
                    g.load_manifest()
            self.assertEqual(raised.exception.code, 1, command)
            self.assertEqual(asked.call_count, 1, command)                   # only the question about the backup
            text = '\n'.join(logs.output)
            self.assertIn("'%s' needs an existing manifest; only 'update' can build a new one" % command, text)
            self.assertIn('To use the backup yourself', text)
            self.assertFalse(os.path.exists(MANIFEST + '.oldbackup'), command)

    def test_other_commands_without_a_backup_do_not_ask_at_all(self):
        os.remove(BACKUP)
        self.damage_manifest()
        g.run_report.reset('clean')
        with self.assertRaises(SystemExit), self.assertLogs('gogrepoc', level='ERROR') as logs:
            with self.terminal() as asked:
                g.load_manifest()
        asked.assert_not_called()
        self.assertIn("'clean' needs an existing manifest", '\n'.join(logs.output))

    def test_update_does_offer_it(self):
        self.remove_manifest()
        g.run_report.reset('update')
        with self.terminal(answers=['n', 'y']):
            self.assertEqual(g.load_manifest(), [])


class UpdateAfterNewManifestTests(RecoveryTests):
    """The whole path: `update -full` without a manifest, answering the two questions."""
    def run_main(self, *argv, answers):
        from types import SimpleNamespace
        from test_run_summary import games_api
        args = g.process_argv(['gogrepo_delta.py'] + list(argv) + ['-nolog'])
        with mock.patch.object(g, 'request', games_api()), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})):
            with self.terminal(answers=answers) as asked:
                return g.main(args), asked

    def test_update_full_builds_a_new_manifest_after_two_noes_to_the_backup_and_a_yes_to_the_new_one(self):
        self.remove_manifest()
        status, asked = self.run_main('update', '-full', answers=['n', 'y'])
        self.assertEqual(status, 0)
        self.assertEqual(asked.call_count, 2)
        self.assertEqual(sorted(game.title for game in g.load_manifest()), ['game_0', 'game_1', 'game_2'])
        self.assertEqual(self.text(MANIFEST + '.oldbackup'), self.backup_text)

    def test_update_full_stops_when_both_questions_are_declined(self):
        self.remove_manifest()
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR'):
            self.run_main('update', '-full', answers=['n', 'n'])
        self.assertEqual(raised.exception.code, 1)
        self.assertFalse(os.path.exists(MANIFEST))

    def test_download_never_offers_a_new_manifest(self):
        self.remove_manifest()
        with self.assertRaises(SystemExit) as raised, self.assertLogs('gogrepoc', level='ERROR') as logs:
            self.run_main('download', 'somedir', '-os', 'windows', '-lang', 'en', answers=['n'])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("'download' needs an existing manifest", '\n'.join(logs.output))
        self.assertFalse(os.path.exists(MANIFEST))


if __name__ == '__main__':
    unittest.main()
