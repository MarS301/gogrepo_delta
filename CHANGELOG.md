# Changelog

Every change to `gogrepo_delta.py`, newest first. Below it: how the versions work, and the known issues. This file is the former
"REFACTORING NOTES" block at the top of the script, moved here in full; the script now only points to it.

The goal of the refactoring was to keep behaviour. The only intended differences are listed explicitly, marked **DIFFERENCE**. Places in the
code that were changed for an entry may carry a "Refactoring" comment or docstring.

## How the version works

- The version is `0.5.N`, where **N is the number of the newest entry** below. Every new entry raises the version, so the entry number and
  the patch number always match. A test (`tests/test_config.py`) reads this file and fails if they do not.
- Entries 1-23 were made before this rule existed. Their headings say "Entry N" and do not name a version; the rule starts with entry 24.
- Small corrections that are not worth an entry (a spelling in the credits, say) do not change the version.
- The script stays one file, by choice.

## Known issues (not fixed yet)

- **A path over 259 characters is only warned about, and two kinds of rare name clash are not handled** (entry 0.5.91; the survey of a real library of 145+ files found none of them, the longest
  `GAMEFOLDER\NAME` there was 167 characters). (1) The script cannot shorten a path that is too long for Windows: the folder is GOG's slug and the installer name repeats most of it, so a game with a slug
  of about 95 characters or more may not fit even in a very short library path. It warns once, tries the download, and a refused write is reported as a failed file as before; the fixes are long path support
  (`LongPathsEnabled`) or a shorter library path. (2) Names that differ only in Unicode form are not normalized (macOS stores one form, so two such names would be one file there), and the duplicate rules at
  update compare names exactly, so two files whose names differ only in case are two manifest entries, and one file on Windows and macOS. Neither was seen in a real manifest; the migration of old names does
  ignore case.
- A language group that contains only a patch counts as "has your language" for that system (edge case, not handled).
- Reading the legacy manifest format is 3-4 times slower than it was with `eval` (0.7 s for a 1.2 MB file, 12 s for 23 MB); the JSON format, which is
  the default, is not affected.
- Saving the legacy manifest format still re-formats the whole manifest on every save (the cost grows with the library); it is not the default.
- A save that is killed hard (power loss, task kill) between creating and renaming its temporary file leaves a randomly named `*.tmp` file behind;
  nothing removes it later (entry 30). They are ignored by `.gitignore`.

## 0.5.92 - 25.11.2026 - combined warnings in a dry run, wakelock, two fixes found by tests that failed first, a test folder that was never removed

Each fix below has a test that failed before the change (open item 2 and finding F were checked first: item 2 turned out to fail only in one combination, and the other commands were fine).

- **Fixed: the combined warnings of `download` appeared after the summary in a dry run** (seen in a real run: the long-path warning of 0.5.91 came after `exiting...`). `cmd_download` only flushed the
  collected warnings (`note_summarised`) at the end of a real download; the dry run, the "nothing to download" exit and the "only finished files in !provisional" exit returned before that, and the
  program's exit printed them last. All three now flush before they return, so the warnings stand above the summary. A test makes a warning pending before each way out and checks that it is printed
  during the run (and, for the dry run, after the count of what is left to download).
- **Fixed (finding G): `Wakelock()` failing hid the real error.** `wakelock = Wakelock()` was inside the `try`, and the `finally` used the name, so a failing constructor ended in an `UnboundLocalError`
  that replaced the real error. The block under `if __name__ == "__main__"` now starts with `wakelock = None` and releases only a wakelock that was made (it stays a block: the entry point tests run its source). Tests for it: constructor fails (the real error is logged, exit status 1, the command does not run), taking fails, success, failures status, error in the
  command, Ctrl+C and `SystemExit` with its own code.
- **Fixed (open item 2): `download -ids ...` stopped with `AttributeError: galaxyDownloads`** for a manifest with entries from before the fields `galaxyDownloads` and `sharedDownloads` existed, when a
  game that `-ids` did not select had a leftover folder in `!downloading` or `!provisional`. `_clean_work_dir` read the lists of every game directly, and only the selected games get the defaults. It now
  reads them with `_game_files` (an entry may lack any of the four lists). The case was first reproduced with a new rig scenario; the other commands (`verify`, `backup`, `import`, `clean`, `list`, `export`,
  `trash`) and `download` with `-ids`, `-skipids` and a dry run were checked with old entries and work, and now have tests.
- **Fixed (finding F): `clean_target_problem` stopped with a `TypeError` for a file of the manifest whose name is not known yet** (an unreleased extra has `name` = None). It is the check that clean runs
  on the folder it is given, and it looks through the files of the games when no game folder is inside: the very case of a clean started on the folder of one game, where it should print its explanation.
  An entry without a name is skipped now.
- **New tests: `--dryrun` and the file-name check (0.5.89).** A dry run refuses the same five names with one warning and one summary entry each, writes nothing and counts the same files as a dry run without
  the bad entries.
- **Fixed in the tests: every test run left folders behind in the temporary folder.** `_bootstrap.py` made a `gogrepo_delta_tests_*` folder for the configuration file and never removed it (110 had piled up in
  one working session); it is removed when the process ends now. The scratch folder `gogrepo_delta_cwd_*` was also meant to be removed at exit, but that never worked on Windows, for two reasons: a folder cannot be
  deleted while it is the current folder of the process, and not while a file in it is open (a test that runs `main()` attaches the script's log handler, which then holds `gogrepo.log` in that folder open;
  at the end of a full run the folder holds that file and the process is inside it), and the removal ignores errors, so Windows kept one folder after every run (found by the new test on his Windows).
  `remove_scratch_dir` now leaves the folder and closes the log files first. Two tests start a Python that imports the bootstrap: both folders are gone afterwards, and before the cleanup the process is in the
  folder and the log file is open (the child does what `main()` does), afterwards neither (the two conditions Windows needs, checked on every system). You can delete the old folders: in PowerShell
  `Remove-Item "$env:TEMP\gogrepo_delta_tests_*", "$env:TEMP\gogrepo_delta_cwd_*" -Recurse -Force`.
- **Fixed in the tests: three test classes left their temporary folders on Windows** (`cleanorph_*` from `test_clean_orphaning`, `cleanup_incomplete_*` from `test_cleanup_incomplete_metadata`, `resumeretry_*` from
  `test_resume_retry_limit`; seen on a screenshot of his temporary folder: the files were deleted, the folders stayed). Each registered the cleanup that changes back to the old folder before the cleanup that removes
  the temporary folder, and `addCleanup` runs in reverse, so the folder was removed while the process was still inside it (Windows refuses, and `ignore_errors=True` hid it). The order is swapped.
  `tests/test_cleanup_order.py` reads all test files and fails for this order (and for a `tearDown` that removes the folder before it changes back); it runs on Python 3.8 (no `ast.unparse`).
- **Fixed in the tests: the download rig left its working folder behind, and its fake server running, when a scenario failed while it was set up** (found by looking at what a full test run leaves in the
  temporary folder: the test with a scenario that does not exist left a `rig_*` folder every time). `_run` now stops the server and removes the folder before it raises; a test checks both.
- **Tests:** `tests/test_cli_main.py` (7), `tests/test_old_entries_and_unnamed_files.py` (14), `tests/test_bootstrap_cleanup.py` (2), `tests/test_cleanup_order.py` (2), and in `tests/test_download.py` 8 more with 5 new rig scenarios (and 1 in `tests/test_old_python_support.py`)
  (`unsafe_file_names_dryrun`, `old_manifest_ids`, `old_manifest_skipids`, `old_manifest_dryrun`, `old_manifest_leftover_ids`). 14 mutations of this change were checked; 12 were caught, one was first missed
  (an old entry that also lacks `extras`, which got a test) and one is an equivalent change of the same behaviour. The scratch folder cleanup was checked with 3 more, and the order guard with the wrong order put back in one test: all caught.

## 0.5.91 - 24.11.2026 - the rest of the path: game folder, MD5 XML folders, and a warning for paths over 259 characters on Windows

The remaining parts of the known issue "only the file name is made portable". The survey of a real library (`gogrepo_survey_names.py`) found no names that differ only in case or Unicode form and no
non-ASCII names, so those two stay out; what was left is cheap hardening and the Windows path length.

- **Changed: the folder of a game is made portable where `update` builds it** (`_game_folder_name`): the slug GOG sends, plus the suffix of movies (`-movie`) and of duplicate titles (`_ID`), goes through
  `portable_file_name` (one warning when that changes it; the title stays the slug). GOG's slugs are letters, digits and `_`, so nothing changes today. A folder that was stored under another name gets
  the existing rename marker (`old_folder_name`) from the normal update merge, and the next download, verify or clean moves the folder on disk, as for any change of the folder name.
- **Changed: the MD5 XML tree checks its three folders** (game folder, operating system, language) in `save_manifest`: an unsafe one is skipped and collected into one combined warning. A test checks that
  every language and operating system name of the script's own tables is portable.
- **New: warning for a path over 259 characters on Windows without long path support.** Windows refuses a path of 260 characters or more (the last one is the terminating NUL). When a file is about to be
  downloaded, the longest of its three places (`LIBRARY\GAME\NAME`, `LIBRARY\!downloading\GAME\NAME`, `LIBRARY\!downloading\!provisional\GAME\NAME`) is measured; over 259 characters the file is added to one
  combined warning that names the count, the files and the two fixes (registry value `LongPathsEnabled` = 1, or a shorter library path). **Warn only: the download is tried anyway** and no failure is counted, because
  the system's answer is better than a guess; if it refuses, the file is reported as failed as before. `_windows_path_limit_in_effect` is true only on Windows and only when `LongPathsEnabled` is not 1 (also
  when the value cannot be read); on Linux and macOS nothing is measured. A file that is already up to date is not mentioned.
- **New: `gogrepo_survey_names.py`, a separate file next to the script.** A read-only survey of the manifest: names that differ only in case or Unicode form, non-ASCII names, the longest `GAMEFOLDER\NAME`, the longest library
  path that still fits, and with the library path as argument the files that would be over 259 characters.
- **Fixed on the way: three test problems of 0.5.90 on Windows, none in the script.** (1) NTFS does not refuse `setup:2.exe`; it writes the stream `2.exe` of a file `setup`, so the test's check for a file
  system without colons never skipped. A helper (`create_file_named`) now checks that the name exists as given, with tests for it that simulate NTFS. (2) `os.path.join(folder, 'a:b.exe')` is `a:b.exe` on
  Windows: a name whose second character is a colon is taken for a drive and the folder is thrown away, so the test of a refused name tried to create a folder `a:`. (3) A test that a MD5 XML file was *not*
  written joined its path the same way, so it could never fail on Windows. `path_in(folder, name)` (folder, separator, name) now builds such paths in the tests. The same join behaviour is one more reason why
  a `:` in a name is refused before any path is built from it: on Windows `c:evil.exe` would be written to the current folder of drive C.
- **Fixed in the tests of this entry: the path-limit tests no longer depend on the length of the temporary folder.** They assumed a short one; the macOS runner of the CI has about 60 characters, so the library path
  of the test was already near the limit and `short.exe` counted as too long as well (4 files instead of 3). The test now fills one folder so that the longest of the three paths is exactly 200 characters,
  whatever the temporary folder is, and skips when that folder is too deep (over about 165 characters) to do so.
- **DIFFERENCE: on Windows without long path support, `download` may now print one warning about long paths.** Nothing else changes: no file is refused or renamed because of its path length.
- **Tests:** new `tests/test_portable_paths.py` (18 tests: the folder helper, `update` with unsafe and duplicate slugs and with a folder stored under another name, the three MD5 XML folders, the path limit
  with the boundary of exactly 259 and 260 characters, the combined warning, the three places, an up-to-date file, and the detection with a simulated registry including a missing `winreg` and an unreadable value).
  21 mutations of this change were checked and all were caught (one was first missed, a registry value other than 0 or 1, and got a test).

## 0.5.90 - 24.11.2026 - portable file names: made portable where update stores them, old manifests migrated, every place that uses a name guarded

The second half of the known issue "file names from a download address are not checked", and the rename that entry 0.5.89 left out. Until now a name that Linux, Windows and macOS do not all accept was
only refused when the file was queued for download. Now `update` stores a portable name in the manifest, so every command sees the same name as the disk, a manifest from before is migrated by `update`,
and every place in the script that joins a manifest name to a folder checks the name.

- **New: `portable_file_name(name)`.** Every character that `unsafe_file_name_reason` refuses becomes `_` (a path separator too: `../../x.exe` becomes `.._.._x.exe`); a trailing space or dot is dropped;
  a name that is empty or only dots becomes `_`; a Windows device name gets a `_` in front (`CON.txt` becomes `_CON.txt`); a name that is longer than 251 bytes is shortened to 240 bytes. A name that is
  fine is returned as it is, and the result is always fine, so a second run changes nothing (a test checks 20,000 random names for both).
- **New: shortening.** The start of the name, `~`, 8 characters of the SHA-1 of the whole name and the extension (kept when it is 16 bytes or less): two long names that start alike stay different, the same
  name always gives the same result, and a character is never cut in the middle. The limits are bytes of UTF-8, which fit ext4 (bytes), APFS (characters) and NTFS (UTF-16 units); 251 leaves room for the
  `.xml` of a MD5 XML file and 240 for the `(1)` of the duplicate rules.
- **Changed: `fetch_file_info` stores the portable name.** This is where `update` takes the name from the address. When it differs from what the server sent, the manifest entry also gets the field
  `name_from_server` with the original (only then; an entry whose name is fine has no such field, and a field that is no longer true is removed), and one warning says what was stored instead.
- **New: `migrate_unsafe_file_names`, run by every `update` right after the manifest is loaded.** Every file (installers, Galaxy, shared, extras) whose stored name is not portable gets the portable name; its old
  name goes into `old_name` (unless a rename is already waiting there, which keeps the older source) and into `name_from_server`. A new name that another file of the game has already (case ignored) gets
  `(1)`, `(2)`, ... by the duplicate rules. No network and no file is touched: the files on disk are renamed by the rename handling that `download`, `verify` and `clean` already run first, with its checks
  for a destination that is already right. The manifest is saved at once (an update that finds nothing new would not save it otherwise), one line per file says what was renamed, and the summary counts
  `file names made portable`. A second run finds nothing.
- **Changed: every place that joins a manifest name to a folder refuses a name that is not portable**, with one warning and one entry in the run summary (`GAME/NAME`, "refused, reason"), then goes on with
  the next file. The warning now ends with "run update to give it a portable name". The places: download (since 0.5.89), `verify`, `backup`, `import`, the MD5 XML files written by `save_manifest`
  (collected into one warning, as no entry is wanted for each of the many saves), and the rename handling (a *new* name that is not portable is refused; an *old* name that is not a file of the game's folder,
  that is empty, `.`, `..` or with a separator, cannot be moved, so the marker is dropped with a warning, but not in a dry run). The old name of a rename may still hold `:` and the like: that is the
  file that has to be moved. `clean` and the orphan code only compare names with the file listing of a folder and join nothing, so they needed no change.
- **Fixed on the way: the lookup of the other parts of a split ZIP (`x.zip.001`, `.002`) did not escape the name for `glob`.** A name with `[` could not find its parts (`?` and `*` cannot be in a name any more).
- **DIFFERENCE: `update` stores another name than the server sent when that name is not portable**, and migrates the names already in the manifest. Nothing on disk changes until the next `download`, `verify` or `clean`.
- **DIFFERENCE: a name over 251 bytes is refused (download, verify, backup, import) and shortened by update.** Before, only the file system refused it, when the file was written.
- **DIFFERENCE: `verify`, `backup`, `import` and the rename handling report and skip a name that is not portable**, and the run ends with exit status 1; they trusted the name before. A manifest that `update` has
  migrated has no such names, so this only shows for a manifest that was not updated yet.
- **DIFFERENCE: the manifest can hold the new field `name_from_server`.** Older versions of the script keep it and ignore it.
- **Not changed:** what a refused name does in `download` (0.5.89). Not covered, now listed in the known issues: the rest of the path (folder names, total path length, Unicode forms).
- **Tests:** new `tests/test_portable_names.py` (32 tests: the cases of the rule, 20,000 random names, the limits and the shortening, the numbering of clashes, the migration (all four lists, old entries without
  lists, clashes with case, a waiting rename, a second run, entries without a name), `fetch_file_info` with a made-up redirect, `update` end to end with a manifest from before (names, saved at once, summary count,
  and the file renamed on disk by the next rename run), and `verify`, `backup`, `import`, the rename handling, the MD5 XML files and the ZIP lookup with `../evil.exe` and `a:b.exe` entries, each checked for
  files that must not appear outside the game folder). 40 mutations of this change were checked and all were caught (two were first missed, an early save in `update` and the case rule in the numbering, and
  got tests).

## 0.5.89 - 24.11.2026 - file names are checked when a download is queued (known issue)

The first half of the known issue "file names from a download address are not checked". A file name is the last part of the address GOG's server redirected to, after `unquote()`,
so `..%2F..%2Fx.exe` arrives as `../../x.exe`. `_queue_item_downloads` joined it to the game's folder as it was. Now a name is checked first, and a file whose name is refused is not
downloaded. GOG does not send such addresses today; the check is for a server (or a changed address) that does.

