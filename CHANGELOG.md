# Changelog

All notable changes documented in `gogrepo_delta.py` are listed here. This changelog summarizes the implementation notes included with version **0.15.29**; it does not claim changes beyond those recorded in the source.

## [0.5.29] - 31.10.2026

### Added

- Updated the author credits to include eddie3 and kalaynr (the original projects), as well as MarS301 and claude.ai.

### Changed

- Chunk-verification downloads now wait for the configured retry delay between attempts, as the existing retry message indicated.
- A run that only needs to recover completed provisional files now handles those files without requiring another download to trigger the recovery process.
- The generated configuration file now explains that lists must be separated by commas, not spaces or semicolons. It also clarifies that section names and os and lang values must be lowercase, while option names may use any case.
- Updated the project URL shown by --help and the URL used by update_self() to point to the new repository: https://github.com/MarS301/gogrepo_delta.

### Fixed

-  Fixed a NameError when processing older manifests without api_downlink entries if the download URL contained signed parameters (wsSecret, wsTime, prefix).
-  The chunk-verification download loop now respects the configured http_retry_delay before retrying an incomplete chunk.
-  Completed files left behind by an interrupted run are now moved to their proper locations even when no additional downloads are needed.

### Compatibility and behaviour notes

- none

## [0.5.19] - 30.10.2026

### Added

- Added browser-based GOG authentication with `login --browser`, intended for CAPTCHA challenges or changes to GOG's automatic login page.
- Added an INI configuration file, `gogrepo_delta.cfg`, with `[settings]`, `[common]`, and per-command defaults.
- Added the `list` command for searching the manifest by game ID, title, or name.
- Added the `export` command to write manifest contents to CSV, including optional on-disk status.
- Added JSON manifest and resume-manifest output, with legacy-format reading and a `--manifestformat legacy` compatibility option.
- Added manifest recovery prompts that can restore a valid `.bak` file instead of silently starting with an empty library.
- Added end-of-run summaries and failure-sensitive exit codes.
- Added default OS/language detection and English fallback for the automatically detected language.
- Added combined reporting for repetitive MD5-related warnings.

### Changed

- Refactored command-line parsing so legacy single-dash long options and GNU-style double-dash options are both accepted.
- Removed Python 2 compatibility code; Python 3.10 or newer is required.
- Centralized common logging flags and extracted OS/language validation.
- Changed password handling to use a secure prompt when the password is omitted; command-line passwords now produce a deprecation warning.
- Renamed the application and User-Agent to `gogrepo_delta` / `GOGRepoDelta/0.15.19` while retaining existing library filenames.
- Changed manifests to indented JSON by default, with read-back validation, atomic replacement, and preservation of the previous/legacy versions.
- Changed update persistence to save manifest/resume state in batches and at completion rather than after every game.
- Increased download read chunks to 64 KB and replaced per-chunk watchdog timer creation with one timer thread per response to reduce CPU overhead.
- Reworked download processing into module-level helper functions while preserving intended file effects and log ordering.
- Updated default OS/language selection across update, download, verify, import, and backup.
- Improved configuration-file generation: shared defaults are placed in `[common]` where appropriate, and generated comments are shorter and grouped.
- Added safer handling of interrupted update fetches and flushes combined MD5 warnings before command completion.

### Fixed

- Fixed an undefined variable in a rarely used import path.
- Fixed filename de-duplication for files without extensions and dotfiles.
- Fixed numeric-ID checks for non-string values.
- Fixed a file-handle leak in `hashfile()`.
- Fixed Windows scheduled-task detection when standard input is connected to `NUL`.
- Improved handling of Unicode output redirected on Windows by escaping characters unsupported by the active console code page.
- Improved login CAPTCHA detection and handling of rejected/expired login codes.
- Fixed download preallocation error handling so a failed Windows file-handle creation does not kill a download worker.
- Improved handling of unreadable, missing, or damaged manifests and made non-interactive recovery fail safely.

### Compatibility and behaviour notes

- The first run creates `gogrepo_delta.cfg`; the generated defaults preserve the built-in behaviour.
- A plain update/download/verify/import/backup now defaults to the detected OS and language rather than all variants. Specify `--os` and `--lang` to retain/select additional variants.
- Automatic English fallback applies only when language selection is implicit. Explicit `--lang` or `--skiplang` selection is literal.
- JSON manifest layout is not readable by older gogrepoc versions. Use `--manifestformat legacy` when compatibility with older versions is required.
- Hard termination during an update can require re-fetching up to 49 games since the last batch save.
- Download reads use 64 KB chunks; very slow connections that cannot deliver a chunk within the configured HTTP timeout may be interrupted.
- Verification now returns exit status `1` when it finds problems, including missing files.
- A failed login now returns exit status `1`.

### Source notes

The source documents the above work as an incremental refactoring of `gogrepoc.py`, with the intention of preserving behaviour except where a difference is explicitly noted. Real GOG downloads and authentication were not fully verified as part of the source's own notes.