- **New: `unsafe_file_name_reason(name)`.** Returns `None` for a name that can be a file name on Linux, Windows and macOS alike, otherwise a short reason. The goal is a library that can be copied
  between the three systems, so a name is refused if any one of them would refuse it: empty, `.` and `..`; a `/` or `\`; any of `< > : " | ? *`; a control character (0-31 and DEL); a trailing
  space or dot (Windows drops it, so the file would get another name); a Windows device name, with or without an extension and in any case (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`,
  `LPT1`-`LPT9`, also with the superscript digits 1-3, `CONIN$`, `CONOUT$`: `con.txt` and `NUL.tar.gz` count). Not refused: anything else, including spaces inside or at the start of
  a name, parentheses (`the.art.of.playing.(2014).1080p.mp4`), non-ASCII letters and a name that is longer than 255 bytes (a file system refuses that one when the file is written).
- **New: refused files are reported and skipped, the rest goes on.** `_queue_item_downloads` checks the name after the `-skipfiles` test (a file that is skipped on purpose is not reported) and before
  any path is built from it. A refused file gets one warning (`     refused    NAME (reason)`) and one entry in the run summary (`GAMEFOLDER/NAME`, "refused, reason"), so the run ends with
  exit status 1; the other files of the game and the other games download as usual. Control characters in a name are shown as `\xNN` in both.
- **DIFFERENCE: an unsafe name that is already in the library is now also reported.** The check runs for every file that would be looked at, also one that is already downloaded and up to date. On Linux
  and macOS a file such as `setup:2.exe` can exist; it is left alone, but it is reported as refused from now on and the run ends with status 1. Nothing is renamed or deleted.
- **NOT changed (known issue, narrowed):** the other places that join a manifest name to a folder (`save_manifest` for the MD5 XML files, `handle_game_renames`, `verify`, `backup`, `clean`) do not check
  it. Renaming a refused file on the fly (for example `:` to `_`) was considered and not done: the manifest name is what `verify`, `clean`, `backup` and the up-to-date test compare with the file on disk,
  so a file saved under another name would look missing and be downloaded again, and two names could become the same name. It needs the name to be changed where `update` stores it, which is a separate change.
- **Tests:** new `tests/test_file_name_safety.py` (15 tests: safe names, every character of the set and every control character at the start, middle and end of a name, trailing space and dot, device names,
  escaped display, and `_queue_item_downloads` with a refused name: one warning and one failure each, the good files queued, nothing created outside the game folder, `-skipfiles` not reported, a refused file that is already in the library is reported and left alone);
  `tests/test_download.py`: 2 more with a new rig scenario `unsafe_file_names` (five bad names in two groups of one game: the server is never asked for them, the folder tree equals the plain fresh download,
  one warning and one summary entry each). 16 mutations of this change were checked and all were caught.

## 0.5.88 - 23.11.2026 - dead code removed from the download path (known issue)

The known issue "unreachable code is kept as it was" listed three spots. Each one was checked before anything was removed; two were removed, one was wrong.

- **Removed: the `folder_name` default in `cmd_download`.** `handle_game_renames` runs first on the same list and, at the top of its loop and before any `continue`, gives every game
  `galaxyDownloads`, `sharedDownloads` and `folder_name` (also in a dry run). The `try ... except AttributeError` loop after it could never run.
- **Removed: the `galaxyDownloads` and `sharedDownloads` defaults in `_item_download_lists`.** Its only caller is `_process_download_item`, whose only caller is `cmd_download`, after the
  renames above. The docstring now says what the function relies on.
- **Removed: the `SSLError` handler in `_download_ioloop`.** `requests.exceptions.SSLError` is a subclass of `ConnectionError` (checked with `issubclass`, requests 2.34.2; it has been
  one since requests 1.x), and the handler for `ConnectionError` stands first, so the "SSL issue while downloading" message was never printed. An SSL error is reported, as before, as
  "server response issue while downloading content for ..."; what arrived is kept and the response is closed. `ChunkedEncodingError` is not a `ConnectionError` and keeps its own handler.
- **NOT removed: `os.makedirs(dest_dir)` in `_prepare_download_file`.** It looked dead because the game's folder is made before, but the final file is `game folder + name`, and a name taken from
  a download address can hold a separator (see the new known issue). The check also found that such names are not validated at all; that is now a known issue with a planned
  hardening, not part of this cleanup (it would change what the download refuses).
- **No change in behaviour.** The download tests (rig and unit) pass as before.
- **Tests:** new `tests/test_download_preconditions.py` (5 tests: `handle_game_renames` gives the three attributes to every game it is handed, in a dry run too, and not to games that are only in
  the directory list; the download helper works on that result; `_prepare_download_file` creates the folders, also for a name with a separator, which pins the code that was not removed);
  `tests/test_download_loop.py`: 2 more (a broken connection of any of the three kinds keeps what arrived, is reported and closes the response; `SSLError` is a `ConnectionError`, the reason for
  the removal, so a change in requests is noticed); `tests/test_download.py`: 1 more with a new rig scenario `old_manifest_entries` (a manifest without `folder_name`, `galaxyDownloads` and
  `sharedDownloads` is downloaded into the title folders). 11 mutations of this change were checked and all were caught.

## 0.5.87 - 22.11.2026 - three known issues fixed

Three of the known issues, the cheap ones; they are removed from the list above.

- **`HTTP_FETCH_DELAY` is deleted.** It was defined and never used (no code, test, README text or config key referred to it), so it never had an effect and was not a setting
  in the config file. `HTTP_RETRY_DELAY` and `HTTP_RETRY_COUNT` are the settings that count. Making it a real delay between requests would change the download behaviour; that is
  not part of this entry.
- **The file names in the combined "No MD5 data was available" warning are listed in alphabetical order.** The worker threads report them in any order, so the list differed from
  run to run. `flush_summarised` now sorts the names of every combined warning (this is the only condition that uses it): not case-sensitive (`A.exe`, `a.exe`, `B.exe`), a tie
  keeps capitals first, otherwise plain text order (`patch_10.exe` comes before `patch_2.exe`). When there are more names than `summary_max_items`, the names shown are the
  alphabetically first ones, so the same files give the same warning on every run.
- **An old-format manifest with data of the wrong type is damaged, not accepted.** A manifest in the old format that held valid data that is not a list of games (a bare number,
  text, a tuple) or a list with entries that are not records was accepted by the loader and failed later. `parse_manifest_text` now raises `ManifestDamaged` ("the old-format data
  is of type int, not a list of games", "the old-format list holds entries that are not games"), which goes through the existing recovery like any damaged manifest: the damaged
  file is kept, the backup copy is offered, and without a backup the run stops with the usual message. A backup of the wrong type is not used. An empty old-format list is a valid
  empty library, as before. The JSON format already checked its structure.
- **Tests:** `tests/test_summarised_warnings.py`: the test of the cap listed the names in the order they were reported and asserted that `file19.exe` is not shown; with sorted names it
  is among the first 15, so it now expects the alphabetically first 15 (one test adapted), and 2 more tests (the order, and the same warning in any order). `tests/test_manifest_recovery.py`:
  5 more (wrong types with the backup, the two messages, no backup, a wrong-type backup, and the empty list that stays valid). 9 mutations of these changes were checked.

DIFFERENCE: the order of the names in a "No MD5 data" warning is now alphabetical; a wrong-type old-format manifest goes to recovery instead of failing later.

## 0.5.86 - 21.11.2026 - the resume file: braces in old-format files (finding A) and a damaged file no longer becomes a fresh update (finding B)

Findings A and B of the 0.5.76 review, in one patch.

- **A: an old-format resume file is read without changing its text.** `load_resume_manifest` replaced every `{` and `}` of the text, which also changed braces inside
  titles, changelogs and other strings. It now gives the text to `_load_legacy_literal` (which reads Python literals and never runs anything, and removes only the
  `AttrDict(**{...})` wrapper tokens), after the old `'size': 5L,` fix. The default JSON format was not affected.
- **B: only a missing file means "no resume file".** Before, any `IOError` returned an empty list, and `cmd_update` wrapped the whole resume setup in `except Exception`
  that set `resumedb = None`: a cut-off, non-text, wrongly built or unreadable resume file, or a wrong-typed `failure_counts`, silently became a fresh update.
  Now `load_resume_manifest` returns `[]` only for `FileNotFoundError`. A file that cannot be read (permission, folder instead of file, not UTF-8), whose JSON or old-format
  text is damaged, or that holds no list of games and properties, stops the run: one message that names the file, says it only remembers what an unfinished update
  still has to fetch, that nothing was changed, to delete it (or copy the `.bak` over it, if there is one), and exit status 1. Nothing is fetched or written first.
- **The properties record is checked** (new `check_resume_manifest`, called by `cmd_update`): the last entry is a record, every game entry is a record, `failure_counts` is a
  table of text ids and whole numbers of 0 or more (or absent), `complete` is yes or no and, in a file of the current version, present; a current-version file that is
  not complete also needs `os_list`, `lang_list` (lists), `installers` (text) and `strict` (yes/no), which resuming reads directly. Each failure gives the same kind
  of message and stops. A file of another version is left to the question below. `load_resume_manifest` itself checks only the file as a whole, so tests and tools that
  build partial records still work.
- **The question about an incompatible resume file no longer relies on `input()` failing.** Without a terminal (`EOFError`, as in a scheduled task) the run stops with a
  message and exit status 1 instead of silently discarding the file, as the broad `except` used to do. Answering `D` discards, `A` aborts, as before; a complete file of
  another version is still discarded without asking.
- **DIFFERENCE: `--resumemode noresume` also stops for a damaged resume file** (it still reads the file for the failure counts, and writes it again later). Delete the file to go
  on. A resume file that used to be ignored by accident (for example one without `complete`) now stops the run.
- **Tests:** new `tests/test_resume_loading.py` with 34 tests (braces and `5L` in old-format files, the text is not run as code, a missing file, truncated / garbage / empty /
  non-list / non-text / unreadable / permission-denied files and the `.bak` hint, every check of the record, `cmd_update` stopping before any request and leaving the file
  unchanged, `noresume` with a damaged file, resuming a good file in both formats, and the incompatible-version question with `D`, `A`, no terminal and a complete file).
  The real resume file of the maintainer (JSON, an unfinished update of 77 games with movies on) was run through the new loader and checks once, offline, and passed.
  `tests/test_update_warning.py` had two tests that simulated "no resume file" by making `load_resume_manifest` raise `IOError`, which only worked because the old broad `except`
  swallowed it; they now return `[]`, the loader's answer for a missing file (no behaviour change).
  26 mutations were checked: 24 were caught at once; one survivor was a missing test case (a non-list old-format file); one showed a real gap (a file of the current version
  without `complete` was not flagged), fixed in the code with a test; the last, a different default for `complete` inside `needresume`, changes nothing after that check.

## 0.5.85 - 21.11.2026 - `list` keeps the games that have no installer; a resumed update keeps `-movies`

- **`list` no longer hides games that have no installer at all when `-os`, `-skipos`, `-lang` or `-skiplang` is used.** A game with only extras (like
  `gwent_the_witcher_card_game` and `hotline_miami_2_wrong_number_digital_comics` of the maintainer's manifest) or with no files has no installer that could pass the
  filter, so it was dropped, although `download` takes the extras of such a game whatever `-os` and `-lang` say (extras belong to no system or language). The filters
  decide about installers: now a game is hidden only if it has installers and none of them fits. The games without installers show `-` in OS and LANG, as before
  without a filter; extras still count in FILES and SIZE. A game with installers for another system only (and extras) is still hidden: otherwise `list -os windows` would
  show Linux-only games. `update`, `download` and the other commands were not changed (checked: `update` keeps such games, `download` keeps their extras).
- **A resumed update keeps `-movies` and `-moviequality` of the request.** When `update` found an unfinished update, it ran the resume pass with the settings saved
  by the interrupted run and then started the requested update again, but that restart did not pass `-movies` and `-moviequality` on: a request with `-movies` fetched
  no movies at all after a resume pass. The restart now gets the values of the request, saved before the resume pass replaces them (`save_movies`,
  `save_moviequality`, like the other `save_*` values). The resume pass itself is unchanged: it still uses what the interrupted run saved.
- **A test that pinned the old behaviour was rewritten.** `test_an_old_resume_file_without_the_settings_means_no_movies` ran its request with `movies=True` and asserted that no
  movie is fetched; that was the bug. It now runs without `-movies`, and a new test covers what it meant (the resume pass has no movies; the restart of a request with
  `-movies` fetches them, with the request's `-moviequality`).
- **Tests:** `tests/test_movies.py` has 3 more for the resume restart (the resume pass with the saved settings and then the request with its own, a resume with `-movies`
  and `-moviequality`, and no movies when the request has none while the movies in the manifest are left alone), 1 rewritten (above), and 3 more for `list` (games without
  installers with every filter, games whose installers do not fit are still hidden, words / ids / tags with them and the "but none has files" message). 8 mutations of
  these changes were checked and all were caught. Observation: the real GOG answer in `tests/data/movies` tags every
  movie `MOVIE`, so `list -tags MOVIE` works even without tags of your own.

DIFFERENCE: `list` with `-os` / `-lang` shows more (the games without installers); `update -movies` after an interrupted update now really fetches the movies.

## 0.5.84 - 20.11.2026 - `-notags`: only the games without any tag, in all six commands

- **New switch `-notags`** for `list`, `update`, `download`, `verify`, `import` and `backup` (and `notags = yes` in the config file). It selects only the items that
  have no tag at all in your GOG library, movies included, for example to find what you have not sorted yet: `list -notags`. It is the missing counterpart of `-tags`:
  before, items without tags could only be reached by `-skiptags` with the name of every tag you have.
- **Rules.** `-notags` and `-tags` exclude each other (argparse refuses the pair; in the config file, the option typed on the command line wins and the other one
  from the file is dropped, as with `-os`/`-skipos`). `-notags` can be used with `-skiptags`, `-ids`, `-skipids` and the other filters; an item must pass all of
  them. If nothing is left, the command stops and says so (`no game without tags in the manifest`, `... matches -ids`), it never falls back to "all games"; `list`
  fails the run (exit code 1) as it does for `-tags`.
- **Safe with old data.** A manifest entry that has no `tag_names` field at all (never refreshed) is *unknown*, not "without tags", so `download -notags` can never
  pick games only because their tags have not been read yet. A manifest with no tag data at all stops with the usual message to run `update` once.
- **`update -notags`** uses the tags GOG sends in that very run (`item.tag_names`), like `-tags` and `-skiptags`; the tags of the games not fetched are refreshed, and
  a run limited by `-notags` never removes games from the manifest. A resumed update keeps `-notags` (`cmd_update` passes it on when it restarts itself).
- `select_games_by_tags()` and `cmd_list()` have a new last parameter `notags=False`; `cmd_update()` too. The README and the help text are updated.
- **Tests:** `tests/test_tags.py` has 18 more (selection, ids for the id-based commands, a manifest without tag data, entries without tag data, the options in every
  command, `-tags` plus `-notags` refused, dispatch to `verify`, `update` and `list`, and `update` with `-notags` with fresh tags, with `-skiptags`, never removing
  games, the narrowing check, and a resumed update); `tests/test_movies.py` has 2 more (movies without tags in `list`, nothing left); `tests/test_config.py` has 1
  more (`notags` from the file, and the exclusion with `tags`). 16 mutations of this change were checked; the 3 that survived at first (dispatch of `update`, the
  narrowing check, the restart of a resumed update) got their own tests.

DIFFERENCE: only a new option; nothing changes without it. If you set `notags = yes` in `[common]`, every command that takes tags obeys it.

## 0.5.83 - 20.11.2026 - `list` takes `-tags` and `-skiptags`

- **`list` can be limited by the tags of your GOG library.** `-tags TAG ...` lists only the items that have one of the tags (any of them), `-skiptags TAG ...` leaves
  out the items that have one of them. The rules are those of `update`, `download`, `verify`, `import` and `backup` (`select_games_by_tags()` is reused): case,
  accents and punctuation do not matter; a tag that no item has is an error that lists the tags that exist (and hints at a tag with spaces typed without quotes);
  a manifest without tag data says to run `update` once; `-skiptags` wins over `-tags`. In `list` the tags are one more filter next to the words, `-os`, `-lang`
  and `-format ids`: an item must pass all of them. A filter that leaves nothing says so (`no game matches the tag filter: ...`) and the run fails (exit code 1),
  like the other filters of `list`. Nothing is listed and no tag filter is ever turned into "all games".
- **This also selects movies.** The tags of movies are stored like those of games (`tag_names`), so after you tag your movies in your GOG library and run `update`
  once, `list -tags Movies` shows only the movies. This was the way to list only the movies: `-os` cannot do it (the files of a movie belong to every operating
  system), and `video`/`vid` is no operating system. Checked by the maintainer on a real manifest: movies are tagged there. A `-media game|movie` option for
  `list`, `download`, `verify`, `backup` and `update` is a later idea.
- **No tags column** in the table: an item can have several tags, so the lines would get long.
- The line `N of M games` still counts the whole manifest as M.
- `cmd_list` has two more parameters at the end (`tags=()`, `skiptags=()`); the README (`list`, tag section) and the help text describe the options. The config
  file keys `tags` and `skiptags` now also apply to `list`, as they do to the other commands.
- **Tests:** `tests/test_config.py` has 1 more (`tags` and `skiptags` from `[common]` and `[list]` reach `list`); `tests/test_movies.py` has 6 more (movies selected by tag, several tags and case, `-skiptags` wins, with `-os`, words and `-format ids`, an unknown tag, a
  manifest without tag data, a filter that leaves nothing, and `list` without tag options unchanged); `tests/test_tags.py` has 2 more and `list` joined the test of
  which commands accept the options. 9 mutations of this change were checked; the one that survived at first (the failure of an empty filter) got its own test.

DIFFERENCE: only new options; `list` without `-tags` and `-skiptags` behaves as in 0.5.82. If your config file sets `tags =` or `skiptags =` for all commands, `list` now obeys it too.

## 0.5.82 - 20.11.2026 - `list`: movies are shown with an -os filter, and an invisible character no longer shifts the columns

- **DIFFERENCE: `list` shows movies when `-os` (or `os =` in the config file) is in use.** The files of a movie have the operating system `video`, so the filter
  `-os windows` never matched them and a movie was left out as a game with no files for that system. `list` now uses `os_selected()` like `update`, `download`, `verify`
  and `backup`: the files of a movie belong to every operating system. `-lang` and `-skipos` are unchanged (a movie still has a language, and `-skipos` only
  leaves out the systems that are named). The `-os` help text of `list` was not changed.
- **A column shift in `list` is fixed.** The width of a text on the screen (`_display_width`) counted every character as one column except combining accents and wide
  Chinese, Japanese and Korean characters. Characters that take no room (byte-order mark U+FEFF, zero-width space and joiner, soft hyphen, variation selectors, control
  characters) were counted as one, so the row was padded too little and every column after the name moved one place to the left. Found in a real manifest: the long
  title of MouseCraft is `'MouseCraft\ufeff'`. The new helper `_char_width` counts them as zero (Unicode categories Mn, Me, Cf, Cc); `_fit` uses it too. The text
  itself is not changed, in the manifest or on the screen.
- **Tests:** `tests/test_ids.py` has one more (invisible characters in `_display_width`, `_pad` and `_fit`); `tests/test_movies.py` has 3 more (movies with `-os`,
  `-lang` and `-skipos` still working as described, and a row with a byte-order mark stays aligned). 4 mutations of these changes were all caught (one only after
  the test for `_fit` was tightened).

## 0.5.81 - 19.11.2026 - Unattended runs: a missing manifest stops the command, -usebackup; Python 3.8 failures fixed

- **DIFFERENCE: `download`, `verify`, `import`, `backup`, `list`, `export` and `diagnostics` stop when there is no manifest.** Before, a missing manifest without a backup was
  read as "the first run": an empty list, nothing to do, and exit status 0. In a scheduled task that starts in the wrong folder (the manifest is read from the current
  folder) that looked like success. Now the command ends with exit status 1 and one message: `The manifest '/path/gog-manifest.dat' does not exist (the manifest is
  read from the current folder, '/path'), and there is no backup copy. 'download' needs it, so nothing was done. Run it from the folder that holds the manifest, or run
  'update' first to make one.` `update` (builds the manifest), `wishlist` (only marks the games you own) and `clean` (its own, more specific refusal) are unchanged. A
  manifest that exists but lists no games is not "missing". The rule is the new argument `load_manifest(require_existing=True)` of those commands, not a global state
  (a first version that used the current command name was refused for `update` by a test that had left another name behind).
- **`download` reads the manifest before the token.** It used to make the GOG session first, so a scheduled `download` in the wrong folder first read the token (and with an
  encrypted token asked for a password) before it found out that there was no manifest. A test runs all seven commands with the network and the token patched to fail.
- **New option `-usebackup` (all commands, like `-manifestformat`; `--usebackup` in the README).** When the manifest is missing or damaged and `gog-manifest.dat.bak`
  exists, the backup is used **without asking**: the backup is checked first (if it is not usable either the run stops and changes nothing), a damaged manifest is kept as
  `.damaged`, a warning says `-usebackup was given`, and the summary counts `manifests restored from the backup copy`. This is for runs that cannot be asked; without the
  option they stop as before, and the message now names the option. With no backup it changes nothing (a run that cannot ask still stops). The option is switched on and
  off by every run (it does not stay on). **It can also be a default of the config file:** `usebackup = true` under `[common]` (the new config file has the line, explained,
  set to `false`), so that a machine that only runs scheduled tasks needs no option on every command line.
- **Python 3.8 (log of the best-effort job, 83 failed, 1328 passed): one cause.** The download test rig (`tests/download_rig/rig.py`) made its test files with
  `random.Random(seed).randbytes(size)`, which exists only from Python 3.9: 81 tests failed with `AttributeError`, and two tests of `test_isolation` failed because the rig
  had already changed the working folder when it crashed and did not change it back. The rig now builds the same bytes with `getrandbits(8 * size).to_bytes(size, 'little')`
  (that is the definition of `randbytes`; every fixture and hash stays valid), and `rig.run` always restores the working folder. No failure of the log was in the program.
- **A static check keeps it that way** (`NoNewerPythonFeaturesTests`): the program and every test file are read as a syntax tree and refused for features newer than 3.8
  (`randbytes`, `removeprefix`, `functools.cache`, `zip(strict=)`, `glob(root_dir=)`, `zoneinfo`, `match`, ... ; the three guarded uses are listed with the reason). This
  could not run on 3.8 itself in the sandbox (Python 3.12 only): the next run of the best-effort job on GitHub is the real test of 3.8 and 3.9.
- **Tests:** `tests/test_unattended_manifest.py` (20 tests: the refusal for each command, `-usebackup` in every case that matters, the seven commands through `main` with the
  network and the token patched to fail, the option on every sub-command and off by default, not sticky, README); `tests/test_old_python_support.py` has 7 more (22); `tests/test_config.py`
  has one more (the config-file default). 23 mutations of these changes were all caught (two only after a test was tightened or added).

## 0.5.80 - 18.11.2026 - What the Python 3.9 job found: old-format manifests could not be read on Python 3.8 and 3.9

- **Bug fixed (found by the first run of the best-effort job on Python 3.9): `_load_legacy_literal` raised `IndentationError` on Python 3.8 and 3.9.** It reads the
  old pprint/`AttrDict` manifest format by removing the `AttrDict(**` ... `)` wrapper and calling `ast.literal_eval`. The removed wrapper leaves spaces in front of
  the text; Python 3.10 and newer ignore leading spaces and tabs, 3.8 and 3.9 do not. So a manifest in the old format (and other old-format files read this way) could
  not be loaded on 3.8 or 3.9, which the README promises to start (best effort). The text is stripped before `literal_eval` now; what is not a plain literal is still
  refused (`__import__(...)`, calls, attribute access).
- **Three more of the four failures were in the tests, not in the program:** `assertNoLogs` exists only from Python 3.10 (`tests/_bootstrap.py` has a stand-in that is
  installed only where the real one is missing), and the two Unicode tests compared the whole stderr of a child process with an empty text although the program prints
  its one-line warning on a Python older than 3.10 (`without_old_python_warning` removes exactly that line and nothing else).
- **The best-effort job now tries Python 3.8 as well as 3.9** (the README lists both; it was set up for 3.9 only, and the maintainer pointed out that 3.8 is still
  offered by the runners). Job `best-effort`, a matrix of 3.8 and 3.9 with `fail-fast: false`, still the only job with `continue-on-error: true`. It runs on
  **`ubuntu-24.04`, not `ubuntu-latest`**: the first run showed that `ubuntu-latest` could not provide Python 3.9 (change made by the maintainer, now in the file with the
  reason). 3.8 could not be tried in the sandbox this was made in (it has Python 3.12 only): a static check of the program and the tests found no syntax and no
  library call newer than 3.8 apart from those named above, but the first run on GitHub is the real test, and a red entry for 3.8 is information, not a defect of the
  workflow. The README (table and list) now says the CI tries both.
- **Tests:** `tests/test_old_python_support.py` (15 tests, one skipped on a Python that has the real `assertNoLogs`): the legacy literal loads with a
  `literal_eval` that imitates the one of 3.9 (the failing case of the CI run, a list of wrapped items, text with leading spaces or tabs, and text that must still be
  refused); the stand-in for `assertNoLogs` (passes, fails with the message, ignores lower levels, accepts a number and a logger object, leaves the logger as it was);
  the helper that removes the version warning, tested against the text that `check_python_version` really prints. `tests/test_repo_files.py` checks the new job (3.8 and 3.9,
  fail-fast off, `ubuntu-24.04`, the only one that may fail). The whole suite also passes with `assertNoLogs` removed from `unittest` (imitating 3.8 and 3.9). 14 mutations of
  these changes were all caught (one only with `assertNoLogs` removed, because this Python has the real one).

## 0.5.79 - 17.11.2026 - The actions of the release workflow are pinned to commit hashes

- **`build.yml`: every `uses:` line names a full commit hash with the version in a comment**, so that a moved or hijacked tag cannot change what builds, attests
  and uploads the release binaries (the workflow has `contents`, `id-token` and `attestations` write permissions). Nothing else in the file changed (only
  these four lines). `tests.yml` stays on version tags, as decided. The hashes were checked by the maintainer with `git ls-remote` on 17.11.2026, and each
  floating tag the workflow used was the newest release of its major version, so the pins run what the tags ran:

  | Action | Was | Now | Hash (a tag without `^{}` points at the commit itself) |
  |---|---|---|---|
  | `actions/checkout` (2 uses) | `@v6` | `v6.1.0` | `d23441a48e516b6c34aea4fa41551a30e30af803` |
  | `actions/setup-python` | `@v6` | `v6.3.0` | `ece7cb06caefa5fff74198d8649806c4678c61a1` |
  | `actions/attest` | `@v4` | `v4.2.2` | `1e69f48acb82d1966a394da916b4c1698aa569d6` |

  For comparison, `actions/checkout` v6.0.3 is `df4cb1c069e1874edd31b4311f1884172cec0e10` (the `^{}` line of an annotated tag). `actions/checkout` v7.0.0 and v7.0.1
  exist; `dependabot.yml` (0.5.78) will propose them after the 14 days of cooldown. A pinned action no longer receives fixes by itself: that is what the monthly
  Dependabot pull requests are for. When one arrives, read what changed in the action (for `build.yml` the tests do not run it), then merge.
- **To update a pin by hand:** `git ls-remote https://github.com/actions/<name> 'refs/tags/<major>*'`, take the hash of the version you want (the `^{}` line if
  there is one), and change the hash and the comment of every `uses:` line of that action in `build.yml`.
- **Tests (`tests/test_repo_files.py`, 25):** every `uses:` line of `build.yml` has a 40-character lowercase hash and a comment `# vX.Y.Z`; no `uses:` line the test cannot
  read (a local action or a Docker reference would fail it, so a decision is needed first); the same action has the same hash and version everywhere in the file;
  and `build.yml` (hash plus comment) and `tests.yml` (tag) use the same major version of `actions/checkout` and `actions/setup-python`. The tests check the form
  and not the hashes themselves, so that a Dependabot pull request that changes them is not failed by the tests. Eight mutations (a tag, a short or uppercase hash,
  a missing comment, a comment without patch version, two different checkout hashes, a different major version, a `uses:` the test cannot read) were all caught.
- Nothing in this entry could be tried outside GitHub: the first published release shows whether the workflow resolves all four pinned actions.

## 0.5.78 - 17.11.2026 - CI: a best-effort job for Python 3.9, Dependabot for the GitHub Actions

- **New CI job `Best effort / Python 3.9 (may fail)`** in `tests.yml`: the whole suite on Python 3.9 with all packages. It is the only job with
  `continue-on-error: true`, so a failure there is visible (a red job) without failing the run. This is the "best effort" the README promises for 3.9;
  Python 3.8 is still not tested. It could not be tried in the sandbox this was made in (no Python 3.9 there): the first run on GitHub shows whether
  the suite passes on 3.9, and a red job is information, not a defect of the workflow. The README (table and list of requirements) says so.
- **`.github/dependabot.yml`:** Dependabot checks the GitHub Actions used in `.github/workflows` **once a month** and proposes a release only when it is
  **at least 14 days old** (`cooldown: default-days: 14`), so that a bad or hijacked release is usually found before it reaches you. Every pull request runs
  the tests; the release workflow (`build.yml`) only runs when a release is published, so read what changed in an action it uses. GitHub reports a mistake
  in the file under Insights > Dependency graph > Dependabot.
- `requirements-dev.txt` also lists `pyyaml` (the tests of the workflow files and of `dependabot.yml` read them as YAML; without it those tests skip).
- **Pinning the actions of `build.yml` to commit hashes** was decided here and done in 0.5.79 (it waited for hashes that the maintainer checked). Hashes found on the web for
  `actions/setup-python` and `actions/attest` came only from third-party pull requests and are not used. Verified so far, by the maintainer with
  `git ls-remote`: `actions/checkout` v6.0.3 is `df4cb1c069e1874edd31b4311f1884172cec0e10` (the `^{}` line of the annotated tag) and v6.1.0 is
  `d23441a48e516b6c34aea4fa41551a30e30af803` (a tag without `^{}` points at the commit itself). `actions/checkout` v7.0.0 and v7.0.1 exist as well; the
  workflows stay on v6 until Dependabot proposes the move and the maintainer accepts it.
- Tests: `tests/test_repo_files.py` has 6 more tests (23): the job for Python 3.9 exists, has a time limit and is the only one allowed to fail, 3.9 is not in the
  main matrix, the README calls 3.9 best effort in both places, and `dependabot.yml` is valid YAML of version 2 and says github-actions, `/`, monthly,
  cooldown 14. 11 mutations of these files were all caught (one only after the README test looked at both places).

## 0.5.77 - 17.11.2026 - CI and packaging: more Python versions, a required-packages-only job, requirements files, .gitattributes, .editorconfig

- **The tests now run on Python 3.10, 3.11, 3.12, 3.13 and 3.14** (the README says 3.10 or newer; the release binaries are built with 3.14). Python 3.10 and 3.14
  run on Ubuntu, Windows and macOS as before, 3.11 to 3.13 on Ubuntu only (nine jobs instead of six). 3.8 and 3.9 stay "best effort, not tested", as
  the README says; a test job for them would need a decision of the maintainer (they cannot be tried in the sandbox this was made in).
- **New CI job `Required packages only / Python 3.10`:** it installs only `html5lib`, `requests`, `psutil` and `pytest` and runs the whole suite, so
  that an optional package (`cryptography`, `blake3`, `html2text`, PyObjC) cannot become a requirement without anybody noticing. The main jobs install
  everything, so the tests of the encrypted token, BLAKE3 and the changelog text run for real there. The job found a real problem at once:
- **Tests fixed: 10 tests failed without the `cryptography` package** (`PasswordRetryTests` in `test_token_password.py` and two tests in
  `test_update_legacy_changelog_and_tokens.py`). They test the password prompts of an encrypted token file and cannot work without it. They are now
  skipped without the package, like the tests added since 0.5.73. The whole suite has been run with `cryptography`, `blake3` and `html2text`
  made unimportable: no failure, 38 skipped (2 of them are skipped with all packages). (`has_cryptography()` is in `tests/_bootstrap.py` now.)
- **`requirements.txt`, `requirements-optional.txt` and `requirements-dev.txt`.** Required packages, the optional ones (with `html2text>=2015.6.21` and PyObjC only on
  macOS) and everything for the tests. `tests.yml` installs from them instead of its own list (it was missing `html2text`; the release build has it).
  `pip` caching is on. The README names the files. `build.yml` is **not changed** (it cannot be tried outside GitHub and is not part of this entry);
  a test compares the packages it installs with the requirements files, so the two cannot drift apart unnoticed.
- **`.gitattributes`: text files are LF in the repository and in every checkout** (`* text=auto eol=lf`). A checkout with CRLF is what made patches fail on
  whitespace. **One step on the maintainer's computer after this change:** `git add --renormalize .` and commit what it shows (nothing, if the
  repository already has LF everywhere, as the archive of 0.5.76 has); the working files of a Windows checkout turn LF the next time git rewrites them
  (`git rm --cached -r . && git reset --hard`, after committing or saving your work).
- **`.editorconfig`:** UTF-8, LF, final newline, no trailing whitespace (not in Markdown, where two spaces are a line break), 4 spaces (2 in YAML and JSON).
  The program, the tests and the new files already follow it (a test checks that), so saving a file in an editor that reads it changes nothing.
- `tests.yml`: a time limit of 30 minutes for every job (a hanging test must not run for hours) and `concurrency`, so that a new push stops the
  run of the old one.
- **Tests:** `tests/test_repo_files.py` (17 tests): the workflows are valid YAML; one version of `actions/checkout` and `actions/setup-python` in both
  workflows; the test matrix has the oldest Python of the README and the newest is the one of the release build; every operating system of the release
  is tested; every job has a time limit; `tests.yml` has no package list of its own; the required-only job has no optional file; `build.yml` installs
  exactly the packages of the requirements files (plus `pyinstaller`); no package twice; every package the program imports at start is in
  `requirements.txt` and none of the optional ones is imported at start; the README names every package and the requirements files; `.gitattributes`
  and `.editorconfig` hold their rules; the program, the tests and the new files have no tabs, no trailing whitespace and a final newline. 17 mutations
  of these files were all caught (one only after the test looked at the main job alone).
- Not done: `build.yml` is unchanged (see above); no pinning of the actions to commit hashes and no `dependabot.yml` (both are decisions of the maintainer).

## 0.5.76 - 17.11.2026 - A game that can never be fetched is given up after a few retries (resume manifest)

- **DIFFERENCE: a retry limit for the resume manifest (handover open item 5, "0.5.50 risk").** A game whose details could not be fetched stays in
  the resume manifest so that the next update tries it again. That was for ever: while one game was pending, every `update` only resumed it and
  **never got to the update that was asked for** (`resume completed` / `returning to specified download request` came only when nothing was
  pending). A game whose details can never be fetched therefore held back all updates until `-resumemode noresume` was used by hand.
- New setting **`resume_retry_count`** in `[settings]` (default **3**, 0 or more): a failed game is tried again by that many later updates, so the
  first try plus 3 retries; the next failure gives it up. A game that is given up is removed from the pending list with a warning (`giving up on
  'game_002' (id 1002) for now: its details could not be fetched 4 times in a row ...`), the resume manifest is complete, and the update that was
  asked for follows in the same run. With 0 a game is given up at its first failure.
- **The failure is never hidden.** Every failed try is in the run summary and the exit status is 1, as before. A game that was given up is not
  retried by a resume pass any more, but every update that includes it (for example one that fetches games not in the manifest yet) tries it once and
  reports the failure again, until it works. For that the count is kept: the properties record of the resume manifest holds `failure_counts` (game id as
  text to number of failures in a row), also when the resume manifest is complete, and also with `-resumemode noresume`. A successful fetch removes
  the game from it. An older resume manifest has no `failure_counts` and starts at 0. The ids are text on purpose: with number keys the manifest
  did not read back identically from JSON and was saved in the old format with a warning (found by the new tests).
- **Not changed:** while a game still has retries left, the resume pass comes first and the update that was asked for waits (up to 3 extra runs for a new
  failure). An interrupted update (Ctrl-C) adds no failure. The first try counts: `resume_retry_count = 3` means 4 tries in all.
- The final warning now names the limit (`a game is given up after 3 retries`). README: a short paragraph under `--resumemode`.
- Tests: `tests/test_resume_retry_limit.py` (14 tests on a fake account API; the pending list, the counts in the manifest file, the exit status and
  the update that follows are checked across several runs); `tests/test_config.py` checks the new constant with a config file and the default.
  Thirteen mutations were all caught (one only after the config test was extended).

## 0.5.75 - 17.11.2026 - `clean`: one place that orphans a file; the dry run counts a file marked for change

- **Bug fixed (open item 7 of the handover): a dry run of `clean` did not count a file that the manifest marks as changed.** It printed `orphaning
  file ... as it has been marked for change.` and then `nothing to clean. nice and tidy!`, with no total. It now counts the file and prints
  `total size of newly orphaned files: ...` like for any other file. A dry run still moves and saves nothing.
- **Refactoring (D9 of the handover): the two copies of the code that move a file to the orphan folder are one function** (`_orphan_game_file`).
  The same files are chosen, in the same order, with the same messages, counts and exit status (the new tests that do not touch the bug pass on the
  0.5.74 code as well). The files chosen are the same: a file that is unknown to the manifest can never be in the list of files marked for
  change, so the two old conditions never both held and are now an if/elif.
- **DIFFERENCE: a file that cannot be moved is reported, never a crash and never "nothing to clean".** Making the folder inside `!orphaned` used to be
  outside the part of the code that catches errors (a crash with a traceback); it is inside now, and `exist_ok` is used. When nothing at all could be
  moved the run says `nothing could be moved to the orphan folder: see the errors above.` instead of `nothing to clean. nice and tidy!`. In a
  dry run a file that vanished meanwhile is a warning (`could not look at ...`), not a crash. A failed move is in the run summary and the exit status
  is 1, as before.
- `ensure_attribute(obj, name, default)` replaces the four `try/except AttributeError` blocks of `cmd_clean` (`folder_name`, `force_change`, `updated`,
  `old_updated`; D1 of the handover). The other 43 places are not changed yet. The unused local `changed_item` is gone.
- Tests: `tests/test_clean_orphaning.py` (15 tests). 17 mutations of the new code were all caught.

## 0.5.74 - 17.11.2026 - A login over an encrypted token file asks for the password twice; a timing test that does not depend on the computer

- **DIFFERENCE: when the token is saved over an existing encrypted file and no password was typed earlier in the run (in practice: a login while
  `gog-token.json` is encrypted), the password is now asked for twice, like any new password.** Before it was asked once and not checked, so a typo
  silently set a password that nobody knew. The old file is replaced by the login, not opened, so there is nothing to check the password against; the
  password may be the old one or a new one. A mismatch is asked again (up to 3 times at a terminal, see 0.5.72). After a read (an update, a refresh)
  the password is known and nothing is asked, as before. This is the decision of 0.5.73, option A.
- **Test fixed: `test_a_large_library_is_not_slow`** failed on the maintainer's Windows computer (15.04 seconds against a limit of 15; about 1.5 seconds
  on the sandbox computer, so the computer was busy or slow, not the search). A limit in seconds can never be right for every computer. The test now
  compares CPU time (not wall-clock time) for 500 and for 3000 games, best of three: 6 times the games must take less than 18 times as long (about 6
  times is expected, a search that compares every game with every other would need about 36). A deliberately quadratic search fails it.
- Other tests that measure seconds (`test_download_loop.py`, `test_review_fixes.py`, `test_wishlist.py`) check that a timeout or a retry does not
  hang or repeat (limits of 4 and 5 seconds around waits of about a second); they were not changed. If one of them fails on a slow computer, tell me.
- Tests: `test_token_fallback.py` (the "keeps its one prompt" test became "asks twice"), 5 more in `test_token_password_create.py`.

## 0.5.73 - 17.11.2026 - Token file review: damaged files, limits, stronger keys

- **DIFFERENCE: a damaged or unusable token file ends the run with one clear message, not a traceback.** A new `TokenFileError` (a `ValueError`, as
  these errors always were) covers: a file that is not JSON or not a token file, a wrong format, version, encryption mode or key derivation, a
  missing, not base64 or wrongly sized `salt`, `nonce` or `ciphertext`, key derivation values that are missing or not whole numbers, and a decrypted
  content that is not a token. The message names the file, and the end of the run says `Delete gog-token.json and run the login command again, or
  restore a copy of it.` All of this is checked **before** a password is asked for. A wrong password is still a `TokenPasswordError` with its own message.
  Before, most of these ended with a raw `KeyError`, `binascii.Error`, `TypeError` or `JSONDecodeError` traceback.
- **A token file cannot ask for unlimited memory or time.** The key derivation values read from a file must be: `kdf_n` a power of two from 2**14 to
  2**20, `kdf_r` from 8 to 32, `kdf_p` from 1 to 16, and 128 * N * r at most 256 MiB (so with r = 8 the largest N is 2**18). Files this program wrote
  (2**14, 8, 1) are far inside. The values are not authenticated by the encryption (its associated data is only the format name): a changed value can make
  a file fail to open, never open with a different password; this is not changed, so as not to break existing files.
- **A stronger key derivation can now be saved.** `hashlib.scrypt` was called with Python's default memory limit (32 MiB), which refuses N = 2**15
  with r = 8: raising `_TOKEN_SCRYPT_N` would have made every save fail. The limit is now 257 MiB, in step with the limit for reading. `_token_key`
  also takes its default values when it is called, not when it is defined, and the writer uses one set of values for the key and for the file.
  Nothing changes for the default values.
- **A plain save over an encrypted file is said aloud.** With `token_mode = plain` (or `GOGREPO_TOKEN_MODE=plain`) the next save of the token, also after
  a refresh, replaces an encrypted file by readable text. It always did; now one warning says `... was encrypted and is now saved as readable plain
  text, because the token mode is plain ...`. **Correction of 0.5.70:** its entry and the README said that an existing token file "is not converted"
  and that an encrypted one is not replaced by a plain one unless you log in again. That was wrong; the README is corrected.
- `import base64` is a normal import (it was `__import__('base64')` in three places).
- Looked at and left as it is: the temporary file of a save is created in the same folder and replaced atomically (0600 on Linux and macOS; the
  permission bits mean nothing on Windows, where the folder's own access rights apply); the password is asked once per process and cached.
- **Not changed, decision for the maintainer:** when the token is saved over an existing encrypted file and no password was typed in this run (in
  practice: a login while `gog-token.json` is encrypted) the password is asked once and is not checked against the old file, so a typo silently sets a
  new password. The test `test_an_existing_encrypted_file_keeps_its_one_prompt` records that design. Options: ask twice (the old file is replaced
  anyway), or check the typed password against the old file.
- Tests: `tests/test_token_file_validation.py` (16 tests, among them the real `__main__` block with a `TokenFileError`). One test in
  `tests/test_update_legacy_changelog_and_tokens.py` now expects `TokenFileError` instead of `JSONDecodeError` for a broken file. Nineteen mutations:
  seventeen were caught (two only after a test was added); two are equivalent (the defaults of `_token_key` are always overridden by the writer).

## 0.5.72 - 17.11.2026 - A new token password is asked for again; jitter in the retry waits

- **A new token password that does not match is asked for again.** When a token file is created or encrypted (a first login, `token_mode =
  encrypted` with a plain file, as in the real log where it happened in the middle of a token refresh), the password is typed twice. If the two do
  not match, or nothing was typed, the program now says `The two passwords do not match. Please try again (1 of 3).` (or `The password must not be
  empty. ...`) and asks again, up to 3 times (`TOKEN_PASSWORD_ATTEMPTS`, the same number as for a wrong password when a file is opened). Before, the
  first mismatch ended the run with a traceback (`ValueError: Token passwords do not match`). After the third failure the error is raised as
  before and nothing is remembered.
- Without a terminal (a scheduled task, a pipe) there is still one attempt and the old errors, as for a wrong password.
- **DIFFERENCE: jitter in the waits before a retry.** Every wait varies at random by up to 20 percent in both directions (`RETRY_JITTER = 0.2`):
  with `http_retry_delay = 5` a wait is anything from 4 to 6 seconds. It applies to `request()`, `request_head()`, the token refresh and both
  download loops (the chunk-verifying and the plain one), so threads that failed together do not all try again at the same moment. A `Retry-After`
  of the server is never shortened: the wait is the longer of the jittered delay and `Retry-After`, as before. The retry messages name the wait that
  is really made, rounded to one decimal (`will retry in 4.7s`; the download messages showed whole seconds). The number is a constant, not a setting
  (a setting would be easy to add); the explanation of `http_retry_delay` in the config file mentions it.
- Not done (decisions for the maintainer): growing waits (backoff).
- Tests: `tests/test_token_password_create.py` (9 tests, one of them saves a refreshed token over a plain file with a mismatch first),
  `tests/test_retry_jitter.py` (13 tests), two more in `tests/test_chunk_retry.py`. `tests/_bootstrap.py` switches the jitter off for all other
  tests, which expect exact waits. Seventeen mutations were all caught (three only after a test was added).

## 0.5.71 - 17.11.2026 - A network problem ends the run with a friendly message

- **DIFFERENCE: a run that a network problem stops no longer ends with a page of traceback.** It ends (exit status 1, as before) with one line, for
  example `Network problem: could not connect to auth.gog.com. Please check your internet connection and try again later.`, and a hint:
  `Run the command again with -debug to see the technical details.` Before, the end of such a run was the `fatal...` entry with a traceback of about
  70 lines (seen in a real log, with the network switched off during a token refresh).
- It covers an error that reaches the top of the program from a request after the retries are used up: no connection (also a failed name lookup), no
  answer in time, an answer that was cut off, and GOG answering 408, 429 or a 5xx (`GOG is busy or not working right now (error 503 from api.gog.com).
  Please try again later.`). The host is named when it is known and the text never holds the rest of the address, so it holds no token. Every other
  error (a 404, a bug) is logged as before, with its traceback.
- With `-debug` the traceback is logged as well, after the friendly line.
- The line before it, when a token refresh gives up, is shorter: `Could not renew the token: GOG could not be reached or did not answer properly.
  The login itself is not affected.` (it repeated the whole error text, which is in the traceback anyway). A refresh that GOG refuses still says
  "Please login again".
- Not changed: errors inside download threads (a file that fails is listed in the summary as before).
- Tests: `tests/test_network_message.py` (12 tests, among them the real `__main__` block of the script with `main()` failing). Eight mutations were all caught.

## 0.5.70 - 17.11.2026 - token_mode is a setting of the config file

- **New setting `token_mode` in `[settings]` of `gogrepo_delta.cfg`: `encrypted` (the default) or `plain`.** It chooses how `gog-token.json` is
  written, as the environment variable `GOGREPO_TOKEN_MODE` did before. The word is not case sensitive; an empty value means the default; any other
  word stops the program at start with the usual message (`[settings] token_mode = plan: 'plan' is not one of: encrypted, plain`). A new config file
  contains the line (`token_mode = encrypted`) with an explanation. An existing config file is not changed; without the line the default applies.
- **The environment variable still works and wins** when it is set (also when it is set to a different word than the file). A wrong value in it is
  refused as before, also when it is empty.
- **Kept on purpose: only the environment variable makes encryption mandatory.** `GOGREPO_TOKEN_MODE=encrypted` without the `cryptography` package stops
  with a message (as before). `token_mode = encrypted` in the file is the default and keeps the old fallback: the token is saved as readable text
  with one warning per run (never over an existing encrypted or unreadable file). Reason: the generated config file contains the line, so a "mandatory"
  reading would change what happens for everybody who has no `cryptography` package. `token_mode = plain` needs no package and gives no warning.
- Only the writing is affected: an existing token file is read as it is, whatever the setting says, and is not converted.
- The warning and the "install the package" message now also name the setting (`token_mode = plain`) as a way out.
- Tests: `tests/test_token_mode_setting.py` (14 tests). Nine mutations (default, precedence, validation, case, generated text, messages) were all caught.

## 0.5.69 - 17.11.2026 - Tokens and secrets are hidden in the log

- **DIFFERENCE: the values of tokens, secrets, codes and passwords are replaced by `***` in everything that is logged**, on the console and in
  `gogrepo.log`. A failed request is logged with its full address (`400 Client Error: Bad Request for url: ...`), and for the token server that
  address holds the `refresh_token` and the `client_secret` in its query string; the login request holds the one-time `code`. Hidden are the values of
  `client_secret`, `refresh_token`, `access_token`, `token`, `code` and `password` in an address (`name=value`) or in a printed dictionary or JSON
  (`'refresh_token': '...'`), and the value after `Bearer`. The rest of the message stays, so the status code and the address are still readable:
  `... token?client_id=...&client_secret=***&grant_type=refresh_token&refresh_token=***`.
- It works as a `logging.Filter` (`SecretFilter`) on both handlers, so it covers every message and also the traceback that `log_exception` writes
  (a traceback repeats the error text). It never drops a record, and a record without secrets is left as it was.
- **Not changed: entries written by earlier versions.** `gogrepo.log` (and its numbered backups) may already hold refresh tokens from failed refreshes.
  Delete or move them before sharing a log. Text that does not look like `name=value`, `name: 'value'` or `Bearer value` is not recognised.
- Tests: 10 more in `tests/test_request_retry.py` (the patterns, both handlers, and two end-to-end tests that run a failing refresh and a failing request
  against a local server and read what the console handler and the real log file handler wrote). Nine mutations (each filter or pattern removed) were all caught.

## 0.5.68 - 17.11.2026 - One retry loop; a failed token refresh no longer looks like a lost login

- **DIFFERENCE: a token refresh that fails for a temporary reason is no longer reported as "Please login again".** Before, *any* failure of the
  refresh (the network down, a timeout, GOG answering 500 or 503) was tried again and then ended the run with `AuthExpired`, the message that tells
  the user to log in again, although the login was fine. Now a refresh fails as "temporary" if the network or the connection failed, it timed out,
  the answer was cut off, or GOG answered 408, 429 or a 5xx: it is tried again `http_retry_count` times and then raised like the error of any other
  request (the run ends with the usual "fatal" log entry, exit status 1; the token file is untouched). Everything else still means "log in again" and
  still raises `AuthExpired` at once, without retries: GOG refusing the refresh token (400, 401, 403, any other 4xx), an answer that is not a JSON
  object, a token without a refresh token. **Not checked against live GOG:** which status GOG really sends for a refused refresh token; 400 and 401
  are the usual ones for an OAuth server, and every other 4xx is treated the same way as before.
- **One retry loop for `request()` and `request_head()`** (`_send_with_retries`). The two functions were near copies that called themselves once per
  retry. Same rules as before (`http_no_retry_codes` and `no_retry_statuses` are raised at once, `quiet_statuses` get no warning, everything else is
  retried `retries` times after `http_retry_delay`), same signatures and defaults. `request_head()` now handles the same cases; it had no
  `no_retry_statuses` or `quiet_statuses` arguments and still has none, since nothing needs them.
- **DIFFERENCE: `Retry-After` is honoured.** If GOG answers with a `Retry-After` header (seconds or an HTTP date), the wait before the next try is that
  long if it is longer than `http_retry_delay`, but never more than 300 seconds (`RETRY_AFTER_MAX`); a shorter, missing, past or unreadable value
  changes nothing. Applies to `request()`, `request_head()` and the token refresh.
- **DIFFERENCE: a response cut off while its body is read (`ChunkedEncodingError`) is retried** like the other connection errors; before, it ended the call at once.
- **The retry messages show a decimal delay as it is** (`will retry in 2.5s`; `%d` showed 2s).
- `renew_token()` is a loop instead of a call to itself. It still holds `token_lock` while it waits for a retry, on purpose: all threads need the new
  token, and this way only one of them asks GOG. A session without a token, and a token that is still valid for 5 minutes, are left alone as before.
- Not done (decisions for the maintainer): growing waits (backoff) and a random part (jitter) between retries; they need a new setting.
- Tests: `tests/test_request_retry.py` (37 tests; fake sessions with real `requests.Response` objects, plus four over a real local HTTP server). Two
  tests in `tests/test_review_fixes.py` that expected `AuthExpired` for a refresh timeout now expect the timeout. Ten mutations of the new code
  (each of the rules above removed or reversed) were all caught.

## 0.5.67 - 15.11.2026 - Clearer download messages; dead code removed

- **Wording: the messages name games and movies.** A real movie download printed `downloading games with id(s): {the_gamers_directors_cut}`. Now `downloading id(s)/title(s): {...}` and `skipping id(s)/title(s): {...}`; the three messages of `update` that said `game id(s)` say `id(s)`; and the errors when nothing is left to download say `no game or movie ...`. Two typos of those errors are gone: `no game was found was found after skipping ...` (said twice) and `... was found` + `after skipping ...` that ran together as `foundafter`.
- **Progress lines say what their numbers are.** The line used to read `   1072.3MB      1.1MB/s  1x  the_gamers_directors_cut-movie/the.gamers.directors.cut.(2002).720p.mp4` followed by `1.10GB remaining`, and `1x` (the number of parallel connections of that file at that moment) had to be looked up in the code. Now `   1072.3MB left     1.1MB/s   1 connection   <folder>/<file>`, `2 connections` for two, the file names stay lined up, and the sum is `1.10GB remaining in total`. How often the lines are printed (about once a second per file, some 350 lines for a three-minute movie) is unchanged; `_report_progress` had no test, now it has.
- **Dead code removed** (nothing used it; each was judged not worth reviving). `update_self()` (44 lines; it only wrote test files such as `updatetest.test` and fetched the unverified `master` tarball, and `selfupdate` replaced the idea), `save_config_file()`, `load_config_file()` and `CONFIG_FILENAME` (the legacy `gog-config.dat`, which nothing has read or written since the config moved to `gogrepo_delta.cfg`), `input_timeout()` with the `signal` import (POSIX-only), `MANIFEST_SYNTAX_VERSION` (the resume manifest has its own, `RESUME_MANIFEST_SYNTAX_VERSION`, which stays) and `purge_md5_chunkdata()` (`save_manifest` can drop the md5 data). 82 lines fewer, and the known issue about `update_self` is gone from the list above. The README says that `gog-config.dat` is a leftover of older versions that you can delete.
- **Kept on purpose:** `HTTP_FETCH_DELAY` (a polite delay between requests may be added), the two unused wake-lock classes `DBusSessionInhibitor` and `GnomeSessionInhibitor` (part of the idea to keep a Linux machine awake without PyQt5), `__author__`, and everything that only looks like removed code (`USER_CONFIG_FILENAME`, `REPO_HOME_URL`, `NEW_RELEASE_URL`, `GOG_MEDIA_TYPE_MOVIE`, which movies use now). A test lists what was removed and what looks similar but stays.
- **0.5.63 note corrected:** the open points about movies on live GOG are answered by the log of a real download (see that entry).
- `tests/test_messages.py`: 15 tests (the progress lines, the messages and errors of the id selection, the removed code); 10 mutations of the new wording were checked and all caught. Two tests of removed code are gone (`test_config_roundtrip` and `test_update_self_is_still_not_connected_to_any_command`), the test of the data file names no longer lists `gog-config.dat`, and two tests of `tests/test_download.py` look for the new error text.

DIFFERENCE: some log and error messages are worded differently (see above), the progress lines have a new form, and 82 lines of unused code are gone. Nothing else changes.

## 0.5.66 - 15.11.2026 - Image downloads replace artwork safely

- **The problem.** A cover or background image could be deleted or moved before its replacement was requested. If the request or file write failed, the previously usable image was already gone. Background-key cleanup could also remove old folders after only some of the current images had downloaded, or when the manifest did not say whether the key list was complete.
- **Now each image is installed atomically.** The response is written to a temporary file in the destination directory, checked for non-empty content, flushed, and installed with `os.replace`. The previous image remains in place if the request or write fails. Old files are cleaned or moved to `!orphaned` only after the replacement is installed.
- **Background cleanup requires complete metadata.** A successful game-details fetch marks `bg_urls_complete`. Old background keys are pruned only when that marker is present and every current image was successfully obtained. Older manifests without the marker retain unrecognized background folders. If one current image fails, no stale-key cleanup is performed for that refresh.
- **The image paths are checked.** Path traversal and unsafe path components in image metadata are rejected so an image cannot be written outside the game's `!images` directory. Symlinked directories are not traversed during old-image cleanup.
- `tests/test_image_handling.py`: failed requests and empty responses preserve old images, successful atomic replacement, orphaning only after success, incomplete metadata retention, failed-refresh retention, stale-key cleanup after a complete successful refresh, and path traversal rejection.

DIFFERENCE: image replacement is now transactional and conservative background cleanup requires an explicit completeness marker. Existing image directory layout and `-nocleanimages` semantics are retained.

## 0.5.65 - 15.11.2026 - Game-directory rename cycles are staged safely

- **The problem.** A game folder can need a new name when GOG changes the game's title or the folder name recorded in its metadata. Renames were handled one game at a time. If two games exchanged folder names (or formed a longer cycle), the first destination was still occupied by another game's source folder and could be moved to `!orphaned`.
- **Now directory renames are staged as a group.** Every unambiguous source folder is first moved into a temporary directory under the library root. Only after all sources have been staged are destinations installed. This supports two-folder swaps and longer cycles without treating another game's source as an unrelated clash.
- **Safety.** A genuine destination clash is still preserved under `!orphaned`. Duplicate source or destination mappings and path-like folder names are skipped as ambiguous or unsafe. If staging or committing fails, the operation attempts to restore the original folders and leaves `old_folder_name` pending for a later retry. Dry runs only report the planned changes and create no staging or orphan directories.
- `tests/test_game_renames.py`: two- and three-folder cycles, genuine destination clashes, staging and commit failures with rollback, dry runs and ambiguous duplicate destinations.

DIFFERENCE: game-directory renames are now staged together, just like file rename cycles. Ordinary single-folder renames and the handling of genuine destination clashes remain unchanged.

## 0.5.64 - 14.11.2026 - `export` checks that the CSV file can be written

- **The problem.** With `gog-library.csv` open in Excel, `export` ended with `PermissionError: [Errno 13] Permission denied: 'gog-library.csv'` and a traceback. The check for a locked file that `wishlist --csv` already had (`file_write_problem` and `file_write_message`) was never used by `export`.
- **Now `export` does the same.** Before it reads the manifest it checks that the file can be written. If not, one error says `cannot write gog-library.csv (Permission denied). If the file is open in another program, for example Excel, please close it and run the command again.`, the run ends with exit status 1 (`FAILED: 1` in the summary), and nothing is changed: an existing file keeps its content, a file that did not exist is not created. A folder that does not exist or a name that is a folder are reported the same way.
- **The check is not enough alone**, and a drive on which a file locked by Excel looks writable to a check (the log came from WSL on a Windows drive) would slip through. So the opening of the file for writing is guarded as well: if it fails after the check has passed, the same message and exit status come, again without a traceback and without a partly written file.
- `tests/test_export_lock.py`: 10 tests (refused before the manifest is read, the old file untouched, no file created, a folder in the place of the file, a missing folder, the check passing and the opening failing, through `main` with no traceback, and the normal paths unchanged). `tests/test_movies.py`: one test that deleted its own working folder (Windows refuses that) is now two tests.

DIFFERENCE: `export` ends with an error message and exit status 1, instead of a traceback, when the CSV file cannot be written. Nothing else changes.

## 0.5.63 - 14.11.2026 - Movies: `update --movies` puts GOG's movies into the manifest (opt-in)

- **What it is.** `update --movies` (or `movies = true` in `[update]` of the config file) also asks GOG for the movies of your library (`getFilteredProducts` with media type 2) and for each movie's details (`/account/movieDetails/<id>.json`), and puts them into the manifest as items with `media_type` `'2'`. From then on `download`, `verify`, `backup`, `clean` and `import` handle them like any other item. Off by default: one movie can be many gigabytes (a 4K concert is 19 GB).
- **The data it is built on.** Three real answers of GOG's account API are kept as fixtures in `tests/data/movies` (the movie list and the details of two movies). They show that a movie's `downloads` is not a game's `[[language, {os: [files]}]]` but a flat list of `{manualUrl, playerUrl, name, size}` with no version, date, OS or language field. The language is the first part of the address (`/downloads/<slug>/en1video1`), the kind (`video`, `patch` for the subtitles) the second, and the quality is in the name in parentheses (`... (1080p)`). Before this version every movie would have failed at `dict(item_json_data['downloads'])`.
- **Video variants: `--moviequality`.** A movie offers several qualities (720p, dvd, 1080p, 4K; others have 576p, 480p, 396p). The value is `best` (default, the highest resolution; a tie goes to the bigger file), `all`, one quality (`1080p`), `max:<quality>` (the best that is not above it) or a list in order of preference (`1080p,720p`). If none of the listed qualities is offered the best one is taken and the log says so, so a movie never ends up without its video. `dvd` ranks as 576 and `4k` as 2160; a label that is not known ranks lowest and can still be asked for by name. The subtitles (`patch` files) are always taken; the extras (posters, ...) are filtered like those of a game. A wrong value is refused by the command line with the reason.
- **Language.** The wanted languages if the movie has them; else English (log line); else whatever language it has. (No movie with a language other than English has been seen.)
- **No operating system.** The files of a movie have the `os_type` `video` and belong to every OS selection: `--os` neither takes nor drops them (new `os_selected()` in the ten places that filtered by `os_type`, `filter_languages` and the "narrowing" warning of `update`). `--installers galaxy` does not empty a movie.
- **Folder.** `<slug>-movie` (`MOVIE_FOLDER_SUFFIX`), so movies are recognised in the library folder; the file names come from the resolved address as for games (`deliverance_making_of_kingdom_come_1080p.mp4`). The name on GOG's server differs from the product slug, which is why nothing is derived from the slug.
- **An update without `--movies` leaves the movies of the manifest alone.** A full `update` removes manifest items that are not in the library it fetched; without this rule one update without `--movies` would have dropped every movie from the manifest and `clean` would then have moved their folders to `!orphaned`. The log says how many movies were left. With `--movies` a movie that is gone from your library is removed like a game. With `--ids`, movies are asked for only if an id was not found among the games (a movie can be named by its slug).
- **Resume.** `movies` and `moviequality` are saved with the resume information and used when an interrupted update is resumed; a resume file from an older version means no movies.
- **`list` and `export`.** A `MEDIA` column in `list` and a `media` column in `export` (after the title) say `game` or `movie`; `list` shows the OS of movie files as `vid`. In the CSV every column after `title` moved one place to the right.
- **Checked against live GOG on 14.11.2026** with a real download of one movie ("The Gamers: Director's Cut": a 720p video of 1.1 GB, the subtitles and three extras, 1.10 GB in all, no failures): the address `/downloads/<slug>/en1video1` redirects to the CDN like an installer link; the CDN honours the range requests of the downloader (it checks that every chunk comes back with the `Content-Range` it asked for); the token refresh in the middle of the run worked; the files went through `!provisional` into `<slug>-movie`; and `-ids` found the movie by its slug without the suffix. Not seen: an MD5 for a video (`.mp4` and `.zip` are on the list of files without an md5 XML, so movies are verified by size, like extras) and the choice among several video variants on real data (this movie offers only one).
- **README:** a `Movies` section; `pyobjc-framework-Cocoa` is listed as optional again (the program starts without it; the macOS binaries contain it; the build stopped because of a wrong package name once, which is why it looked required).
- `tests/test_movies.py`: 55 tests on the real fixtures (the quality rules, the language choice, every file of a movie, the manifest and its folders, updates with and without `--movies`, removal, resume, the narrowing warning, the columns, the command line); 17 mutations of the new logic were checked and all caught. `test_ids`, `test_manifest_format` and `test_export_update_time` read the new columns.

DIFFERENCE: a new opt-in (`update --movies`, `--moviequality`); `list` has a `MEDIA` column and the CSV of `export` a `media` column after `title`. Without `--movies` nothing is fetched or changed, and the movies of a manifest are left alone.

## 0.5.62 - 13.11.2026 - Rename state is saved; circular file renames are staged safely

- **A successful rename is now committed to the manifest immediately.** `handle_game_renames()` reports whether it changed rename state, and `download`, `verify` and `clean` save the manifest when needed. `download` saves the complete manifest, not only the selected games. This prevents a successful on-disk rename from being forgotten and attempted again on the next run.
- **File rename cycles are handled as a group.** Pending source files are first moved into a temporary staging directory, then placed at their destinations. This safely handles swaps such as `A -> B` and `B -> A` without orphaning one of the cycle's source files as a false destination clash. Ambiguous duplicate paths are skipped rather than guessed.
- **An already-correct destination is recognized by both size and MD5.** When both match the manifest, the stale `old_name` marker is cleared without replacing the valid destination. Missing size or MD5 is never treated as a match.
- **Failed renames remain retryable.** `old_name` / `old_folder_name` are cleared only after success (or after a destination has been positively verified); failed file renames invalidate `prev_verified` and cause that state to be saved. A dry run no longer creates `!orphaned` or a temporary staging directory.
- `tests/test_game_renames.py`: 10 regression tests for ordinary and folder renames, already-correct destinations, two-file circular renames, failed staging, dry runs, and saving the complete manifest.

DIFFERENCE: rename handling is safer and persists its state. Circular file renames are staged before destination changes; ambiguous duplicate source/destination mappings are left pending. Directory rename cycles are not specially staged and remain subject to the existing destination-orphaning behavior.

## 0.5.61 - 13.11.2026 - Cleanup keeps files when manifest metadata is incomplete

- **`clean` no longer orphans unrecognized files from a game folder if any download, Galaxy download, shared download, or released extra has no filename.** A missing filename can mean that GOG file metadata could not be fetched; it is not proof that a local installer or extra is obsolete. The known filenames are still recognised, and normal orphaning still happens when all filenames are known.
- **The `!downloading` cleanup follows the same rule.** It leaves unrecognized files in the affected game's work folder when any downloadable manifest item has an unknown filename, rather than deleting a partial download that may belong to that item. With complete filenames, obsolete work files are still removed as before.
- **MD5 XML cleanup now protects incomplete OS and language metadata as well as unknown filenames.** If any download has no OS, the existing OS directories and their contents are retained. If an entry for a known OS has no language, that OS's existing language directories and contents are retained. The XML writer skips entries without an OS or language because it has no safe destination for their XML; existing cached data is left alone.
- `tests/test_cleanup_incomplete_metadata.py`: 7 regression tests (unknown names in `clean` and `!downloading`, plus normal cleanup when metadata is complete). `tests/test_md5_cleanup.py`: 3 new tests for unknown OS/language metadata and a successful manifest save.

DIFFERENCE: cleanup is deliberately less aggressive when metadata is incomplete. Some genuinely obsolete files may remain until a later update provides complete filenames, OS and language information; this is preferable to moving or deleting valid user data based on missing metadata.

## 0.5.60 - 11.11.2026 - CSV export: update date and update time (UTC) in two columns; clearer text for refused prices

- **`export`: the `updated` column is now two columns, `update date` and `update time (UTC)`.** One cell with `2026-06-23T18:59:00+02:00` is text to a spreadsheet; two cells with `2026-06-23` and `16:59:00` are a date and a time that Excel and the like show in the format of the user's language. The stamp is converted to UTC (an offset moves the time and, over midnight, the date: `00:30+05:30` becomes the previous day, `19:00:00`); a stamp without a zone is taken as UTC, which is how the program stores GOG's stamps; something that is not a stamp (a year, an old value) goes into the date column unchanged with an empty time, and a file without a stamp gets two empty cells. The `on disk` column from `--savedir` is still the last one, so every column after `md5` moved one place to the right.
- **`wishlist --prices`: the text of a refused price is GOG's message.** The warning showed the raw JSON of the answer cut off after 120 characters (`{"_links":{"self":{"href":"\/api\/products\/1293804420\/prices?countryCode=DE"}},"message":"Product 1293804420 not fo...`). It now quotes the `message` of that JSON: `GOG refused the price request for Shadow of the Road: "Product 1293804420 not found"; its price is not known`. An answer that is not JSON, or has no message, is shown as before.
- **What that message says:** GOG does not know a price for those products in that country (for example a game that is no longer on sale or not released); this is a fact about the product, not a rate limit, so a delay between the requests would not change it. The fix of 0.5.58 (a refused game does not stop the others) is what keeps the run going.
- `tests/test_export_update_time.py`: 14 tests (offsets and midnight, the stamp forms, missing values, the columns and their order in the file, the readable price text). One test of `tests/test_manifest_format.py` reads the `on disk` column one place further right; one of `tests/test_wishlist.py` checks the quotes around GOG's message.

DIFFERENCE: the CSV of `export` has one more column (`update date` and `update time (UTC)` instead of `updated`); the warning for a refused price quotes GOG's message.

## 0.5.59 - 11.11.2026 - `clean -trash` lists what is inside a folder before it deletes it

- **The remark that led to this.** `-trash -all` listed only the top-level items with a file count and size, and `-folders` printed just `Deleting <folder>` although the whole folder went. A list that does not show what disappears is not much of a safeguard.
- **Now every folder is followed by its contents.** A file with its size, a subfolder as `name\ (N files, size)`, an empty folder as `(empty)`, a link as a link (never followed). It applies to the list that comes before the question of `-trash -all`, to the `Deleting <folder>` line of `-folders` and to the one of `-images`. The contents are read before the deletion and printed only if the folder was really deleted (a folder that could not be deleted is reported as a failure and not listed).
- **How much is shown.** In a **dry run** everything: every top-level item and every file below each folder with its path inside the folder (long output is the point of a dry run; redirect it to a file). Otherwise the list is capped: 20 entries per folder and 200 lines of contents in all, and what is left out is counted (`... and 5 more items (-dryrun lists everything)`, or `(N items not listed: the limit of 200 lines was reached ...)` when the limit for the whole run was used up); the list of top-level items stays at 20 and says `... and N more items`. All of this comes before the question, so the answer is given with the list in front of you.
- Not changed: the lines for single duplicate files (`Deleting <file>`), and `-partials` and `-provisional`, which still print one `Deleting` line per folder or item.
- `tests/test_trash_listing.py`: 22 tests (the helper with its two modes and limits, the order before the question, a dry run that lists all, `-folders`, `-images`, a failed deletion, links). One test of `tests/test_clean_report.py` changed: a dry run now lists all 25 top-level items instead of 20 (asking still lists 20).

DIFFERENCE: `clean -trash` prints the contents of the folders it is about to delete, and a dry run of `-trash -all` lists every top-level item (it used to stop at 20). Nothing is deleted differently.

## 0.5.58 - 11.11.2026 - `wishlist --prices`: one refused game no longer stops the prices of all the others

- **The problem.** The prices of the first 15 games came, then the run printed `GOG does not accept 'DE' as a country for the prices` and fetched no more. The program took every HTTP 400 from the price request for "GOG does not know this country" and switched the prices off for all remaining games. But GOG also answers 400 for single products (not for sale, not released, no price for the country), so one such game, here the 16th, made the program blame a perfectly good country code.
- **The fix.** A 400 for one game is now that game's problem: a warning names the game and quotes GOG's answer (control characters removed, at most 120 characters), the price that was known before is kept (so no change is reported by mistake), and the run goes on; the count `prices refused by GOG` appears in the summary and the run still ends with status 0. The country is blamed, as before, only when GOG has refused the first three price requests and has not answered any (a price or "no price" counts as an answer, because then the country is known to be accepted). If a wishlist has fewer than three games and GOG refuses every one, there is a warning that names `-country`, and the run ends with status 1 (`refused for every game`).
- **Not known:** why GOG refuses those games. The warning now carries GOG's own words, so the next report can say. If the refusals turn out to come in a burst after a number of quick requests, a polite delay between price requests (the unused `HTTP_FETCH_DELAY` of the old code was meant for that) would be the next step.
- `tests/test_wishlist.py`: the fake GOG can refuse single products; 8 new tests (among them 20 games with the 16th and the 18th refused: 18 prices saved and no country blame; the 404 that counts as an answer; the known price kept; the sanitised text); the country test now expects three refusals instead of one. Nine mutations of the new logic were checked and all caught.

DIFFERENCE: `wishlist --prices` no longer stops at the first HTTP 400 of GOG; a wrong country is recognised after three refusals in a row at the start (it used to be one), and a refused single game is a warning, not a failure.

## 0.5.57 - 11.11.2026 - Token storage without the `cryptography` package falls back to plain text, with a warning

- **The decision from 0.5.37 is implemented.** Until now, saving a token without the `cryptography` package ended with a `RuntimeError` and a traceback. Now the token is saved as readable JSON (`"encryption": "plain"`, file permissions as before) and one warning per run says that it is **not encrypted** and which command installs the package (`python -m pip install cryptography`). No password is asked in that case.
- **When it does not fall back.** The fallback applies only where it cannot destroy anything and nobody asked for encryption:
  - an existing encrypted `gog-token.json` is never replaced by a plain-text file: the run stops with a message that says to install the package, and the file is untouched;
  - the same for an existing token file that cannot be read (damaged, not JSON, other format or version): it is not replaced, and the message also says that deleting it and logging in again is the other way out;
  - `GOGREPO_TOKEN_MODE=encrypted` set on purpose never falls back: it stops and names `GOGREPO_TOKEN_MODE=plain` as the explicit alternative. `GOGREPO_TOKEN_MODE=plain` is unchanged and needs no warning.
- **Reading an encrypted token without the package** now says `gog-token.json is encrypted, but the "cryptography" package that opens it is not installed. Install it with: ...` and exits with status 1 without a traceback (new `TokenModuleMissing`, a subclass of `RuntimeError` as the old error was; the top level prints its message). A plain-text token is read without the package. The legacy `gog-token.dat` is migrated to a plain-text `gog-token.json` in the same way (and the `.dat` file is left alone as always).
- **Encrypting a plain-text token file asks for a new password twice.** This is the way back after the fallback (install the package, run again) and it also applies to anyone who had a plain-text file and no `GOGREPO_TOKEN_MODE`. Before, the program asked once, as if the file already had a password, so a typo became the password of the new encrypted file without a confirmation. An existing encrypted file still asks its one password.
- **README:** a new paragraph says that the binaries are for people who do not want to install Python and the dependencies (one file per platform that contains Python and all packages, not code-signed, check the download first). `cryptography` moved from the required to the optional dependencies, marked as strongly recommended; the token notice, the login text and the file table describe the fallback.
- `tests/test_token_fallback.py`: 23 tests, among them every case above, the file permissions, one warning per run, the real import failure, the confirmation of a new password, and the top level started as a program without the package (message, exit status 1, no traceback, token file untouched).

DIFFERENCE: without the `cryptography` package the program saves the token as plain text and warns, where it used to stop with a traceback; it stops with a message (and changes nothing) if an encrypted or unreadable token file exists or if encryption was requested with `GOGREPO_TOKEN_MODE=encrypted`. Encrypting a plain-text token file now asks for the new password twice.

## 0.5.56 - 10.11.2026 - `clean` reports what it did; `-trash -all` empties `!orphaned`, with a question

- **Every stage now says what it looked at**, so a run that deleted nothing no longer looks like a run that did not work. Before, `-partials` and `-trash` printed only their heading when nothing matched, and the log of such a run could not be told from a broken one.
  - `-partials`: how many unfinished download folders it deleted (or "would be deleted" in a dry run), or that `!downloading` has no game folders; loose files directly in `!downloading` are named as not touched, because an unfinished download is always a game folder.
  - `-provisional`: how many items it deleted, or that nothing is waiting.
  - `-trash` (strict): how many folders of `!orphaned` it looked at and how many duplicates it deleted, and what it kept and why: files without a file of that name in the game folder, files whose size or content differs, folders without a game folder of that name (the first five are named), subfolders inside the folders and loose files directly in `!orphaned` (neither is looked at). If anything was kept it points to `clean -trash -all`. An empty `!orphaned` is named as such.
- **`-trash -all` deletes everything in `!orphaned`**, loose files, folders and subfolders included; the folder `!orphaned` itself stays. Until now there was no way to empty it. It cannot be combined with `-installers`, `-images`, `-folders` or `-relaxed` (it makes them unnecessary), and `-all` needs `-trash`. The plain `-trash` stays strict and the deprecated `trash` command keeps its old meaning.
- **It shows and asks before it deletes.** It lists the number of items and files, the total size and each top-level item with its size (the first 20). At a terminal it asks `Delete all N items (size) from '!orphaned' for good? [y/N]` with the existing `ask_yes_no` (`y`, `yes`, `j`, `ja`; Enter, anything else and a closed input mean no). Without a terminal, such as a scheduled task, it refuses with an error and exit status 1 and deletes nothing, unless `-yes` is given. `-yes` skips the question, needs `-trash -all`, and is deliberately a command line switch you write on purpose: do not put it in a config file you also use by hand. `-dryrun` lists, never asks and deletes nothing. A link in `!orphaned` is removed itself, not what it points to.
- **Read-only files and folders no longer stop a deletion** (`rmtree_force`). Windows refuses to delete a file with the read-only attribute, which Git sets on its objects, so a `.git` folder in `!orphaned` could not be removed by `-folders`, `-images` or the clean-up of `!downloading`. The same helper now serves `-partials`, `-provisional`, `-trash` and `-trash -all`. A failure that is not a permission problem is still reported as before. It uses `onexc` on Python 3.12 and later and `onerror` below, because `onerror` is deprecated.
- **Smaller fixes in `-trash`.** A folder in `!orphaned` whose name is also the name of a file in the game folder (for example `!orphaned\game\manual.zip\inner.bin`) made it fail while hashing a folder; it is now counted as a subfolder that is not looked at.
- **README:** `pyobjc-framework-Cocoa` (PyObjC) is now listed as a required dependency on macOS, with its install command, instead of as an optional one. The program itself still starts without it (one warning, no sleep inhibitor), which the README says.
- `tests/test_clean_report.py`: 51 tests. Two of them (real read-only files and folders) skip themselves for the root user and on Windows they test the attribute that Git sets; they were also run as an unprivileged user here.

DIFFERENCE: `clean` has the new switches `-all` and `-yes`; the stages print report lines they did not print before; read-only files no longer stop deletions on Windows. `-trash -all` is the first deletion in the program that asks a question, and the only one that refuses to run unattended without `-yes`. Everything else is unchanged.

## 0.5.55 - 10.11.2026 - `clean` refuses to run without a manifest that lists games

- **The problem.** The manifest is read from the current working directory, and a missing manifest (with no backup either) reads as an empty one, which is the normal state of a first run. For most commands an empty manifest is harmless, but `clean` took every folder of the library for "not in the manifest" and moved all of them to `!orphaned`. Starting `clean` from another folder than usual was enough. Nothing was deleted and the folders could be moved back, but it was a mass move nobody asked for. This was the known issue listed in the previous entry.
- **The check.** When the `-orphans` stage is going to run (the default), `clean` stops if the manifest lists no games, whether the file does not exist or exists and is empty. The message names the manifest file with its full path, says that it is read from the current folder and which folder that is, says what would have happened, and gives the way out: run `clean` from the folder that holds `gog-manifest.dat`, or run `update` first. Exit status 1, nothing is changed. It applies to `-dryrun` as well, and it is looked at before every other stage of the same run and before the check for a game folder (0.5.54).
- **Not affected:** `-partials`, `-provisional` and `-trash` on their own: they read no manifest and work on `!downloading` and `!orphaned` alone. A manifest that is damaged or has a backup is handled as before (the question about the backup, or the error); this check is only for a manifest that loads and is empty.
- `tests/test_clean_manifest.py`: 10 tests, among them the mistake itself through `main` (manifest in one folder, `clean` started in another: the tree on disk is identical afterwards), a manifest that exists but lists no games, the dry run, the combination with other stages, and that `-partials` alone still runs. The stage tests and three tests of `tests/test_run_summary.py` that run `clean` without a real manifest now fake this check as well.

DIFFERENCE: `clean` stops with an error (exit status 1) when the manifest does not exist or lists no games; it used to move all game folders to `!orphaned`. Everything else is unchanged.

## 0.5.54 - 09.11.2026 - `clean` refuses the folder of a single game

- **The mistake it stops.** `clean` expects the library folder, the one that contains all the game folders. Given the folder of ONE game instead, it took the subfolders of that game (`extras`, ...) for games of their own, found none of them in the manifest and would have moved them to `!orphaned` (inside the game folder), while the files in the game folder, which the person wanted checked, were never looked at. A stray file there was reported as "nothing to clean. nice and tidy!". It also created an empty `!orphaned` folder in the game folder.
- **The check.** Before anything is done, `clean` looks at the folder it was given. A folder with at least one subfolder that is a game folder of the manifest is a library and is accepted. Otherwise it is taken for the folder of one game, and refused, if its own name is the folder name of a game of the manifest, or if it directly contains a file of the manifest (an installer or an extra) of a game. A folder that matches neither (an empty new library, for instance) is accepted as before. Names are compared the way the file system does (not case-sensitive on Windows).
- **What happens when it refuses.** One error message that names the game, says why the folder looks like that game's folder and gives the folder to use instead (the one that contains it); exit status 1; nothing is changed: no rename of game folders, no `!orphaned` folder, nothing moved. It also applies to `-dryrun`, and it is looked at before every other stage of the same run, so `clean DIR -partials -orphans` on a game folder deletes no partial downloads either.
- **Not affected:** `-partials`, `-provisional` and `-trash` on their own. They read no manifest and only touch `!downloading` and `!orphaned` of the folder given, so a game folder simply has nothing for them.
- `cmd_clean` takes an optional `items` argument (the manifest, when the caller has loaded it already); the rest of its behaviour is unchanged.
- `tests/test_clean_target.py`: 18 tests, among them the mistake itself through `main` (the tree on disk is identical afterwards) and the cases that must still work (a normal library, a library with unknown folders, a new empty one). Three tests in `tests/test_run_summary.py` and the stage tests in `tests/test_clean_stages.py` now fake the check, because they run `clean` on folders that do not exist.

DIFFERENCE: `clean` stops with an error (exit status 1) when the folder it is given looks like the folder of one game; it used to carry on and treat the game's subfolders as games. Everything else is unchanged.

## 0.5.53 - 09.11.2026 - New command `selfupdate`: is there a newer release? (it only looks)

- **`selfupdate`** (also `selfupdate -check`, the only thing it does for now) asks GitHub for the newest published release of the repository and says whether it is newer than the running version. If it is, the command names it, shows the address of its release page and says that nothing was downloaded or installed. Exit status 0 when the check worked (newer or not), 1 when it did not (no network, GitHub refused, an answer that makes no sense), so a scheduled job can tell the two apart.
- **It deliberately installs nothing.** The program holds a GOG login, so replacing it from the internet needs a way to check what arrives. That way (releases signed with a key that is not on GitHub) is not decided yet; downloading and installing stay out of the program until it is. The old `update_self()` is still not connected to anything and must not be (it would fetch the unverified `master` branch).
- **What the request is.** One plain `GET` to `api.github.com/repos/MarS301/gogrepo_delta/releases/latest` with the user agent of the program, a timeout and no login data of any kind: the GOG token, the manifest and the session of the other commands are never touched, and nothing is written to disk. Redirects are not followed, at most 1 MB of the answer is read, and a draft or pre-release is ignored.
- **What is trusted from the answer.** Only a tag that is a plain version number (`v0.5.60`). The release address is shown only if it lies on this repository's release pages (otherwise the general releases page is shown), and every text from GitHub has its control characters removed (no escape sequences on the console) and is cut to a short length. Versions are compared as numbers (0.5.10 is newer than 0.5.9).
- **Release workflow (`build.yml`, no change to the script):** every release now also gets `gogrepo_delta.py`, a `SHA256SUMS` file for all release files and a GitHub build attestation for each of them. How to check them is in the README ("Verifying a download"). Releases made before this change have none of these.
- `tests/test_selfupdate.py`: 28 tests with a faked GitHub (no network), among them that no GOG function is used, that nothing is written, that foreign addresses and escape sequences are neutralised and that every failure becomes a message and exit status 1.

DIFFERENCE: a new command `selfupdate`; the first (and only) place where the program contacts a server other than GOG, and only when this command is run. Nothing else changes.

## 0.5.52 - 09.11.2026 - `clean` takes over `trash` and `clear_partial_downloads`; three bugs in them fixed

- **One command for all clean-up.** `clean` now has stages, chosen by switches; each stage only runs when asked for, and they always run in this order:
  1. `-partials`: delete the unfinished downloads in `!downloading` (what `clear_partial_downloads` did).
  2. `-provisional`: delete the finished files waiting in `!downloading/!provisional`. This is a separate switch because these files are complete: without it the next `download` moves them into place, with it they are downloaded again.
  3. `-orphans`: move files and folders that are not in the manifest to `!orphaned` (what `clean` always did). It is the default: `clean DIR` without any stage switch does exactly this, as before.
  4. `-trash`: permanently delete from `!orphaned` (what `trash` did), refined by `-installers`, `-images`, `-folders` and `-relaxed` as before.
  `-dryrun` applies to every stage. Only the `-orphans` stage reads the manifest; `-partials`, `-provisional` and `-trash` work on the folders alone.
- **Safety rules.** `-orphans` and `-trash` cannot be used in the same run (a dry run could not show what the real run would delete, and `!orphaned` is the safety net for what `clean` just moved); the run stops with a message before anything is touched. `-installers`, `-images`, `-folders` and `-relaxed` are refused without `-trash`, so a mistyped command never does less than it seems to.
- **Old commands still work, with a notice.** `trash` and `clear_partial_downloads` print one warning ("deprecated ... use: clean -trash" / "clean -partials") and do what they did. They will be removed in a later version. The folder argument of `clean` is now called `gamedir` like in the other commands, so a `gamedir` entry of the config file now serves `clean` as well. A config file written by an older version has a `cleandir =` line in `[clean]`: it is ignored with one warning ("[clean] has no option 'cleandir' ... ignored"); move its value to `gamedir` or delete the line.
- **Bug fix: `clear_partial_downloads` never deleted anything in `!downloading/!provisional`.** The second loop looked for the folders in `!downloading` instead of `!provisional`, so they stayed, and loose files there were ignored. `-provisional` (and nothing else) now removes both folders and files, and leaves the `!provisional` folder itself.
- **Bug fix: `trash` and `clear_partial_downloads` crashed with `FileNotFoundError`** when `!orphaned` or `!downloading` did not exist (a library that never had an orphan or a partial download). They now say there is nothing to do.
- `tests/test_clean_stages.py`: 33 tests for the stages and their order, the combination rules, the two bug fixes, the old commands and the dry run. `tests/test_config.py`: `installers` is now listed in the `[clean]` section too.

DIFFERENCE: `clean` has new switches and the folder argument is called `gamedir` (a `cleandir` entry in an existing config file is ignored with a warning); `trash` and `clear_partial_downloads` print a deprecation warning; `clear_partial_downloads` no longer crashes when `!downloading` is missing and `trash` no longer crashes when `!orphaned` is missing. `clean` without switches behaves as before.

## 0.5.51 - 08.11.2026 - Safer and less redundant MD5 XML cleanup

- **Do not discard MD5 XML when GOG metadata is incomplete.** During cleanup, a download or released extra with no filename can indicate a metadata-fetch failure. Existing XML files in that affected language/download folder or extras folder are now retained instead of being treated as obsolete. Once all relevant entries have names again, normal stale-file cleanup resumes.
- **Remove redundant directory enumeration.** The download-language XML directory is now listed once (the old code listed it twice through nested loops). The language list is also built in one pass instead of repeating the same scan for each item.
- Existing named entries are still cleaned normally: stale XML is removed when the manifest has complete filename information, and expected XML files remain untouched.
- `tests/test_md5_cleanup.py`: regression coverage for preserving existing download and extra MD5 XML when names are unknown, and for normal cleanup when names are known.

DIFFERENCE: cleanup is deliberately more conservative when manifest metadata is incomplete; valid existing MD5 XML is no longer deleted on that evidence alone.

## 0.5.50 - 07.11.2026 - Failed game details remain pending in the resume manifest

- A game whose details could not be fetched or processed is no longer removed from the resume manifest. It remains pending, and `complete` stays false until every game has been processed successfully.
- A later `update` retries the pending game. The run reports how many games remain pending and tells the user to run `update` again.
- `tests/test_update_saves.py`: regression tests cover retaining a failed game, keeping the resume manifest incomplete, and retrying the game successfully on the next run.

DIFFERENCE: failed game-detail requests are retried on a later `update` instead of being silently discarded from resume state.

## 0.5.49 - 07.11.2026 - `wishlist`: the CSV always writes the release date as ISO (2026-11-05)

- **The date of the CSV is `YYYY-MM-DD` in every case.** The by-country formats of 0.5.45 are gone (`_DATE_FORMATS` and the `country` parameter of `format_release_date()` and `write_wishlist_csv()`): Excel reads a date in
  the order of the computer's language, so `11/05/2026` became 11 May on a German Excel while `06/23/2026` was left as text. `2026-11-05` is understood in every locale and then shown the local way. The day is
  the one in GOG's text (no time zone conversion); the saved JSON file keeps the original text.
- **`-country` is only for the prices** (default `US`; `UK` is taken as `GB`), as before. The extra text about the date format in the message after the CSV (0.5.48) is gone again.
- `tests/test_wishlist.py`: the date tests are for the ISO form, and one checks that the country still selects the prices and nothing else (53 tests).

DIFFERENCE: the release date column of the CSV is ISO instead of the format of the country.

## 0.5.48 - 07.11.2026 - `wishlist`: a CSV file that is open in Excel is reported instead of a traceback

- **A locked CSV file.** On Windows a spreadsheet program that has the file open makes writing it fail with `PermissionError`, which ended the run with a traceback (`fatal...`) after the saved list had been updated.
  Now `file_write_problem()` checks the CSV file first, before anything is fetched (opening for appending changes nothing in the file and a file that did not exist is not left behind), and the command says
  `cannot write gog-wishlist.csv (Permission denied). If the file is open in another program, for example Excel, please close it and run the command again.`, counts one failure (`csv: file cannot be written`) and exits with status 1.
- **The CSV is written before the saved list is updated.** If the file gets locked after the check, the same message appears and the saved list is left as it was, so the next run reports the same changes again instead of "no changes".
  A saved list (`-output`) that cannot be written is reported the same way instead of with a traceback.
- **The message after the CSV says which date format was used** (`dates as written in DE, like 31.12.2026`, or `dates as 2026-12-31 (give -country ...)` without a country), so it is visible why the dates look as they do.
- `tests/test_wishlist.py`: 7 new tests (54 in total).

DIFFERENCE: only the error handling of the `wishlist` files and the wording of one message.

## 0.5.47 - 07.11.2026 - `wishlist -csv` without a file name writes `gog-wishlist.csv`

- `-csv` takes an optional file name now (`nargs='?'`): `wishlist -csv` writes `gog-wishlist.csv` (`WISHLIST_CSV_FILENAME`), `wishlist -csv my.csv` writes `my.csv`, and without `-csv` no CSV file is written, as before.
  Another option after `-csv` is not taken as its file name (`wishlist -csv -prices`). A `csv = ...` entry of the configuration file works as before.
- `tests/test_wishlist.py`: 9 new tests (47 in total), among them how `-csv` and a `csv = ...` entry of the configuration file go together (the command line wins).

DIFFERENCE: `-csv` alone was an error ("expected one argument") and now works; nothing else changes.

## 0.5.46 - 07.11.2026 - A wrong token password is asked for again

- **A wrong password no longer ends the run with a traceback.** `_read_token_json` now asks for the password again (`Wrong password. Please try again (1 of 3).`), up to `TOKEN_PASSWORD_ATTEMPTS` (3) times, when the program is
  run from a terminal (`_can_prompt_again()`); in a scheduled task or a pipe there is one attempt, as before. The wrong password is forgotten, so it is never used twice, and the right one is kept for the rest of the run
  (saving the refreshed token does not ask again).
- **An empty password** is asked for again as well. It used to be stored as the password (`_TOKEN_PASSWORD = ''`), so a second call did not ask any more.
- **After the last attempt** the same `could not decrypt token file (wrong password or damaged file)` is raised, now as `TokenPasswordError` (a `ValueError`, so existing handlers still work); the top level logs it without a traceback,
  with the hint to delete `gog-token.json` and run `login` again if the password is forgotten, and exits with status 1.
- `tests/test_token_password.py`: 10 tests. (The top-level message in the `__main__` block is not covered by a test.)

DIFFERENCE: only the handling of a wrong or empty token password.

## 0.5.45 - 07.11.2026 - `wishlist`: release dates by country, `UK`, and an empty wishlist

- **Release date of the CSV by country.** `wishlist -country DE -csv ...` writes `23.06.2026` instead of GOG's `2026-06-23T18:59:00+0200`: `format_release_date()` uses the order and separators of the country
  (DE, AT, CH, PL, CZ ... `23.06.2026`; GB, FR, ES, IT, AU, BR ... `23/06/2026`; US, PH `06/23/2026`; NL `23-06-2026`; JP, CN, TW `2026/06/23`; KR, HU `2026. 06. 23.`) and ISO `2026-06-23` without a country or for a
  country that is not in the list. The day is the one in GOG's text (no time zone conversion). The saved JSON file keeps the original text.
- **`-country` has no default value any more** (it is still `US` for the prices): the dates are only written for a country that was given. A configuration file entry `country = ...` works as before.
- **`UK` is taken as `GB`** (`UK` is not an ISO code; GOG answers 400 Bad Request for it). **A country GOG refuses is not retried:** a 400 on the price request is reported once ("use the two-letter ISO code, for example GB"),
  counted as one failure, and the other prices are not requested; the wishlist is still saved. Before, the same request was repeated 4 times with 5 seconds in between, for every game. `request()` has a new
  parameter `no_retry_statuses` for this (statuses that are raised at once for that call only; the global `http_no_retry_codes` are unchanged).
- **An empty wishlist** is sent by GOG as `"wishlist": []`, not `{}`; it was refused with "the answer of GOG has no "wishlist" list". It is read as 0 games (games that were on the list before are reported as removed);
  a list of ids is accepted too.
- `tests/test_wishlist.py`: 38 tests (13 new).

DIFFERENCE: only the `wishlist` command and one new optional parameter of `request()`.

## 0.5.44 - 07.11.2026 - New command `wishlist`: save the GOG wishlist and see what changed

- **New:** `wishlist` saves the games on the wishlist of the logged-in account to `gog-wishlist.json` (`-output`) and reports what changed since the last run: added games, removed games
  (and which of them are now in the manifest), and, with `-prices`, games whose price went down or up. `-csv FILE` writes a spreadsheet (`-delimiter` as for `export`; with `;` the prices use
  decimal commas). Nothing is downloaded: wishlist games are not owned, and GOG gives installers only for owned games.
- **The addresses** (not documented by GOG): `embed.gog.com/user/wishlist.json` (`{"wishlist": {"<id>": true, ...}, "checksum": ...}`), `api.gog.com/products/<id>` for title, slug, release date and
  store link, and `api.gog.com/products/<id>/prices?countryCode=DE`, which lists one price per currency as `"<cents> <currency>"` strings (`"999 EUR"`). Prices are kept as integer cents
  (`parse_gog_money()`, `choose_price()`); `-country` (default `US`) and `-currency` (default: the first one listed) pick what is saved. The format of the first two was checked with real answers
  of an account; the details of `api.gog.com/products/<id>` (`title`, `slug`, `release_date`, `links.product_card`) are read defensively and every field is optional.
- **Details are fetched once** and kept in the file, so a later run only asks for new games (and for games whose details were not available before); prices are fetched for every game on each run with `-prices`.
  A game GOG has no details or price for (404) is kept without them and is not a failure; other request errors are failures (exit status 1). Without `-prices` the saved prices stay and are not reported as changes.
- It uses the normal `request()` (timeouts, retries, the token refresh) and writes the file atomically. A saved file that cannot be read means a first run, with a warning.
- `tests/test_wishlist.py`: 25 tests against a local fake GOG server that answers in the format of the real responses.

DIFFERENCE: a new command only; no existing command, manifest or option changes. **Not tested against the live service:** whether the token the program holds is accepted by `embed.gog.com/user/wishlist.json` (as it is by the other `embed.gog.com` calls) has to be
confirmed with a real run; if GOG answers with a login page, the command says so and suggests logging in again.

## 0.5.43 - 06.11.2026 - The PyObjC package to install is `pyobjc-framework-Cocoa`

- The macOS build in `build.yml` failed at "Install macOS-only dependencies" (`No matching distribution found for pyobjc-framework-CoreFoundation`): that package name does not
  exist. The `CoreFoundation` module (and, through its dependency `pyobjc-core`, the `objc` module) comes with **`pyobjc-framework-Cocoa`**, which `tests.yml` already used.
  `build.yml` now installs that one, with `python -m pip` like the other steps.
- The hint printed when PyObjC is missing (added in 0.5.40) named the wrong package too; it now says `python -m pip install pyobjc-framework-Cocoa`. The test for that warning checks the name.

DIFFERENCE: only a message and the CI file change.

## 0.5.42 - 06.11.2026 - `download` records the BLAKE3 of each file right after it arrived

- **New:** with the optional `blake3` package installed, `cmd_download` hashes every file that has arrived and stores the result in the `blake3` field of its manifest entry,
  so a `verify` that follows does not have to be the "first verify" for it. The hashing runs in the downloader thread that finished the file (`_download_blake3()`, called
  after the move to `!provisional`), so it overlaps with the other downloads and reads a file that is still in the disk cache; the value is written to the manifest by
  `_finish_provisional_downloads()` together with the flags it already resets, in the same single save. Files recovered from an earlier run (already in `!provisional`) are hashed there.
- **The same rule as `verify`: only confirmed content gets a baseline.** With an md5 in the manifest, md5 and BLAKE3 are computed in one read pass and the BLAKE3 is kept only if the md5
  matches (a mismatch logs a warning, keeps the download and records nothing; `verify` will report it). Without an md5 (types GOG gives no md5 for) the known size must match.
- **A re-downloaded file never keeps the BLAKE3 of its old content:** if new data came in and no new BLAKE3 could be recorded (no package, `-noblake3`, md5 mismatch), the old value is removed.
- New option `-noblake3` for `download` (also in the config file); without the package `download` says so once, like `verify` (not on a dry run, which hashes nothing).
  A failure while hashing only produces a warning; it never makes a download fail. `prev_verified` is untouched: only `verify` marks a file as verified.
- `tests/test_download_blake3.py`: 11 tests on 8 new scenarios of the download rig (`blake3_*`). The rig now patches `_blake3` to `None` unless a scenario asks for the stand-in, so the results do not depend on whether the package is installed on the machine.

DIFFERENCE: with `blake3` installed, `download` adds the field `blake3` to the manifest entries of the files it fetched and reads each finished file once more. Without the package, or with `-noblake3`, nothing changes except the one-line notice.

## 0.5.41 - 06.11.2026 - Less console output when many files are missing

- **`verify`: one line per game.** A game that was not downloaded (yet) printed one `missing file ...` warning per file, 99 lines for 14 games, and
  the same files were listed again in the run summary. Up to `MISSING_FILES_LISTED` (3) missing files of a game are still named; beyond that one line
  says `game: 6 of 6 files missing`, and the names go to the debug level (run with `-debug` to see them). Every missing file still counts as a failure (exit status, summary).
- **Grouped failure list in the run summary.** When there are more failures than `max_listed_failures` and all of them are files inside game folders, the summary
  shows one line per reason (`missing: 99 files in 14 games`) and the games with their number of files in a wrapped paragraph, instead of the first 40 file names and
  "and 59 more". A short list still names every file, and failures without a folder keep the old cut-off.
- `tests/test_failure_summary.py`: 9 tests.

DIFFERENCE: only the wording and amount of console / log output changes. No file is treated differently, and the counts, exit status and manifest are as before.

## 0.5.40 - 05.11.2026 - Review fixes: download hang, token timeout, root file system, partial info files, macOS without PyObjC, Python 3.8 / 3.9

- **Download threads could wait forever.** `_download_worker` asked `job.work.empty()` and then called `job.work.get()`. With several threads, two of them
  could both see one file left; the second waited in `get()` for a file that never came, and `cmd_download` waited for that thread. It now takes files with
  `get_nowait()` and stops on `queue.Empty`.
- **The token refresh had no timeout** (`renew_token` called `session.get` without `timeout=`); a connection that stalled held `token_lock`, so every thread
  waited. It now uses `http_timeout`, like every other request.
- **An expired login in a download thread.** `renew_token` ended with `sys.exit(1)`; in a worker thread that only ended the thread, and the run reported
  "a download thread stopped unexpectedly". It now raises `AuthExpired`, a `SystemExit` subclass (so in the main thread nothing changes: exit status 1, and no
  `except Exception` can swallow it). A worker catches it, marks its file as failed with "login expired, run the login command again", and sets
  `job.abort`, so the other workers take no new files; the files that were not started are reported with the same reason.
- **`get_fs_type` never tried the root mount `/`**, so a folder on the root file system was "unknown" and was not preallocated (containers, one-partition installs).
- **`ConditionalWriter` wrote its buffer even when the `with` body raised**, which could leave an incomplete `!info.txt`, `!serial.txt` or MD5 XML. It writes
  nothing then. A changed existing file is now replaced atomically (`atomic_write_text`, permissions kept; in place as before if the folder is read-only).
- **macOS without PyObjC.** `CoreFoundation` and `objc` were imported unconditionally, although the README lists PyObjC as optional. They are imported by
  `_import_macos_modules()`; without them the `Wakelock` is skipped with one warning and the program runs.
- **Python 3.8 and 3.9.** The check exited below 3.10, so the `specialPy3 = [3,8]` branch was dead. Now only versions below 3.8 stop; 3.8 and 3.9 print a
  warning and carry on (`check_python_version()`). The one call that needed 3.10, `glob.glob(..., root_dir=...)` in the split-zip test of `verify`, is replaced by
  `_multi_zip_parts()`. The syntax was checked for 3.8, but there is **no 3.8 / 3.9 in the test matrix**: they are best effort.
- `tests/test_review_fixes.py`: 24 tests, one or more for each point above. (`assertNoLogs` in `tests/test_run_summary.py` needs 3.10; the tests themselves still
  need 3.10.)

DIFFERENCE: an expired login inside a download thread now stops the download run with "login expired" failures instead of a silent thread death; Python 3.8 and 3.9 start
with a warning instead of exiting. Everything else only removes a hang, a wrong "unknown" or a corrupt write.

## 0.5.39 - 04.11.2026 - `-tags` and `-skiptags`: select games by the tags of your GOG library

- The tags are the ones you made in your GOG library (for example "Favorites", "NEXT TO PLAY"). GOG sends them with the product list: every product has a list of tag ids, and the whole answer has the list of `{id, name}`. `update` now stores the **names** in the new field `tag_names` of every game in the manifest. Matching ignores case, accents, punctuation and spacing (`-tags "next to play"` finds `NEXT TO PLAY`); a game matches if it has **any** of the tags given.
- New options `-tags TAG ...` and `-skiptags TAG ...` for `update`, `download`, `verify`, `import` and `backup` (also settings in the config file). They combine with each other and with `-ids` / `-skipids`: `-tags` with `-ids` means the games that are in both; `-skiptags` always wins. A tag with spaces must be in quotes; if the words of one tag were typed without quotes, the message says so.
- `download`, `verify`, `import` and `backup` read the tags from the manifest: the options are turned into ids before the command runs (`apply_tag_options()`), so those commands needed no change. The selection can never fall through as "all games": if nothing is left, or the manifest has no tag data yet (run `update` once), the command stops with a message. A tag that no game has is an error and fails the run, with a list of the tags that exist.
- `update -tags` / `-skiptags` limit what is fetched, like `-ids` does, but keep the normal rule for what counts (new and updated games; add `-full` for all of them). Like `-ids`, a tag-limited update never removes games from the manifest. A tag that does not exist in your library is reported at the end of the run and fails it; a tag that exists but has no games is not an error.
- Every `update` that reads the product list also refreshes `tag_names` of the games that it does not fetch again (the list is read anyway; no extra requests), and saves the manifest if a tag changed. So a tag change on GOG reaches the manifest with the next `update`, even a plain one.
- The tag data was checked against the documented format of the GOG product list (`tags` with `id`, `name` at the top and a list per product). The format of the per-product list was not visible in an example with data, so ids, `{id, name}` entries and unknown ids are all handled; an id without a known name is kept as the id.
- `tests/test_tags.py`: 26 tests (name resolution, selection, ids/skipids handling, the dispatch in `main`, and `update` against a fake product list, including a control that a normal update does remove a game that left the account while a tag-limited one does not).

DIFFERENCE: `update` writes the new field `tag_names` to the manifest and may save the manifest even when it has nothing else to change (when only a tag changed). Everything else is new options; without them nothing changes.

## 0.5.38 - 04.11.2026 - Optional BLAKE3 checksums kept in the manifest

- GOG publishes only MD5, so BLAKE3 cannot be checked against anything from GOG. It is a **local fingerprint**: the first time a file passes `verify`, its BLAKE3 is stored in the manifest entry (field `blake3`) - "trust on first verify". A later full verification (`verify -forceverify`) then compares only that BLAKE3 instead of computing the MD5 again, which detects any change since the file last passed (bit rot), and is faster on fast disks (BLAKE3 can use several threads and a memory-mapped file).
- Optional: needs the `blake3` package (`python -m pip install blake3`). Without it the program behaves exactly as before and says so once per `verify` run. New option `-noblake3` (also a config setting under `[verify]`) switches the feature off.
- A baseline is recorded only for content that was actually confirmed: a file whose MD5 matched, or - for types GOG gives no MD5 for (`.zip`, `.001`, ...) - a file with a known size that passed the size check (the zip test follows). Nothing is recorded when `-skipmd5` was used for a file that has an MD5, and nothing is recorded or compared for an MD5-less file that is flagged as changed (its recorded value may describe the old content).
- If the BLAKE3 differs and the MD5 is known, the MD5 decides: a mismatch is reported as before (`wrong checksum (md5)`); a match means the stored BLAKE3 was stale, so it is refreshed with a warning. Without a usable MD5 (`-skipmd5`, or a type without MD5) the failure is reported as `changed since last verification (blake3)`. A file that fails is cleaned/deleted as usual and loses `prev_verified`.
- A matching BLAKE3 clears the change mark exactly like an MD5 match (only an MD5-verified file can have one).
- `update`: the BLAKE3 is carried over to the new entry when MD5, size and language are unchanged (also across a rename), and dropped when the MD5 changed. For an MD5-less file it is carried like `prev_verified`, and `-strict` drops it too. New entries get `blake3=None`; manifests from older versions simply lack the field.
- New helper `hash_file()` computes MD5 and/or BLAKE3 in one read pass; `hashfile()` and `hashstream()` are unchanged.
- The summary of `verify` gets three lines when BLAKE3 is active: matches, recorded, mismatches.
- Files that were verified before this version have no baseline: run `verify -forceverify` once to record them (a normal `verify` skips files that are marked as verified). Files downloaded later are verified, and so recorded, by the next `verify`.
- `tests/test_blake3.py`: the tests use a stand-in module with the same small interface, so they run without the package. The real package was **not** available where this entry was written, so it was not run against the real library; the code uses only `blake3.blake3(max_threads=blake3.blake3.AUTO)`, `update()`, `update_mmap(path)` and `hexdigest()`, each guarded with a fallback.

DIFFERENCE: with the package installed, `verify` records BLAKE3 values in the manifest and `-forceverify` compares them instead of the MD5 for files that have one. Without the package, or with `-noblake3`, nothing changes.

## 0.5.37 - 03.11.2026 - JSON token storage and legacy changelog compatibility

- Fix `handle_game_updates()` for older manifests that do not contain a `changelog` field.
- Store tokens in `gog-token.json`. The default is password-based AES-256-GCM encryption with a scrypt-derived key; the password is requested at most once per process and is never stored. `GOGREPO_TOKEN_MODE=plain` explicitly opts into unencrypted JSON for unattended use.
- Read `gog-token.dat` only when the JSON file is absent, migrate its contents to the JSON file, and leave the legacy file unchanged. A corrupt or undecryptable JSON file never triggers a legacy fallback.
- Add regression tests for the missing changelog and token migration/encryption behaviours.
- Add a comment recording the future plugin-system idea; no plugin loader is implemented.

## 0.5.36 - 02.11.2026 - The tests no longer write into the folder they are started from

- Found while packaging this version: after a test run the working folder held a `gog-manifest.dat` and a `gog-manifest.dat.bak` that nobody had asked for. The
  hook tests of `-ids` / `-skipids` in `tests/test_ids.py` (introduced with entry 24) run `verify`, `import` and `backup` on a made-up library of twelve games. They replaced
  the manifest *loader* but not the manifest *saver*, and these commands save the manifest at the end, into the current folder.
- That is a hazard: if the suite is started from a folder that also holds a real library, its `gog-manifest.dat` is overwritten with the made-up one, and after a second run the
  `.bak` is too. A canary file in the starting folder showed exactly that before the fix. No test of the program itself was wrong; the tests were.
- Fixed at the root: `tests/_bootstrap.py` now runs the whole test process in a scratch folder (it changes into it before the script is imported, because the script opens
  `gogrepo.log` in the current folder when it is loaded) and removes it at the end. The hook tests also patch `save_manifest` now, so the cause is not only hidden.
  `tests/test_isolation.py` guards it: the tests run in the scratch folder, a manifest saved with the default path lands there, the script's log file is there, and the scratch folder is outside the
  repository and the starting folder.
- Checked with a canary: the full suite started from a folder holding a `gog-manifest.dat` and a `.bak` passes, leaves both byte for byte as they were, creates nothing there, and no scratch folder is left over.
- If you ran an earlier version of the suite from a folder that holds a real library: look at its `gog-manifest.dat`. A manifest of exactly twelve games (`beneath_a_steel_sky`, `dune`, `gakkou`, ...)
  is the made-up one. `update -full` builds the manifest again from your GOG account (the downloaded files on disk are not touched by that).

DIFFERENCE: none for the program; only the tests changed.

## 0.5.35 - 01.11.2026 - `update` warns when it is about to narrow the manifest

- Found in a real log (30 October): an `update` with a typed `-lang` (and another with a typed `-os`) replaced the installers of the games it fetched by the ones for that
  language and system only, as an update always does. Extras are not filtered, so they stayed. The next full update added the installers back as new entries, and
  `download` marked 216 of them "for change" and had to check them again. Nothing was lost and almost nothing was downloaded, but it cost a long check, and in
  between a `clean` would have moved all those files to `!orphaned`.
- Before a new update starts (not while it resumes an interrupted one; after that, the update that was asked for is checked), `warn_if_update_narrows_manifest()` compares
  the manifest with the operating systems and languages the update will use. It counts the installer entries (`downloads`, `galaxyDownloads`, `sharedDownloads`) that
  the update would drop for the games it could fetch (all games, the ones named with `-ids`, without `-skipids`), using the same filter as the update itself
  (`filter_languages`, with the English fallback of the default language, so that fallback is not reported). It then warns in three lines: what the update is limited to,
  how many installer files of how many games would go and why (which systems, which languages); what that means (the files stay on disk, `clean` would move them to
  `!orphaned`, a later update adds the entries back as new ones, `download` checks them again); and what to do (stop with Ctrl-C and run update again with all systems and
  languages, or put them in the config file).
- It only warns, as decided. It says "up to N" for an update without `-full`, because only the new and updated games are fetched then and that is not known beforehand;
  with `-full` it says "every game". Extras are not counted. The `-installers` option is not taken into account.
- tests/test_update_warning.py: the counting (systems, languages, strict language, the English fallback, both together, `-ids` also as the name on GOG, `-skipids`, ids that are
  not in the manifest, old manifests without the galaxy and shared lists, extras, empty input), the wording, and that `cmd_update` checks once with the lists it will use,
  also for the update that follows a resumed one.

## 0.5.34 - 01.11.2026 - The log starts every run with the version of the program

- Asked for after the analysis of a real log, which did not say which version of the program had written it. The first line of every run in the
  log file `gogrepo.log` is now, for example: `2026-11-01 09:00:00 | INFO     | gogrepo_delta.py version 0.5.34 (Python 3.14.0, Windows-11-10.0.26100-SP0)`.
  It names the version, the Python and the operating system.
- It is written to the log file only, not to the console, so it adds nothing to what is printed, and a `list` that is piped stays clean. It comes
  before everything else a run logs (the notes about the config file, for instance). With `-nolog` nothing is written, as before; `--help` and
  `--version` do not start a run and write nothing.
- `version_line()` builds the text; `process_argv()` writes it as soon as the log file is attached.
- tests/test_log_header.py: the line is first, names version, Python and system, is in the layout of the other lines, comes once per run, and
  stays out of the console, out of `list` output and out of runs with `-nolog`.

## 0.5.33 - 01.11.2026 - `list` says why a search finds nothing when the filter removed the games


- Found in a real log (30 October): a `list ultima` with a language that the Ultima games do not have said "no game matches 'ultima'", although the games are in the manifest (`-ids` found them at once). The words had matched; it was the language filter that took the games out of the list.
- Now, if the words fit games that the operating-system / language filter removed, the message says so: "3 games match 'ultima' (title, title, title) but none has files for the chosen operating system / language." Up to five titles are named. It also names the filter in use (`-os`, `-skipos`, `-lang`, `-skiplang`) and says that it may come from the config file, which is easy to forget.
- If the words fit no game at all, the message is as before ("no game matches ...", with suggestions). The suggestions now come from all games in the manifest, not only from those that passed the filter.
- A filter that leaves nothing when no words were given ("no game has files for this operating system / language") now names the filter in use too.
- In every case the run ends with exit status 1 and a failure in the summary, as before.
- tests/test_ids.py, ListCommandTests: words matching filtered-out games, the filter being named (typed and skip variants), the count and the "and N more" for many games, suggestions with a filter set, the empty-filter message, and games that pass the filter being listed as before.

DIFFERENCE: only the wording of the messages and the source of the suggestions (all games).

## 0.5.32 - 01.11.2026 - The download summary counts what was really downloaded

- Found in a real log (30 October): after an update with a narrowed language, the next full update re-added 216 installers as new, and
  download marked them "for change". Chunk by chunk they were all already right on the disk, so only one file (100 MB) was fetched,
  and the 208 GB were checked locally in four minutes. The summary nevertheless said "files downloaded: 216 (208.41GB)".
- Now the bytes that really arrive are counted per file (job.transferred, filled by _download_ioloop, the only place that receives
  data). In the summary: "files downloaded" counts the files of which data was fetched and shows the amount that came from GOG (for a
  fresh download that is the size of the files, as before; for a file repaired chunk by chunk it is only the chunks that were fetched),
  and the new line "files verified in place (nothing downloaded)" counts the files that were marked for change but needed no data,
  with their size. "files recovered from an earlier run" is unchanged.
- tests/test_run_summary.py: TransferSummaryTests (the figures are checked against the bytes the fake server really sent; the rig server
  now counts them: file_bytes) and FinishProvisionalClassificationTests.

DIFFERENCE: the size shown after "files downloaded" is now the data transferred, which is smaller than before when files were only
  repaired or checked. Scripts that read the summary line "files downloaded" still find it; the checked files are a new line.

## 0.5.31 - 01.11.2026 - Bug fix: atomic_write_text could close a file descriptor that no longer belonged to it

- Found in the review of entry 30. After os.fdopen() took over the descriptor of the temporary file, the with block closed it; if a
  later step failed (typically the final rename, when a virus scanner holds the file on Windows), the error handler called
  os.close() on the same number again. By then another thread may have opened a file and received that number, and it was closed
  under that thread's feet ("Bad file descriptor"), for example a download in progress. The descriptor is now closed by the error
  handler only when no file object took it over (fd is set to None once it has). Rare (a failed save is needed), but the damage
  would have landed on an unrelated file.
- tests/test_atomic_save.py, DescriptorOwnership: a failed swap and a failed write close nothing twice and keep the old file,
  another thread's file survives a failed save, and a descriptor that no file object owns is still closed exactly once.

## 0.5.30 - 31.10.2026 - Security hardening and compatibility-preserving data loading

- Replaced eval-based loading of legacy manifests, resume manifests, config and tokens with
  ast.literal_eval plus recursive AttrDict conversion. Legacy text remains readable.
- Atomic writes now use uniquely-created temporary files; token files are explicitly private
  (0600 on POSIX), including on first creation. Existing file permissions remain preserved.
- Download retry delays no longer hold the shared job lock; response/watchdog cleanup is
  performed in finally blocks.

## 0.5.29 - 31.10.2026 - Credits; test_download_loop.py replaced by the repository owner's version

- __author__ now lists the authors of this version too: eddie3, kalanyr (the original projects), MarS301 and claude.ai.
- tests/test_download_loop.py is the version written by the repository owner and is used as it is from now on. The only change
  against the earlier file is test_restarting_does_not_create_threads: it no longer counts all the threads of the process
  (other threads starting or ending at that moment could disturb the count, which showed on Windows) but checks that the stall
  watchdog still has the same timer thread, and that it is alive, after 20000 pause()/resume() calls. It still fails when a
  timer thread is started for every chunk again.

## 0.5.28 - 31.10.2026 - Bug fix: download left finished files in !provisional when nothing else needed downloading

- Known since the refactoring. An interrupted run can leave completely downloaded files in !downloading/!provisional (they are moved to
  their folders at the end of a run). The next run found them, but if no other file needed downloading it stopped at "nothing to
  download" before moving them, so they stayed there until some later run happened to download something else. Now it says
  "nothing else needs downloading; moving N completed file(s) ... to their place", moves them (which also resets the
  "needs update" flags and saves the manifest, as in a normal run), removes the empty folders, and the summary at the end counts
  them under "files recovered from an earlier run". With nothing left in !provisional the run still says "nothing to download".
- tests/test_download.py: the rig scenario provisional_only (everything in place except one finished file in !provisional) now has
  tests for the file being moved, for the message, and for the summary count.

## 0.5.27 - 31.10.2026 - Config file: a remark about commas and lower case; the project address is the new repository

- The header of the generated file now says that lists are separated with commas (not with spaces or semicolons), and that the
  section names and the values of os and lang are written in lower case while option names may be in any case. That is how the
  program behaves (checked, and kept true by tests): "os = windows linux" and "os = windows; linux" are refused, "os = Windows" and
  "lang = DE" are refused, "[COMMON]" is ignored with a warning, "OS = linux" and "DryRun = true" work, and ids of games may be
  in any case (names are compared ignoring case). Only new files get the remark; a file made earlier is never changed.
- __url__ (shown in --help) and REPO_HOME_URL (used by update_self, which is not connected to any command) now point to
  https://github.com/MarS301/gogrepo_delta. __author__ and the history above keep the credit to the original projects.

## 0.5.26 - 31.10.2026 - Bug fix: the chunk-verification retry loop did not wait before trying again

- Known since the refactoring. When a chunk of a file that is verified against GOG's MD5 data arrives incomplete,
  _download_with_chunk_verification logged "will retry in Ns..." and then tried again at once, so all the retries were used up within
  moments, on a connection that had just failed. The plain download loop has always waited. It now waits HTTP_RETRY_DELAY
  (config setting http_retry_delay) before each retry, and not after the last try. It waits outside job.lock, so the other
  downloads are not held up (the plain loop does hold the lock while it waits; see the known issues).
- tests/test_chunk_retry.py: a chunk that arrives at once needs no wait; one that fails once is retried after the delay; the number
  of retries and the waits between them follow the settings; no wait after the last try, after an HTTP error or after an unexpected
  Content-Range; the lock is free while waiting; the plain loop waits the same time.

DIFFERENCE: a download with chunk verification that hits incomplete chunks now takes up to http_retry_count x http_retry_delay
  seconds longer before it gives up (4 x 5 s with the default settings); that is what the message always promised.

## 0.5.25 - 31.10.2026 - Bug fix: fetch_chunk_tree raised NameError for an old manifest and a signed download address

- Known since the refactoring (it was listed under the known issues). When a game has no api_downlink in the manifest (a manifest
  made before it was stored) and its download address carries the signed parts (wsSecret, wsTime, prefix), the warning used the
  name `d`, which does not exist in that function. NameError is not caught there or in the download worker (only IOError is), so
  the downloader thread ended with an exception and its file was left unfinished. The warning now names the file as the other
  warnings of the function do, and the function returns None, so the file is downloaded without chunk verification, as was
  intended. (The same wording in fetch_file_info is fine: `d` is its parameter.)
- fetch_chunk_tree had no tests. tests/test_chunk_tree.py now covers every branch: file types without checksums, the api_downlink
  way, the old way with and without a signature, and every error that is caught (404, other HTTP errors, bad XML, connection
  and decoding errors).

## 0.5.24 - New command: list (search the manifest by name), and friendlier -ids / -skipids ("did you mean ...")

- list [words] [-os ...] [-lang ...] [-format table|ids]: the games in the manifest, or those whose id, title or name contain all
  the words (any order, any case, accents and punctuation ignored, parts of words match; an id is found by 4 or more digits).
  Table columns: ID, TITLE (what -ids takes), NAME (as on GOG), OS, LANG, FILES, SIZE. -format ids prints only the titles, one per line.
  Reads the manifest only (no login, no network). No match: suggestions and exit status 1. The words go before the options
  (an option like -os takes everything after it as values). The table is on stdout, the messages are on stderr, so it can be piped.
- -ids and -skipids in download, verify, import and backup now go through resolve_game_ids():
    * an exact title or id selects a game, as always (exact wins);
    * otherwise a name that differs only in case, accents, punctuation, underscores or spacing selects it, if it fits ONE game
      ('Beneath a Steel Sky (1994)', 'Ultima IV: Quest of the Avatar', "Baldur's Gate"); the log says what it was taken as;
    * a name that fits several games selects none of them and names them; a game is never selected because it looks a bit like
      the text (suggest_games only suggests: typos, parts of a name, other word order; at most 3, none for texts under 3 letters);
    * words of one name typed without quotes (-ids Beneath a Steel Sky) are recognised and the message shows the quoted form.
  Whatever matches no game is logged with the suggestions and recorded as a failure, so the run ends with exit status 1;
  the games that did match are still processed. -skipids is resolved the same way (a typo there used to skip nothing, silently);
  in download both are looked up among all games, so a skip id outside the games selected by -ids is not a failure.
- update is NOT changed: it checks -ids against the GOG account while scanning, not against the manifest.
- Names: normalize_name() keeps letters of every script as they are and only drops accents on Latin letters, so Japanese names that
  differ by a voiced mark stay different; trade mark signs and apostrophes are dropped, other punctuation becomes a space.

DIFFERENCES: (1) -ids / -skipids names are matched more widely (long titles etc.). (2) A -ids / -skipids entry that matches no game
  now makes the run fail (exit status 1) and is reported, also when other ids matched, and in import and backup where it was silent;
  a scheduled run with a stale id in -skipids now ends with 1. (3) The notice about a newly created config file goes to stderr.

Fixed on the way: with a config file present, a positional argument that takes several values (the list words) was cut to one.

Checked: tests with titles in the style of a real manifest (long titles, trade marks, apostrophes, accents, Japanese, look-alike
  names), mutation checks, the offline download rig (old and new agree in all 69 scenarios apart from the new message in
  ids_not_found and the known nondeterministic order of file names in one warning: 2 of 10 runs differ for the old version
  compared with itself, and for the new one), and runs on a real 76-game manifest. Not checked: the real GOG service.

## Entry 23 - Config file: options with the same name in several commands are set once, in [common]

- Requested: whoever sets a new default normally wants it for every command that has the option (os for download and update, ...),
  and can still override it on the command line. [common] now holds any option; an entry there counts for every command that has
  the option, and commands that do not have it ignore it without a warning. A [command] section overrides [common] for that command.
- The generated file lists an option once, in [common], when two or more commands have it, it is of the same kind (a yes/no switch,
  a list, or a single value with the same type, values and default) and it means the same thing in each (the same note in
  CONFIG_NOTES): shared_options(). Options that differ stay in the sections of their commands: installers (a choice in update, a
  yes/no switch in trash), src_dir and dest_dir (different folders in import and backup). savedir (download and export) is shared.
  A command that has nothing of its own gets no section ([clear_partial_downloads]); the section is still accepted if written by hand.
- A value in [common] that does not fit one command (installers = both for trash) is an error naming that command, only when that
  command is run. An entry in a command section for an option that excludes another (skipos) replaces the [common] entry of the
  excluded option (os) for that command; two excluding entries in the same section are an error.
- The generated file went from 229 to about 190 lines. Files made by earlier versions still work (same keys; [common] is wider).

## Entry 22 - The generated config file is shorter and clearer (469 lines became about 230; nothing about reading the file changed)

- Found when the generated file was looked at on a real machine: a blank line and a 2-3 line comment for every one of 123 entries,
  the same options explained again in up to five sections, and the description of a section sitting right above the comment of
  its first option, so that it read as part of that option's text.
- Now: a header of a few lines; [settings] in six commented groups (SETTING_GROUPS) instead of one paragraph per setting (the
  built-in default is the value that is written, so "(default: x)" is gone; delete the file to see the defaults again); one short
  line per option, written by hand in CONFIG_NOTES; options that belong together (os/skipos, ids/skipids, the skip... family, ...)
  are listed together under one comment that names each of them ("os: ...; skipos: ..."); an option is explained where it first
  appears and listed without a comment in later sections, except where it means something else in another command (installers
  in update and trash, savedir in download and export, src_dir/dest_dir in import and backup), which get their own note;
  options with a fixed set of values show it ([noresume|resume|onlyresume]); no blank lines between entries.
- An option without a note (a flag added later) still appears, with the first sentence of its help text. The tests insist
  that every option has a note, that no note names an option that does not exist, and that every setting is in exactly one group,
  so adding a flag means adding a line to CONFIG_NOTES. SETTINGS now has four fields (the explanation moved to SETTING_GROUPS).
- An existing config file is never replaced, so a file made by the previous version keeps working as it is (checked: same keys,
  same sections); delete it to get the new layout.

Checked with a real manifest (76 games, 217 files): export gives the same CSV with the old file, the new file and no file.

## Entry 21 - Windows: "is anybody there to answer?" (found when the tests were run on Windows 11 / Python 3.14)

- _stdin_is_interactive() relied on sys.stdin.isatty(). On Windows that is also true for the NUL device (what a scheduled task
  or "command \< NUL" gives as input), so a scheduled run printed the question "Use the backup copy ...? [y/N]", read nothing
  and carried on as if the answer was no, instead of saying that the run is not interactive. The outcome was the same (the
  run stops with exit status 1 and the manual instructions), but with a dangling question and without the explanation.
  On Windows it now also asks the console API (GetConsoleMode, via ctypes) whether standard input is a real console.
- The tests that start the script as a subprocess now give it no input (stdin=DEVNULL); before, they inherited the input of
  the test runner, which on a real terminal made the script wait for an answer (a 120 s timeout in one test).

Checked here: the decision logic and the way the console API is called (with a stand-in for it). Only a real Windows run can
  show that GetConsoleMode really answers "no" for NUL; the test test_a_missing_manifest_with_a_backup_stops_a_scheduled_run
  starts the real script with no input and checks for the message, so running the test suite on Windows covers it.

## Entry 20 - Renamed to gogrepo_delta, version 0.5.19, and a config file (gogrepo_delta.cfg)

- Script file and program name are now gogrepo_delta.py (__appname__, the --version text, the User-Agent GOGRepoDelta/0.5.19).
  Nothing else was renamed: gogrepo.log, gog-manifest.dat, gog-token.dat, gog-resume-manifest.dat, gog-config.dat and the
  logger name keep their names, so an existing library and log keep working.
- Config file: INI format, gogrepo_delta.cfg in the folder the program is started from (like the manifest). Set the
  environment variable GOGREPO_DELTA_CONFIG to use another file. When the program is started and there is no such file,
  it is created with every setting and every command-line flag at its default, each with an explanation (ensure_config_file;
  only when the script is run, not when it is imported). An existing file is never changed by the program.
- [settings] holds the former hard-coded values: log_max_mb, log_backups, http_retry_count, http_retry_delay, http_timeout,
  http_no_retry_codes, download_chunk_size, download_threads, progress_interval (was a fixed 1 s sleep), resume_save_threshold,
  summary_max_items, max_listed_failures, file_replace_attempts, file_replace_delay. The built-in defaults are the old values,
  so without a file (or with the generated one) nothing behaves differently. They are read when the program starts, because
  the constants and some default arguments are built from them. A wrong value stops the program with a message that names
  the file, section, key and the reason; an unknown key is a warning. An empty value means "use the default".
  NOT moved: HTTP_FETCH_DELAY (defined but used nowhere), the GOG addresses / client id / secret, file names, the language
  and operating-system tables (not settings; decided with the requester).
- Flag defaults: section [common] (nolog, debug, manifestformat) and one section per command, with one key per flag, named
  like the flag without the dash. Precedence: typed on the command line, then [command], then [common], then the built-in
  default. Built from the real parser (build_parser), so the file and the flags cannot drift apart.
    * yes/no flags: true/yes/on/1 means "as if the flag was typed" (also for the flags that turn something off);
      false or empty means nothing. A flag set in the file cannot be switched off from the command line (no -no-xxx); set it to false.
    * lists (os, lang, ids, skipfiles ...): separated by commas, or one per line; spaces inside an entry are kept.
    * a flag typed on the command line replaces the file's entry completely (lists are not merged) and also switches off the
      entries of the flags that exclude each other with it (file "os" is ignored when -skipos is typed). Two entries in the
      file that exclude each other are an error. Abbreviated flags (-skipo) count as typed.
    * folder arguments (savedir, gamedir, src_dir, dest_dir, cleandir) can be given in the file, then they may be left out.
      Typed folders fill a command's folders from left to right, so give all folders of a command in the file or none.
    * login user name and password are never read from the file.
    * an entry for os / lang / ids counts as typed: for lang this means the English fallback of the default language does not apply.
    * help and version never read the file, so a broken file cannot block them.
  The notes at the start of a run list what the file changed (info line "defaults from the config file ..."), only entries
  that differ from the built-in default.
- process_argv was split into build_parser() (all flags) and process_argv() (reads the config, applies it, parses). To
  know which flags were really typed, the command line is parsed a second time with a parser without defaults and with
  optional folder arguments (_explicit_dests); this only happens when a config file with sections exists.

DIFFERENCE: a file gogrepo_delta.cfg now appears in the working folder on the first run. Nothing else changes with the default content.

Not checked: the real downloads and the real GOG service (as before). Windows and macOS were not tried; the config code uses
  only standard Python and plain relative paths, and the tests do not depend on the operating system. The file is read as
  UTF-8 (a byte order mark is accepted) and written as UTF-8 with the line endings of the system.

## Entry 19 - Login: new captcha detection and a switch to force browser login (requested after GOG changed its login page)

- login_form_has_captcha(): the automatic login looks for a captcha in GOG's login form before it sends the password. It
  now recognises both the old Google reCAPTCHA box (div "g-recaptcha form__recaptcha") and the new captcha field list
  (ol "form__fieldset form__fieldset--captcha", taken from a capture of the changed page). Matching is on the exact class
  text, as before. Before, the new page was not recognised, so the password was sent to a page that could not complete
  the login and the run ended with "Galaxy login failed".
- New switch: login -browser (also --browser). No user name or password is asked for or sent, and GOG's login page is not
  read at all, so a captcha or any other change to that page cannot break it. The sign-in page's address is shown and the
  default browser is opened on it; the person signs in there and pastes the address the browser ends up on
  (.../on_login_success?...&code=...). The code in it is swapped for the token as before. Meant as the way out when the login
  page changes again. A user name / password given together with -browser are ignored with a warning.
- The automatic login, when it meets a captcha (or cannot find the login form), still shows the address and asks for the pasted
  address as before; it now also points to -browser. It does not open a browser by itself.
- The paste step is shared (ask_for_signed_in_url, login_code_from_url) and no longer breaks on spaces or a line break around
  the pasted address; the pasted address (it holds a one-time code) is never written to the log.
- The login command is split into small functions (galaxy_auth_args / galaxy_auth_url, browser_login, _login_with_password,
  _save_login_token). The password flow itself is the old code, moved unchanged apart from the three points below.
- Fixed on the way: an \<input> without an id on the login page raised KeyError (now ignored); a login code that GOG refuses
  (used twice, too old, network problem) gave a traceback and is now a message that says what to do.

DIFFERENCE: the login command now exits with status 1 when the login failed (it always exited with 0 before, also after
  "Galaxy login failed"), so scripts can tell. Nothing else in the normal login changed.

Not checked: the real GOG login pages and token service were not reachable from where this was written. The detection was
  tested on small stand-in pages that contain the elements named above, not on a saved copy of GOG's page; the browser flow
  was tested with GOG's answers faked. Whether GOG shows Google / Discord sign-in on this page, and so whether -browser works
  for such accounts, is not known.

## Entry 18 - End-of-run summary and exit status (requested)

- Every command reports what it did, and main() logs it before the total time ("-- summary: \<command>"): files downloaded
  (with size), already up to date, skipped, recovered from an earlier run; games added / re-checked by update; files
  verified, copied, imported, moved to the orphan folder, deleted. Failures are listed one per line with the reason.
- Failures: a file that could not be downloaded (HTTP error, incomplete, thread crash, or never attempted) or exists twice;
  a game update could not fetch; a file verify found missing / with the wrong size / wrong checksum / failing the zip
  test; a backup source file with the wrong size; a file or folder clean / trash / clear_partial_downloads could not move
  or delete.
- Exit status: 0, or 1 if there were failures. Fatal errors still exit with 1, Ctrl-C prints the summary of what was done
  so far and exits with 1. Note that verify now exits with 1 whenever it finds a problem, including files that are missing.

DIFFERENCE: the exit status can now be 1 for a run that completed; an update that fails for one game still goes on with
  the others (and still drops that game from the resume list, as before) but now reports it.

## Entry 17 - A missing or damaged manifest: use the backup, never an empty list (requested)

- Before, a manifest that was not found was treated as an empty library, so the next update would rebuild everything and
  overwrite the backup history; a manifest that could not be read gave a traceback.
- Now, if gog-manifest.dat is not found (or is damaged, not valid UTF-8, or cannot be parsed) and gog-manifest.dat.bak
  exists, the program says what is wrong, shows the backup (date and size; it is the manifest as it was before the last
  save) and asks "Use the backup copy ... instead? [y/N]" (y, yes, j, ja). Yes: the backup is checked, restored as
  gog-manifest.dat (a damaged file is kept as gog-manifest.dat.damaged, never thrown away) and used.
- If the answer is no (or there is no backup) and the command is 'update', a second question follows: "Start a new, empty
  manifest ... instead? [y/N]". Yes: the damaged file and the old backup are kept (.damaged, .oldbackup, because later saves
  would overwrite the backup) and update starts from scratch. No: it stops with exit status 1, and only now explains how to
  copy, move or delete by hand. Other commands (clean, trash, download, ...) never offer a new manifest, since an empty one
  is useless for them or dangerous (clean would treat every game folder as an orphan): they stop with that explanation.
- A run without a terminal (scheduled task) asks nothing and stops with exit status 1 and the same explanation.
- No manifest and no backup is still the normal first run. A manifest that exists but cannot be read (no permission, locked
  by another program) now stops with a message instead of being treated as empty. A missing resume file is normal and
  never asks.

## Entry 16 - Text in any language (checked after a question about Chinese characters)

- Manifest (JSON and old format), log file, !info.txt / serial files and the export were already read and written
  as UTF-8, so Chinese, Japanese, Korean, Russian, Arabic, Thai, accents and emoji work in all of them.
- Fixed: console output that is redirected on Windows (scheduled task, "> file", pipe) uses the legacy code page.
  A log line with characters outside it caused a "Logging error" traceback and was lost, and print() crashed.
  Such characters are now shown as \uXXXX escapes (the log file has the real characters).

## Entry 15 - Faster, still readable manifest, and an export command (requested)

- The manifest and the resume manifest are now saved as indented JSON (one field per line, keys sorted, special
  characters not escaped) instead of Python text. Any text editor can open it. Measured with this script on a
  synthetic library of 1500 games (12 MB): save 3.0 s -> 0.4 s (this includes the read-back check below and the .bak
  copy), load 2.9 s -> 0.09 s. The plain json module alone is faster still, the rest is the safety net.
- Old-format files load as before (a JSON file is recognised by its first character, '{'). -manifestformat legacy
  writes the old format, for example to keep using other gogrepo versions.
- Safety: every JSON save is read back and compared with the data; if something would not come back exactly
  (tuples, non-text dict keys, NaN, ...) that save uses the old format and says so. The first JSON save over an
  old-format file keeps that file as \<file>.legacy (made once, never overwritten); if the copy fails the format is
  not switched. The usual \<file>.bak still holds the previous version and saves stay atomic. A damaged JSON file
  gives a message that points to the .bak instead of a traceback.
- The JSON loader does not have a limitation of the old loader, which misread { and } in game titles (and, in resume
  files, in changelogs).
- New command: export [-output FILE] [-savedir DIR] [-delimiter C] writes a CSV spreadsheet, one row per file
  (game, kind, file, operating system, language, version, size, md5, date); with -savedir an "on disk" column says
  yes / no / wrong size (sizes only, no checksums). UTF-8 with a byte order mark so Excel shows umlauts; the column
  separator is ';' for most languages and ',' for English, Japanese, Chinese, Korean, Thai and Hebrew.

DIFFERENCE: the manifest file has a different layout, and other gogrepo versions cannot read the JSON layout.

## Entry 14 - hashfile() closes the file it opens

Small fix found while testing: hashfile() (used by verify, import and trash) now closes the file it reads.

## Entry 13 - English fallback for the default language (requested)

- Problem: with the default language (say de) a game that has no German version gave you nothing at all.
- Now, when the language comes from the default (no -lang / -skiplang given) and is not English, English is the
  fallback: for every game, per list (standalone / galaxy / shared) and per operating system, the files in
  your language are used if there are any, otherwise the English ones. A game with German and English
  installers still gives only German. Example: German Windows installer + English-only Linux installer
  -> you get the German Windows file and the English Linux file. Languages other than German work the same
  (locale cn: Chinese where available, otherwise English).
- The fallback applies in all five commands (update, download, verify, import, backup) through
  filter_languages(), and in update it is decided on GOG's data (filter_downloads) before any file information
  is requested. It is stored in the resume file (key 'lang_fallback'; old resume files have none = strict).
- An explicit -lang (or -skiplang) is still taken literally: -lang de gives German only, -lang de en gives both.

DIFFERENCE: the default language list now picks up English files for games without your language. A normal
  update only re-fetches new and changed games, so run "update -full" once to give the games already in your
  manifest their English fallback. An update REPLACES what the manifest holds for every game it fetches, so
  English entries that were stored for a game that also has your language are dropped from the manifest
  (the files on disk stay).

Not handled: a language group that contains only a patch (no installer) counts as "has your language" for
  that system, so the English installer would not be chosen for it.

## Entry 12 - Default operating system and language (requested)

- Before: only "update" defaulted to this computer's OS and locale (detected by taking the first two letters of
  locale.getlocale(), which is often empty on Windows, so it quietly fell back to English); download, verify,
  import and backup defaulted to every operating system and every language.
- Now all five use apply_os_lang_defaults(). -os / -lang given: used as they are. Only -skipos / -skiplang
  given: every OS / language except those (as before; -os with -skipos and -lang with -skiplang are rejected by
  the parser, as before). Neither: this computer's OS and the user's language. The choice is logged
  ("no -os given, using ...") so it is visible what a default run does.
- OS: platform.system() (Darwin = mac). Language: locale.getlocale(), then the Windows display language, then
  locale.getdefaultlocale(); locale names are mapped to GOG's codes (ja -> jp, cs -> cz, zh -> cn / zh,
  pt_BR -> br, bg -> bl, ...). If detection fails or finds nothing GOG offers: windows / en.

DIFFERENCE: a plain download, verify, import or backup now handles one OS and one language instead of
  everything. A plain update stores only that OS and language for every game it fetches and REPLACES what the
  manifest held for that game, so entries for other languages / systems disappear from the manifest (the files
  on disk stay, but a later "clean" would treat them as orphans). Use -os / -lang (e.g. -lang en de) to keep them.

## Entry 11 - Lower CPU usage while downloading (reported: 5-10% of an 8-core CPU at only ~6 MB/s)

- The read loop (_download_ioloop) read 4 KB at a time and started a NEW THREAD (threading.Timer, the
  stall watchdog) for every chunk: ~1500 thread creations per second per download at 6 MB/s.
  _StallWatchdog now uses one timer thread per response and DOWNLOAD_CHUNK_SIZE is 64 KB.
  Measured on a local server (CPU of the downloading process only): 22 -> 1.5 CPU-ms per MB over HTTPS
  (21 -> 0.8 over plain HTTP). Most of what is left is TLS decryption.
  Same timeout rule as before: a download is cut off after HTTP_TIMEOUT seconds without data; time spent
  writing a chunk does not count.

DIFFERENCE: a piece of DOWNLOAD_CHUNK_SIZE must arrive within HTTP_TIMEOUT, so the slowest usable
  connection is about 1.1 KB/s (it was about 70 B/s). The timer thread is now a daemon thread, so it can
  no longer delay program exit after Ctrl-C. When a connection drops, the last incomplete piece (up to 64 KB,
  before: 4 KB) of that read is not written to the partial file; partial data is only ever reused in whole
  MD5-verified chunks and files without MD5 data restart from byte 0, so nothing of value is lost.

## Entry 10 - Update speed and interruption (changed after a real log showed the problem)

- cmd_update saved the manifest AND the resume manifest after every game in the default modes
  (-standard, -updateonly, -skipknown); only -full / -ids saved every RESUME_SAVE_THRESHOLD (50)
  games. A save re-formats the whole manifest with pprint (about 9 s on one real library) while
  fetching a game takes about 1 s, so most of a small update was spent saving. All modes now save
  every RESUME_SAVE_THRESHOLD games and once at the end.
  DIFFERENCE: if the process is killed hard (not Ctrl-C), up to 49 fetched games are lost and fetched
  again by the next run. Manifest and resume manifest are always saved as a pair, so resuming is safe.
- Ctrl-C during the fetch loop now saves the games fetched so far and re-raises (press Ctrl-C again to
  skip that save; the atomic save leaves the previous files intact).
- cmd_download now flushes the combined MD5 warnings when it finishes, like cmd_update. Before, they
  were only printed at interpreter exit, after the final "exiting..." line.

## Entry 9 - cmd_download split (it was one function of ~925 lines with nested closures)

cmd_download is now a short orchestrator. Helpers (all module level, shared state in _DownloadJob):
  _select_download_items, _index_items_by_title, _clean_work_dir, _process_download_item,
  _item_download_lists, _write_info_file (+_write_info_entries), _write_serial_file,
  _download_item_images (+_download_image_from_item_key/_keys), _queue_item_downloads,
  _download_worker, _prepare_download_file, _fit_partial_file, _preallocate,
  _download_with_chunk_verification, _download_without_chunk_verification, _download_ioloop,
  _report_progress, _finish_provisional_downloads, _remove_empty_subdirs.

Duplicated code was merged: the two !downloading / !provisional clean-up loops, the two
empty-folder loops, the three !info.txt item loops, and the three copies of the preallocation
logic (Windows CreateFileW and POSIX posix_fallocate; callers still differ only where the old code
did, e.g. the path used for the Windows file system lookup). Dead code removed: the unused
id->item dict, ~30 lines of commented-out code in the worker. The nested closures now take the
session/state as parameters. Log messages, their order per file, and file effects are unchanged.

DIFFERENCE: the Windows preallocation handle is always initialised to -1. Before, if CreateFileW
itself raised while growing a file that had just been moved from its final location, the error
handler failed with UnboundLocalError and that download thread died.

## Entry 8 - Small fixes

- path_preserving_split_ext now uses os.path.splitext: names without an extension no longer raise
  IndexError (moving an orphaned "README" onto an existing "README" used to crash) and a leading
  dot is not an extension (".hidden" -> ".hidden(1)" instead of "(1).hidden").
- numbered_name(): the "(n)" clash naming rule (incl. GOG's multi-part .bin sets) was copy-pasted in
  makeDeDuplicateName and move_with_increment_on_clash; both use it now. makeDeDuplicateName
  no longer raises ValueError for names without an extension.
- is_numeric_id() also catches TypeError (None and other non-strings return False).

DIFFERENCE: the crash cases above now work; dotfile clash names changed as described.

## Entry 7 - Combined MD5 warnings

- note_summarised() / flush_summarised(): repetitive per-file conditions are logged at DEBUG and
  reported once as a combined warning (end of cmd_update and cmd_download, and at exit as a safety net).
- request(..., quiet_statuses=(404,)): a 404 for an MD5 XML file is an expected answer and is no
  longer logged as a warning by request() (it is still raised and handled by the caller).
- md5_xml_url(): URL building split out of append_xml_extension_to_url_path so it is pure.

## Entry 6 - Atomic saves of the manifest, resume manifest, token and config

Atomic saves: atomic_write_text() (+ _replace_file, _fsync_directory) writes to \<file>.tmp,
flushes to disk and swaps it in with os.replace. Used for the manifest (previous version still
copied to .bak), resume manifest, token and config file. Before, a crash between "move to .bak"
and "move into place" could leave no manifest at all; permissions of an existing file are kept.

## Entry 5 - Logging

- Logger renamed 'ws' -> 'gogrepoc'. The log file now has date and level on every line
  (the console format is unchanged).
- Remaining print() calls that were messages now use logging: failed-download marker
  ("! path") is an error() line, Jython notice is error(), update_self() debug dumps are debug().
- Level corrections: verify findings (mismatched size/md5, zip test failed, missing file) and
  "failed - closing outstanding handle" are warnings; the three XML verification messages that
  end in "skipping" went from error to warning.

## Entry 4 - Bug fix: in cmd_import, setattr(entry, "old_updated", updated) used an undefined name

(NameError in a rarely used path); it is now None, like the line before it.

## Entry 3 - Python 2 support removed (Python 3.10+ is required, which the start-up check already enforced)

- Removed: __future__ imports, sys.version_info branches, compat_open (now plain open),
  universalLineEnd / storeExtend (argparse action 'extend'), u'' string prefixes, the Windows
  Python 2.7 long-path workarounds and the Python 2-only imports (dateutil, pytz, string, codecs).
- The "End Of Support for Python 2.7 and 3.8" warning in main() was unreachable (the start-up
  check exits first) and was removed. The start-up errors now go to stderr.

## Entry 2 - Login

- A password given on the command line still works but now logs a deprecation warning (it is
  visible in shell history and process lists). Without it the prompt uses
  getpass.getpass("Password: "), as before.

## Entry 1 - Command line

- GogArgumentParser: every legacy single-dash long option (-skipos, -dryrun, ...) is now also
  accepted GNU style (--skipos, --dryrun). The old spellings work exactly as before.
- add_common_flags(): -nolog / -debug were copy-pasted into all 10 sub-commands, now defined
  once (help typo "doesn't writes" fixed).
- validate_lang_and_os(): the language/os checks were extracted from process_argv, same messages.

## How the early refactoring was checked

How it was checked: the command line parser, atomic saves, combined warnings and the helper
functions have unit tests (tests/). cmd_download was compared with its pre-split version on 66
offline scenarios (local HTTP server with injected faults, fake Windows kernel32, macOS mode):
file tree, manifest, log lines, exceptions, HTTP requests and preallocation calls were identical in
65 (apart from the two combined MD5 notices that item 10 moved to the end of the download); the 66th
(CreateFileW raising) shows the DIFFERENCE above. 98% of cmd_download's statements are
executed by the scenarios; the rest is the unreachable code listed above. tests/download_rig/
contains the rig so any later change can be checked the same way.

Later changes were checked the same way and in addition with mutation checks (breaking the code on purpose to see that the tests notice) and,
where it applies, runs on a real manifest. `tests/README.md` lists what each test file covers.
