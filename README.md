<div align="center">

# gogrepo_delta

**Build and maintain your own offline copy of your GOG.com game library.**

A community-maintained Python tool for cataloguing, downloading, verifying, importing,
backing up, and organizing GOG installers and bonus content.

[![Version](https://img.shields.io/badge/version-0.5.90-blue)](https://github.com/MarS301/gogrepo_delta)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green)](LICENSE.md)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#requirements-and-installation)

</div>

`gogrepo_delta.py` is a standalone continuation and refactoring of
[gogrepoc](https://github.com/kalanyr/gogrepoc). It keeps a local manifest of your GOG
library and helps you maintain a dependable, verifiable local collection.

> [!IMPORTANT]
> This is an independent community project. It is not affiliated with, endorsed by, or
> supported by GOG.

> [!WARNING]
> **New token storage.** New logins save credentials in `gog-token.json`, encrypted by default with a
> password you choose. Encrypted mode uses the third-party `cryptography` package
> (`python -m pip install cryptography`; the binaries contain it). The password is requested once per process and is never stored.
>
> - **`cryptography` not installed:** the program saves the token as readable JSON with **no encryption** and
>   prints a warning (once per run) that names the package to install. It never replaces an existing encrypted
>   `gog-token.json` (or one it cannot read) by a plain-text file: it stops with a message instead. If you set
>   the environment variable `GOGREPO_TOKEN_MODE=encrypted` yourself it does not fall back either, it stops
>   (`token_mode = encrypted` in the config file is the default and does fall back, with the warning). After you install the
>   package, the next save of a plain-text token asks you to create a password and encrypts the file.
> - **Unattended machines:** set `token_mode = plain` in the `[settings]` section of `gogrepo_delta.cfg` (or the
>   environment variable `GOGREPO_TOKEN_MODE=plain`, which wins over the file when it is set). This stores the
>   token as readable JSON and provides **no encryption**. The setting only decides how the file is written: an
>   existing token file is read as it is, but the next time the token is saved (after a refresh or a login) an
>   encrypted file is replaced by readable plain text, and a warning says so. Keep in mind that a config file is easy to copy, sync or commit together with the other files.
> - **Existing `gog-token.dat` files** are read only when `gog-token.json` is absent. Their contents are
>   migrated to the new file; the legacy file is never modified or deleted.
> - **Damaged file or wrong password:** the program reports the problem rather than silently using an
>   older token. At a terminal a wrong or empty password is asked for again (3 attempts); in a scheduled
>   task or a pipe there is one attempt. If the password is forgotten, delete `gog-token.json` and run `login` again.

## Project at a glance

| | |
| --- | --- |
| **Current version** | `v0.5.90` |
| **Python requirement** | Python 3.10 or newer (3.8 and 3.9 start with a warning; best effort: a CI job tries both and is allowed to fail) |
| **License** | GPL-3.0-or-later |
| **Main script** | `gogrepo_delta.py` |
| **Upstream project** | [kalanyr/gogrepoc](https://github.com/kalanyr/gogrepoc) |

## Table of contents

- [Features](#features)
- [Requirements and installation](#requirements-and-installation)
  - [Binaries (no Python needed)](#binaries-no-python-needed)
  - [Required dependencies](#required-dependencies)
  - [Optional dependencies](#optional-dependencies)
  - [Verifying a download](#verifying-a-download)
- [Quick start](#quick-start)
  - [1. Sign in to GOG](#1-sign-in-to-gog)
  - [2. Update the manifest](#2-update-the-manifest)
  - [3. Download games and extras](#3-download-games-and-extras)
  - [4. Verify your collection](#4-verify-your-collection)
  - [5. Keep the collection up to date](#5-keep-the-collection-up-to-date)
- [Commands](#commands)
  - [login](#login)
  - [update](#update)
  - [Movies](#movies)
  - [download](#download)
  - [verify](#verify)
  - [import](#import)
  - [backup](#backup)
  - [list](#list)
  - [export](#export)
  - [wishlist](#wishlist)
  - [clean](#clean)
  - [clear_partial_downloads and trash (deprecated)](#clear_partial_downloads-and-trash-deprecated)
  - [selfupdate](#selfupdate)
  - [diagnostics](#diagnostics)
- [Selecting games by tag](#selecting-games-by-tag)
- [Operating system and language selection](#operating-system-and-language-selection)
- [Configuration](#configuration)
- [Files and data safety](#files-and-data-safety)
  - [Manifest format and recovery](#manifest-format-and-recovery)
- [Logging and exit codes](#logging-and-exit-codes)
- [Troubleshooting](#troubleshooting)
- [Credits and links](#credits-and-links)
- [Changelog](#changelog)

## Features

- Download GOG game installers, Galaxy installers, shared installers, and bonus content.
- Select games by ID or title, operating system, and language.
- Detect the computer's operating system and language automatically.
- Use English as a fallback when the detected language is unavailable (unless language selection is explicitly supplied).
- Resume interrupted downloads using verified chunks where checksum data is available.
- Retry incomplete chunk downloads using the configured retry count and delay.
- Recover fully downloaded provisional files left behind by an interrupted run, even when no new downloads are needed.
- Verify file sizes, MD5 checksums, and ZIP archive integrity.
- Import existing collections by matching MD5 checksums.
- Create incremental backups.
- Move files not represented in the manifest into an orphaned area, and optionally remove duplicates or obsolete files.
- Download cover and background artwork.
- Store game information, serial numbers, and available changelogs alongside the collection.
- Export the manifest to a spreadsheet-friendly CSV file.
- Save your GOG wishlist (with optional prices) and see what changed since the last run.
- Search and list games in the manifest.
- Configure command defaults, network behaviour, logging, and download performance.
- Write manifests safely using atomic file replacement and keep backup copies.
- Produce end-of-run summaries and meaningful exit codes for automation.

## Requirements and installation

### Binaries (no Python needed)

The ready-made binaries on the [Releases page](https://github.com/MarS301/gogrepo_delta/releases) are for people who do not want to install Python and the packages listed below. Each one is a single program file that already contains Python and all dependencies, the optional ones included (`cryptography`, `html2text`, `blake3` and, on macOS, PyObjC). There is one archive per platform: Windows x64 (`.zip`), Linux x64 and arm64 and macOS Intel (x64) and Apple Silicon (arm64) (all `.tar.gz`). Unpack it and run `gogrepo_delta` (`gogrepo_delta.exe` on Windows) wherever this README says `python gogrepo_delta.py`, for example `gogrepo_delta --help`; the commands and options are the same.

The binaries are not code-signed, so your operating system may show a warning the first time you start one. [Verify the download](#verifying-a-download) before you run it. If you prefer to run `gogrepo_delta.py` with Python, or want to read or change the code, follow the rest of this section.

### Required dependencies

- Python **3.10 or newer** (3.8 / 3.9: starts with a warning, best effort; a CI job tries both and is allowed to fail)
- `html5lib`
- `requests`
- `psutil`

Install the required packages, plus `cryptography`, which is optional but strongly recommended (see below):

```bash
python -m pip install html5lib requests psutil cryptography
```

The repository lists the same packages in files, so that you do not have to type them: `python -m pip install -r requirements.txt` installs the required packages, and `python -m pip install -r requirements-optional.txt` all the optional ones (`cryptography`, `blake3`, `html2text` and, on macOS, PyObjC).

Download `gogrepo_delta.py` into a working directory and run it with Python:

```bash
python gogrepo_delta.py --help
```

The script must be started with a Python interpreter; do not execute it as a shell script.

### Optional dependencies

- `cryptography`: **strongly recommended.** It encrypts the saved login token (`gog-token.json`) with a password you choose. Without it the program still works, but it saves the token as readable plain text and says so in a warning (once per run). It is not needed with `GOGREPO_TOKEN_MODE=plain`.

  ```bash
  python -m pip install cryptography
  ```

- **macOS:** `pyobjc-framework-Cocoa` (PyObjC; it provides CoreFoundation, which the program uses to keep the Mac awake during long runs). It is optional: without it the program still starts, prints one warning and does not keep the computer awake, so a long `update` or `download` can be interrupted by sleep. The ready-made macOS binaries contain it; when you run the script with Python it is worth installing:

  ```bash
  python -m pip install pyobjc-framework-Cocoa
  ```

- `html2text` (2015.6.21 or newer): converts downloaded GOG changelogs from HTML to readable text.

  ```bash
  python -m pip install html2text
  ```

- `blake3`: enables BLAKE3 checksums for `download` and `verify` (see [BLAKE3 checksums](#blake3-checksums)). Without it everything works as before, using MD5 only.

  ```bash
  python -m pip install blake3
  ```

- **Linux/Unix:** PyQt5 with QtDBus support can be used for desktop-session sleep inhibition where supported.
- **Windows:** required Windows API calls use Python's built-in `ctypes` module.

### Verifying a download

From the release that follows this change on, every release on GitHub carries the program binaries for each platform, `gogrepo_delta.py` itself and a file `SHA256SUMS` that lists the SHA-256 checksum of each of them. Every one of these files also has a signed build attestation from GitHub. Check what you downloaded before you run it, because the program holds your GOG login:

1. **Checksum** (finds a damaged or incomplete download). Put `SHA256SUMS` next to the files and run, on Linux:

   ```bash
   sha256sum -c SHA256SUMS --ignore-missing
   ```

   On macOS use `shasum -a 256 -c SHA256SUMS` (it complains about the files you did not download; that is fine). On Windows PowerShell, `Get-FileHash .\gogrepo_delta-<version>-win-x64.zip -Algorithm SHA256` shows the value to compare with the line in `SHA256SUMS`.
2. **Attestation** (shows that the file was built by this repository's release workflow and was not replaced afterwards). With the [GitHub CLI](https://cli.github.com/):

   ```bash
   gh attestation verify gogrepo_delta-<version>-linux-x64.tar.gz --repo MarS301/gogrepo_delta
   ```

What this does and does not protect against: `SHA256SUMS` lies next to the files on the same page, so on its own it only proves that the download is intact. The attestation is what ties a file to the repository's workflow. Neither tells you that the repository itself is free of bad changes; they only make a silently swapped file visible. Older releases have neither.

## Quick start

Run the commands below from the directory in which you want the program's working files (manifest, token, log, and configuration) to live. The game files themselves can be stored elsewhere.

### 1. Sign in to GOG

```bash
python gogrepo_delta.py login
```

Enter your GOG username/email when prompted. If the password is not supplied as an argument, it is requested securely. If the `cryptography` package is installed you will then be asked to create a password that protects the saved token; without it the token is saved as plain text (see the notice above).

If automatic login is blocked by a CAPTCHA or a changed GOG login page, use browser login:

```bash
python gogrepo_delta.py login --browser
```

A browser sign-in page is opened (or its address is displayed). Sign in, then paste the resulting URL when prompted. The authentication token is stored locally in `gog-token.json`.

**Security:** Do not pass your password on the command line. Command-line passwords can be exposed through shell history and process listings; this form is deprecated.

### 2. Update the manifest

```bash
python gogrepo_delta.py update
```

This retrieves library information from GOG and updates `gog-manifest.dat`. The standard update checks new and updated games. The default operating system and language are detected from the current computer.

### 3. Download games and extras

```bash
python gogrepo_delta.py download
```

Downloads the files selected by the manifest and the current OS/language defaults. To use a different destination:

```bash
python gogrepo_delta.py download "/path/to/GOG games"
```

### 4. Verify your collection

```bash
python gogrepo_delta.py verify
```

The verifier checks file sizes, MD5 checksums, and ZIP integrity. By default, files that fail verification are cleaned out of the collection (not silently treated as valid).

### 5. Keep the collection up to date

Run these commands periodically:

```bash
python gogrepo_delta.py update
python gogrepo_delta.py download
python gogrepo_delta.py verify
```

Updates and downloads are incremental. Interrupted downloads can be resumed where sufficient verified data is available. If a run is interrupted after a file has finished downloading but before it is moved out of `!downloading/!provisional`, the next run recovers that completed file even if there are no other downloads to perform.

## Commands

Every command supports `-h` or `--help`. Both the original single-dash long options (`-skipos`) and GNU-style double-dash options (`--skipos`) are accepted.

| Command | Purpose |
| --- | --- |
| `login` | Authenticate with GOG and save a local token. |
| `update` | Fetch library metadata and update the manifest. |
| `download` | Download installers and extras listed in the manifest. |
| `verify` | Check downloaded files against manifest data. |
| `import` | Import existing files by matching MD5 checksums. |
| `backup` | Create an incremental copy of a collection. |
| `list` | List or search games in the manifest. |
| `export` | Export manifest entries to CSV. |
| `wishlist` | Save the GOG wishlist and show what changed since the last run. |
| `clean` | Move files unknown to the manifest into `!orphaned`; with switches also remove unfinished downloads (`--partials`, `--provisional`) or permanently delete from `!orphaned` (`--trash`). |
| `clear_partial_downloads` | Deprecated: use `clean --partials`. |
| `trash` | Deprecated: use `clean --trash`. |
| `selfupdate` | Check on GitHub whether a newer release exists (looks only, installs nothing). |
| `diagnostics` | Generate diagnostic information for troubleshooting. |

### `login`

```bash
python gogrepo_delta.py login
python gogrepo_delta.py login --browser
```

Options:
- `username` (optional): GOG username or email.
- `password` (optional, deprecated): avoid supplying this; otherwise it may be exposed in shell history and process listings.
- `--browser`: use browser-based sign-in. Username and password arguments are ignored with a warning.

### `update`

```bash
python gogrepo_delta.py update
python gogrepo_delta.py update --full
python gogrepo_delta.py update --ids game_id another_game_id
```

Useful options:
- `--standard`: update new and updated games (default unless `--ids` is used).
- `--skipknown`: only update games not already in the manifest.
- `--updateonly`: only update games GOG marks as updated.
- `--full`: update all games in the account.
- `--ids ID ...` / `--skipids ID ...`: include or exclude selected games.
- `--tags TAG ...` / `--skiptags TAG ...` / `--notags`: include or exclude games by the tags of your GOG library, or take only the games without any tag (see [Selecting games by tag](#selecting-games-by-tag)).
- `--os OS ...` / `--skipos OS ...`: select or exclude operating systems.
- `--lang LANG ...` / `--skiplang LANG ...`: select or exclude languages.
- `--skiphidden`: skip games marked as hidden.
- `--resumemode {noresume,resume,onlyresume}`: control update resuming (default: `resume`).
  A game whose details cannot be fetched (a network problem, bad data) is kept in the resume manifest and tried again by the next
  updates, which come before the update you asked for. After `resume_retry_count` retries (config file, default 3) it is given up, so that it no
  longer holds back your updates; every update that includes it still tries it once and reports the failure (exit status 1) until it works.
  A resume file that is missing means "nothing to resume". One that exists but cannot be read or understood (cut off, not text, wrong content, no
  permission) stops `update` with a message and exit status 1, before anything is fetched or changed, and it is never taken for "nothing to resume". It
  only remembers which games of an unfinished update are still to be fetched, so you can delete it (the next update then starts without it) or, if there
  is one, copy `gog-resume-manifest.dat.bak` over it. This also applies with `--resumemode noresume`. A resume file of an incompatible version asks what to do
  (discard or abort); without a terminal (a scheduled task) it stops with a message instead.
- `--strictverify`: clear a previous verified state unless the MD5 matches.
- `--strictdupe`: use stricter duplicate matching when MD5 data is missing.
- `--lenientdownloadsupdate`: do not mark installers for update solely because their update timestamp changed when MD5 data is unavailable or differs.
- `--strictextrasupdate`: mark extras for update when their timestamps change, even if name and size match.
- `--md5xmls`: download available MD5 XML files.
- `--nochangelogs`: do not save game changelogs.
- `--diagnostic`: perform more exhaustive GOG data checks (slower and more verbose).
- `--wait HOURS`: wait before starting.
- `--installers {standalone,both}`: legacy installer selection option (deprecated).
- `--movies`: also put your GOG movies into the manifest (see [Movies](#movies)). Off by default.
- `--moviequality LIST`: which video variants of a movie to take (default `best`; see [Movies](#movies)).

### Movies

GOG's movies (documentaries, concerts, "making of" films that you own) are not part of the default `update`, because a single movie can be many gigabytes. Switch them on with `--movies` (or `movies = true` in the `[update]` section of the config file); everything else (`download`, `verify`, `backup`, `clean`, `list`, `export`) then treats them like any other item of the manifest.

```bash
python gogrepo_delta.py update --movies
python gogrepo_delta.py update --movies --moviequality 1080p,720p
python gogrepo_delta.py list --format table
```

- **Folders.** A movie gets the folder `<name>-movie` next to the game folders (`deliverance_the_making_of_kingdom_come-movie`), so that movies are easy to tell apart. The file names are the ones GOG's server gives (`deliverance_making_of_kingdom_come_1080p.mp4`).
- **Which video variants.** A movie is offered in several qualities (720p, 1080p, 4K, dvd, 576p, ...). `--moviequality` takes `best` (the default: the highest resolution), `all`, one quality (`1080p`), `max:<quality>` (the best that is not above it, for example `max:1080p`) or a list in the order of preference (`1080p,720p`: the first that the movie offers). If the movie offers none of the listed qualities the best one is taken, so a movie is never left without its video. The subtitles that come with a movie are always taken, and its extras follow `--skipextras` like those of a game.
- **Language.** A movie is taken in the wanted languages; if it is not offered in any of them, in English, and if it has no English either, in the language it has.
- **No operating system.** Movies are not chosen by `--os`; `--os linux` still takes them.
- **Update without `--movies`.** The movies already in the manifest are left exactly as they are (they are not removed and `clean` does not touch their folders). They are removed only by an update with `--movies` when they are no longer in your library.
- **Checking.** A movie file is checked by its size (GOG publishes no checksum for video files), like the extras.

### `download`

```bash
python gogrepo_delta.py download
python gogrepo_delta.py download "/path/to/GOG games" --dryrun
python gogrepo_delta.py download --ids game_id
```

Useful options:
- `--dryrun`: show what would be downloaded without downloading.
- `--ids ID ...` / `--skipids ID ...`: include or exclude games.
- `--tags TAG ...` / `--skiptags TAG ...` / `--notags`: include or exclude games by tag, or take only the games without any tag.
- `--os OS ...` / `--skipos OS ...`: select or exclude operating systems.
- `--lang LANG ...` / `--skiplang LANG ...`: select or exclude languages.
- `--skipextras`: skip bonus content.
- `--skipgames`: skip game installers (deprecated).
- `--skipgalaxy`, `--skipstandalone`, `--skipshared`: skip the respective installer groups (legacy/deprecated options).
- `--skipfiles FILE ...`: skip filenames or glob patterns.
- `--covers`: download cover images.
- `--backgrounds`: download background images.
- `--nocleanimages`: delete old artwork instead of cleaning it up.
- `--downloadlimit MB`: approximate download limit in megabytes.
- `--skippreallocation`: do not preallocate disk space.
- `--wait HOURS`: wait before starting.

**Portable file names.** So that a library can be copied between Linux, Windows and macOS, `update` stores every file name in a portable form: a path separator, one of `< > : " | ? *` or a control character becomes `_`, a trailing space or dot is dropped, a Windows device name such as `CON` gets a `_` in front, and a name longer than 251 bytes is shortened to 240 bytes (start, `~`, a short hash, extension). When that changes a name, the manifest entry keeps the original in `name_from_server`. `update` also gives the names already in your manifest this form; the files on disk are renamed by the next `download`, `verify` or `clean`. `download`, `verify`, `backup` and `import` do not use a name that is still not portable (a manifest that `update` has not migrated yet): the file gets a warning line and an entry in the end summary, the run ends with exit status 1, and the rest continues.

### `verify`

```bash
python gogrepo_delta.py verify
python gogrepo_delta.py verify "/path/to/GOG games" --forceverify
```

Useful options:
- `--forceverify`: also verify files unchanged since their last successful verification.
- `--skipmd5`, `--skipsize`, `--skipzip`: skip the corresponding check.
- `--noblake3`: do not record or compare BLAKE3 checksums (see below). Also accepted by `download`.
- `--delete`: permanently delete files that fail integrity checks.
- `--noclean`: leave files that fail integrity checks in place.
- `--clean`: deprecated; cleaning is already the default.
- `--ids ID ...` / `--skipids ID ...`: include or exclude games.
- `--tags TAG ...` / `--skiptags TAG ...` / `--notags`: include or exclude games by tag, or take only the games without any tag.
- `--os OS ...` / `--skipos OS ...`: select or exclude operating systems.
- `--lang LANG ...` / `--skiplang LANG ...`: select or exclude languages.
- `--skipfiles FILE ...`: skip filenames or glob patterns.
- `--skipextras`, `--skipgames`, `--skipgalaxy`, `--skipstandalone`, `--skipshared`: limit the file types checked.
- `--highmemory`: use memory for multipart ZIP testing; at least 50 GB of available memory is recommended.
- `--lowtmpspace`: skip multipart ZIP tests when temporary disk space is insufficient.

**Exit status:** `verify` returns `1` if it finds any problem, including missing files.

#### BLAKE3 checksums

GOG publishes only MD5 checksums, so BLAKE3 cannot be compared with anything from GOG. Instead it is a **local fingerprint** kept in the manifest (field `blake3`), which needs the optional `blake3` package:

- **`download` records it right after a file has arrived** (v0.5.42). The file is hashed once, in its download thread, and kept only if its content is confirmed (see below). `verify` then needs no first pass for it. A file you already had, or one downloaded without the package, gets its BLAKE3 the first time it passes `verify` ("trust on first verify"); both hashes are computed in the same read pass.
- A later full check (`verify --forceverify`) compares only the recorded BLAKE3, which detects any change since the file last passed (for example bit rot) and is faster on fast disks. If the BLAKE3 differs and the MD5 is known, the MD5 decides: a mismatch is reported, a match means the stored BLAKE3 was stale and is refreshed.
- Files verified with an older version have no recorded BLAKE3 yet: run `verify --forceverify` once to record them.
- A BLAKE3 is recorded only for content that was actually confirmed (MD5 match, or for file types without MD5 a known size that matched). `--skipmd5` records nothing for files that have an MD5. After a download, a file whose MD5 in the manifest does not match what arrived gets no BLAKE3 and a warning (the download is kept; `verify` will report it). A file that is downloaded again because it changed never keeps the BLAKE3 of its old content.
- Use `--noblake3` (or `noblake3 = true` under `[download]` / `[verify]` in the config file) to switch the feature off. Without the package, `download` and `verify` say so once and behave as before. A `download --dryrun` hashes nothing.

### `import`

```bash
python gogrepo_delta.py import "/old/GOG collection" "/new/GOG collection"
```

Files are imported only when their MD5 checksums match manifest entries.

Options include `--ids ID ...`, `--skipids ID ...`, `--tags TAG ...`, `--skiptags TAG ...`, `--notags`, `--os OS ...`, `--skipos OS ...`, `--lang LANG ...`, `--skiplang LANG ...`, `--skipgalaxy`, `--skipstandalone`, and `--skipshared`.

### `backup`

```bash
python gogrepo_delta.py backup "/path/to/source" "/path/to/backup"
```

Creates an incremental backup by copying known files from the source collection to the destination.

Options include `--ids ID ...`, `--skipids ID ...`, `--tags TAG ...`, `--skiptags TAG ...`, `--notags`, `--os OS ...`, `--skipos OS ...`, `--lang LANG ...`, `--skiplang LANG ...`, `--skipextras`, `--skipgames`, `--skipgalaxy`, `--skipstandalone`, and `--skipshared`.

### `list`

```bash
python gogrepo_delta.py list
python gogrepo_delta.py list witcher
python gogrepo_delta.py list --format ids
python gogrepo_delta.py list --tags Movies
```

Search terms are matched against game IDs, titles, and names; all supplied words must match, in any order. Put search words before options. The `MEDIA` column says `game` or `movie`; the files of a movie are listed with the operating system `vid`.

- `--format table`: readable table output (default).
- `--format ids`: one game title/ID per line for use in scripts.
- `--os OS ...`, `--skipos OS ...`, `--lang LANG ...`, `--skiplang LANG ...`: filter the listed games. By default `list` shows all systems and languages (it does not use the computer's defaults), but values from the config file apply. The files of a movie belong to every operating system, so `--os` never hides a movie (`--lang` still applies). These filters decide about installers: a game that has no installer at all (only extras, which belong to no system or language, or no files) is always listed, with `-` in OS and LANG; a game whose installers do not fit is hidden.
- `--tags TAG ...` / `--skiptags TAG ...` / `--notags`: list only the games (and movies) with one of the tags of your GOG library, or leave those out, or only those without any tag (see [Selecting games by tag](#selecting-games-by-tag)). Tag your movies on GOG, run `update` once, and `list --tags Movies` shows only the movies. The table has no tags column, because an item can have several tags.

If nothing is found, `list` says why and exits with `1`: either no game matches the words (with suggestions), or games match but none has files for the chosen operating system / language (the message names the games and the filter in use, which may come from the config file).

### `export`

```bash
python gogrepo_delta.py export
python gogrepo_delta.py export --output my-library.csv
python gogrepo_delta.py export --savedir "/path/to/GOG games"
```

Exports one CSV row per manifest file. If the CSV file is open in another program (Excel keeps a file it has open locked) `export` says so before it does anything and changes nothing; close the file and run it again. The spreadsheet includes game ID/title, a `media` column (`game` or `movie`), folder, file type, filename, OS, language, version, size, MD5, and the update date and the update time (UTC) in two columns, so that Excel and other spreadsheet programs show them in the format of your computer's language (the cells hold `2026-06-23` and `16:59:00`, forms every spreadsheet understands). `--savedir DIR` adds an on-disk status column.

- `--output FILE`: output path (default: `gog-library.csv`).
- `--delimiter CHAR`: set the CSV separator. By default, the separator is selected for common spreadsheet locale conventions.

The CSV is UTF-8 with a byte-order mark (BOM) to improve compatibility with spreadsheet applications.

### `wishlist`

```bash
python gogrepo_delta.py wishlist
python gogrepo_delta.py wishlist --prices --country DE
python gogrepo_delta.py wishlist --prices --country DE --currency EUR --csv wishlist.csv
python gogrepo_delta.py wishlist --prices --country DE --csv        # writes gog-wishlist.csv
```

Saves the games on your GOG wishlist to `gog-wishlist.json` and says what changed since the last run: games that were added, games that were removed (marked "now in your library" if they are in the manifest), and, with `--prices`, games that became cheaper or dearer. **Nothing is downloaded**: GOG only provides installers for games you own.

The title, release date and store link of a game are fetched once and kept in the file, so later runs only ask GOG about new games. Requires `login` (the wishlist belongs to your account).

- `--prices`: also fetch the price of every game (one more request per game). Games without a price in the store (delisted, unreleased, not sold in that country) simply have none.
- `--country CODE`: the two-letter country the prices are for, like `DE`, `GB` or `US` (default: `US`). `UK` is taken as `GB`. If GOG refuses (HTTP 400) the price of a single game, that game is named in a warning with GOG's own message (for example `Product 1293804420 not found`), keeps the price that was known, and the other games go on; the run still ends normally. Only when GOG refuses the first three price requests and has answered none, the country is blamed (one error, and the price requests stop); if it refuses every request of a wishlist with fewer than three games, you get a warning and exit status 1.
- `--currency CODE`: GOG gives one price per currency for a country (for example EUR and USD for `DE`); by default the first one is used.
- `--output FILE`: where to save the wishlist and what the next run compares with (default: `gog-wishlist.json`).
- `--csv [FILE]`: also write a spreadsheet (without a file name: `gog-wishlist.csv`) with title, release date (always as `2026-11-05`), store link, "in library", regular price, price, discount and promotion. `--delimiter CHAR` works as for `export`; with `;` the prices use decimal commas. The date is ISO on purpose: a spreadsheet reads a date in the order of your computer's language (`11/05/2026` becomes 11 May on a German Excel, and `06/23/2026` stays text), while `2026-11-05` is understood everywhere and then shown the local way.

If the CSV file is open in another program (on Windows, Excel locks it), the command says so before it fetches anything ("please close it and run the command again") and fails with exit status `1`; the CSV is written before the saved list is updated, so a later run still reports the changes.

The wishlist and price addresses are not officially documented by GOG and could change; if GOG answers with something unexpected, the command says so and fails with exit status `1`. Prices are rounded to what GOG reports in cents.

### `clean`

```bash
python gogrepo_delta.py clean "/path/to/GOG games" --dryrun
```

One command for all clean-up of the games folder. Without a stage switch it moves files and folders that are not in the manifest into the `!orphaned` directory, exactly as before. The switches below select the other stages; each stage only runs when asked for, and they run in this order. `--dryrun` applies to every stage and shows what would be done.

| Switch | Stage |
|---|---|
| `--partials` | Permanently deletes the unfinished downloads in `!downloading` (not the finished files in `!downloading/!provisional`). |
| `--provisional` | Permanently deletes the finished files that wait in `!downloading/!provisional`. The next `download` would move them into place; after this switch it fetches them again. |
| `--orphans` | Moves files and folders that are not in the manifest to `!orphaned` (the default when no other stage is given). The only stage that reads the manifest. |
| `--trash` | Permanently deletes from `!orphaned`. By default only strict duplicates of known game files (same size and MD5). |

Options for `--trash` (they are refused without it):
- `--installers`: also delete installer file types even when they are not duplicates.
- `--folders`: also delete orphaned game folders when a corresponding game folder exists.
- `--images`: also delete orphaned `!images` directories when a corresponding images directory exists.
- `--relaxed`: relax duplicate checks and deletion requirements; use with care.

`--trash --all` deletes **everything** in `!orphaned`: loose files, folders and subfolders, duplicates or not (the `!orphaned` folder itself stays). It cannot be combined with `--installers`, `--images`, `--folders` or `--relaxed`, which it makes unnecessary. Before it deletes anything it lists what it found: the number of items and files, the total size, and each top-level item with its size (the first 20), and under each folder what is inside it: files with their size, subfolders as `name\ (N files, size)`, at most 20 entries per folder and 200 lines in all (the rest is counted: `... and N more items`). Then:

- **At a terminal** it asks `Delete all N items (size) from '!orphaned' for good? [y/N]`. Only `y`, `yes`, `j` or `ja` (any case) go ahead; Enter, any other answer and a closed input mean no, and nothing is deleted.
- **Without a terminal** (a scheduled task, a pipe) there is nobody to ask, so it refuses with an error and exit status 1 and deletes nothing, unless you add `--yes`. `--yes` skips the question and can only be used together with `--trash --all`. Use it on the command line of the unattended job; leave it out of the config file if you also run the program by hand.
- **With `--dryrun`** it shows the full list, without any limit: every top-level item and every file below each folder with its path and size (empty folders as `(empty)`). It never asks and deletes nothing. The output can be long (a `.git` folder has thousands of files); redirect it to a file if you want to read it in peace.

The same listing is printed when `--folders` or `--images` delete a whole folder: the line `Deleting <folder>` is followed by what was in it (in a dry run all of it, otherwise capped as above).

Read-only files and folders (Git, for example, makes its objects read-only, and Windows refuses to delete such files) no longer stop a deletion; this applies to `--partials`, `--provisional` and all of `--trash`.

Every stage says what it looked at, so a run that deleted nothing says why: `--partials` names the number of unfinished downloads it found or tells you that `!downloading` has no game folders (loose files directly in it are mentioned as not touched); `--provisional` says how many items it deleted or that nothing is waiting; plain `--trash` reports how many folders it looked at, how many duplicates it deleted and what it kept (files without a same-named partner in the game folder, files whose size or content differs, folders without a game folder of that name, subfolders and loose files it does not look at) and points to `--all`. The messages of a dry run say "would be deleted".

Give `clean` the library folder, the one that contains all the game folders, not the folder of one game. If the folder you give looks like a single game's folder (its name is a game folder of the manifest, or it holds an installer or extra of a game and no game folders), `clean` stops with a message before it changes anything and tells you which folder to use. `clean` also stops if there is no manifest that lists games: the manifest `gog-manifest.dat` is read from the current folder, so run `clean` from the folder that holds it (or run `update` first). Both checks are part of the `--orphans` stage, which is the only one that reads the manifest.

`--orphans` and `--trash` cannot be used in the same run: first move the files (`clean`), look into `!orphaned`, then run `clean --trash` as a separate step. Examples:

```bash
python gogrepo_delta.py clean "/path/to/GOG games" --partials --dryrun
python gogrepo_delta.py clean "/path/to/GOG games" --trash --folders --dryrun
```

**Warning:** `--partials`, `--provisional` and `--trash` permanently delete files. Always run them with `--dryrun` first and inspect the output.

### `clear_partial_downloads` and `trash` (deprecated)

`clear_partial_downloads` and `trash` still work and take the same options as before, but print a warning and will be removed in a later version. Use `clean --partials` instead of `clear_partial_downloads`, and `clean --trash` (with `--installers`, `--images`, `--folders`, `--relaxed`, and `--installersonly` as `--installers`) instead of `trash`.

### `selfupdate`

```bash
python gogrepo_delta.py selfupdate
```

Checks on GitHub whether a newer release of this program exists and tells you its version and the address of its release page. **It only looks.** Nothing is downloaded, nothing is replaced; to update, download the release yourself and [verify it](#verifying-a-download) first. `--check` is accepted for clarity and changes nothing (checking is all the command does).

This is the only command that contacts a server other than GOG. It sends one plain request to `api.github.com` (no login data, no GOG token, nothing from your library) and writes nothing to disk. It exits with status `0` when the check worked, whether or not a newer release exists, and with `1` when it could not be done (no network, GitHub refused the request, an unexpected answer). GitHub limits requests without a login to about 60 per hour per address, which is plenty for an occasional check.

Why it does not install anything: the program holds your GOG login, so it must not replace itself from the internet unless it can prove that what arrives is the real release. That needs signed releases, which are planned but not available yet.

### `diagnostics`

```bash
python gogrepo_delta.py diagnostics
python gogrepo_delta.py diagnostics --verbose
```

Generates diagnostic information intended for maintenance and troubleshooting. `--verbose` includes additional information.

## Selecting games by tag

`--tags`, `--skiptags` and `--notags` use the tags you made in your GOG library (for example "Favorites" or "NEXT TO PLAY"). They work with `update`, `download`, `verify`, `import`, `backup` and `list`:

```bash
python gogrepo_delta.py update
python gogrepo_delta.py download --tags Favorites
python gogrepo_delta.py verify --tags "NEXT TO PLAY" Completed --skiptags Abandoned
```

- `update` reads your tags from GOG and stores their names in the manifest (`tag_names`). It refreshes them for every game on each run, so run `update` after you change tags on GOG. The other commands read the tags from the manifest and stop with a message if it has no tag data yet.
- A game matches if it has **any** of the tags given. Case, accents and punctuation do not matter. A tag with spaces must be in quotes.
- `--tags` together with `--ids` means the games that are in both. `--skiptags` always wins.
- A tag that no game has is an error (the message lists the tags that exist). If nothing is left to do, the command stops instead of running on all games.
- `--notags` takes only the games (and movies) that have no tag at all, for example to find what you have not sorted yet: `python gogrepo_delta.py list --notags`. It cannot be used together with `--tags` (the program refuses), but it can be used with `--skiptags` and `--ids`. A game whose tags are not known to the manifest yet (an old entry) does not count as "without tags"; `update` refreshes the tags of all games, so run it once if `--notags` misses games. It works with every command that takes `--tags`, also in the config file (`notags = yes`).
- In `list` the tags are one more filter, together with the words, `--os` and `--lang` (an item must pass all of them). `list` reads the manifest only: it needs no login and changes nothing.
- `update --tags` limits what is fetched but keeps the usual rule of what counts (new and updated games; add `--full` for all of them). Like `--ids`, a tag-limited update never removes games from the manifest.

## Operating system and language selection

For `update`, `download`, `verify`, `import`, and `backup`, the default selection is the current computer's operating system and detected language. If detection fails or the detected value is not offered by GOG, the script falls back to Windows and English.

- Use `--os windows linux mac` to explicitly select operating systems.
- Use `--lang en de` to explicitly select languages.
- Use `--skipos` and `--skiplang` to exclude values instead.
- The include and exclude forms for the same dimension are mutually exclusive.

When the language is selected automatically and is not English, English is used as a fallback **per game, file group, and operating system** if the preferred language is unavailable. An explicit `--lang` or `--skiplang` selection disables this automatic fallback. For example, a German default can select German Windows installers and English Linux installers when no German Linux installer exists.

**Manifest note:** an update replaces the stored file information for each game it fetches. If you need multiple OS/language variants, specify them explicitly (for example, `--os windows linux --lang en de`). A plain update can replace other variants previously stored for an updated game; files already on disk are not automatically deleted.

Before a new update starts, the program compares the manifest with the operating systems and languages the update will use. If the update would drop installer entries for other systems or languages, it **warns** (it does not stop): how many installer files of how many games would go and why, that `clean` would then take the files on disk for orphans and move them to `!orphaned`, and that a later update that includes them again adds the entries back as new ones (`download` then checks them again and fetches only what is not right). To avoid it, give all the systems and languages you use with `--os` / `--lang`, or put them in the config file. An update without `--full` says "up to N" because only new and updated games are fetched.

## Configuration

On first run, the program creates `gogrepo_delta.cfg` in the current working directory. Set `GOGREPO_DELTA_CONFIG` to use a different configuration file.

The INI-style file has these sections:

- `[settings]`: internal settings such as HTTP timeouts/retries, download chunk size, thread count, logging limits, progress interval, and save thresholds.
- `[common]`: command-line defaults shared by commands.
- Command sections such as `[update]`, `[download]`, and `[verify]`: command-specific defaults.

Configuration precedence (highest first):

1. Options explicitly supplied on the command line.
2. The relevant command section.
3. `[common]`.
4. Built-in defaults.

Boolean settings accept `true`/`yes`/`on`/`1` and `false`/`no`/`off`/`0`. Lists must be separated by commas or written one item per line; spaces and semicolons are not list separators. Section names and `os` and `lang` values must be lowercase. Option names may use any case. Game IDs and names are matched without regard to case. Empty values use the built-in default. Unknown keys produce warnings; invalid values stop the command with an explanatory message. The program does not overwrite an existing configuration file. These rules are also described in the header of newly generated configuration files; existing files are left unchanged.

Example:

```ini
[common]
# Apply to commands that support these options
os = windows
lang = en

[settings]
download_threads = 4
http_timeout = 30
```

Use a different configuration file:

```bash
# Linux / macOS
export GOGREPO_DELTA_CONFIG="/path/to/my-config.cfg"

# Windows Command Prompt
set GOGREPO_DELTA_CONFIG=C:\path\to\my-config.cfg
```

Login credentials are never read from the configuration file; `token_mode` in `[settings]` only chooses how the token file is saved (`encrypted`, the default, or `plain`).

## Files and data safety

The program keeps its state files in the current working directory (unless configured otherwise):

| File | Purpose |
| --- | --- |
| `gogrepo_delta.cfg` | Configuration and command defaults. |
| `gog-token.json` | Saved GOG authentication token (encrypted by default; plain text if the `cryptography` package is missing or `token_mode = plain` or `GOGREPO_TOKEN_MODE=plain`). Treat it as a credential. |
| `gog-token.dat` | Legacy token file from older versions. Read-only; never modified or deleted. |
| `gog-manifest.dat` | Main library manifest (JSON by default). |
| `gog-manifest.dat.bak` | Previous manifest version. |
| `gog-manifest.dat.legacy` | One-time preservation of the old manifest format during migration. |
| `gog-resume-manifest.dat` | State used to resume interrupted updates. |
| `gog-config.dat` | Leftover of older versions; the program does not use it any more and you can delete it. |
| `gogrepo.log` | Log file. |
| `gog-library.csv` | Default CSV export output. |
| `gog-wishlist.json` | Default output of `wishlist`; the next run compares with it. |
| `gog-wishlist.csv` | Default CSV output of `wishlist --csv`. |
| `!md5_xmls/` | Cached MD5 XML files used to resume and verify downloads. |

Rename recovery is also conservative. A successful file or folder rename is saved to the manifest so the next run does not repeat it. File and game-directory rename cycles (for example, two installers or two game folders swapping names) are staged before destinations are changed. A file destination is treated as already correct only when both its size and MD5 match the manifest. Genuine destination clashes are preserved in `!orphaned`; ambiguous mappings and unsafe folder names are skipped. If a rename fails, its old name remains in the manifest for a later retry. A dry run does not create rename staging or orphan directories.

Cleanup is conservative when GOG metadata is incomplete. If a download, Galaxy download, shared download, or released extra has no filename, `clean` and the `!downloading` cleanup leave unrecognized files in that game's folder rather than treating them as obsolete. MD5 XML cleanup also keeps existing OS and language directories when an entry has no OS or language, and keeps XML files when a filename is unknown. These files may be cleaned on a later run after the manifest contains complete metadata; missing metadata is not treated as proof that local data is obsolete.

Image downloads are also conservative. A new cover or background is downloaded to a temporary file and installed only after the response has been written successfully, so a failed request does not remove the previous image. Old background-key folders are cleaned only when the game-details metadata is explicitly marked complete and every current background was obtained; older manifests and partially failed refreshes keep unrecognized artwork. `-nocleanimages` still deletes superseded images, but only after a replacement is safely installed.

### Manifest format and recovery

Older manifests without stored `api_downlink` information remain supported. If chunk information cannot be retrieved for a file (for example, when an older manifest is used with a signed download URL), that file is downloaded without chunk verification rather than failing because the chunk information is unavailable.

The manifest and resume manifest are written as indented JSON by default. Existing legacy-format manifests remain readable. To write the old format:

```bash
python gogrepo_delta.py update --manifestformat legacy
```

JSON saves are checked by reading the data back. If it cannot be represented without changing its meaning, the old format is used for that save. Saves are atomic; the previous manifest is retained as `.bak`.

If the manifest is missing or damaged and a backup exists, the program offers an interactive restore. A damaged manifest is preserved with a `.damaged` suffix. In non-interactive runs, it stops rather than asking an unanswered question or silently treating a damaged manifest as an empty library. A first run with neither manifest nor backup is normal for `update`, the command that builds the manifest. Every command that needs one (`download`, `verify`, `import`, `backup`, `list`, `export`, `diagnostics`) stops with an error and exit status 1 when there is neither manifest nor backup, before it reads the token or asks for a password: most often the program was started in the wrong folder (the manifest is read from the current folder), and a scheduled task should not end with status 0 after doing nothing. `clean` has its own refusal.

For runs that cannot be asked (scheduled tasks), `--usebackup` uses the backup copy of a missing or damaged manifest without asking, after checking that the backup can be read; a damaged manifest is kept as `.damaged`, and the summary of the run says `manifests restored from the backup copy`. Without it such a run stops, as above. Use it only if you accept continuing with the manifest as it was before the last save.

**Back up `gog-token.json` securely** if you want to preserve the login session, and do not share it in bug reports.

## Logging and exit codes

Logs are written to `gogrepo.log`, with timestamps and severity levels. Common options:

- `--nolog`: disable file logging.
- `--debug`: enable additional debug output.
- Log rotation is configurable in `gogrepo_delta.cfg`.

The first line of every run in the log file is the version of the program, with the Python and the system it ran on (for example `gogrepo_delta.py version 0.5.50 (Python 3.14.0, Windows-11-...)`). It is written to the file only, not to the console, and not with `--nolog`.

At the end of a command, the program reports a summary of completed work and lists failures with reasons. `files downloaded` counts the files of which data was fetched, with the amount that really came from GOG; `files verified in place (nothing downloaded)` counts files that were marked for change but were already right on the disk, chunk by chunk, and needed no data. Completed files recovered from an earlier interrupted run are included in the recovery count.

When a chunk download is incomplete, the chunk-verification retry loop waits for `http_retry_delay` before each retry, except after the final attempt. The wait occurs outside the download job lock, so other downloads can proceed. With the default settings, retry delays can add up to 20 seconds (4 retries × 5 seconds) before the download gives up.

**Exit status:**

- `0`: command completed without reported failures.
- `1`: one or more failures occurred, a fatal error occurred, or the run was interrupted.

A command can therefore complete most of its work and still return `1`. This is intentional and useful for scripts and scheduled jobs.

## Troubleshooting

- Run `python gogrepo_delta.py --help` or `python gogrepo_delta.py COMMAND --help` for the exact options accepted by your copy.
- Run `diagnostics`; add `--verbose` for additional details.
- Check `gogrepo.log` for timestamped error messages.
- If a manifest cannot be read, preserve the `.bak` and `.damaged` files before attempting manual recovery.
- If login encounters a CAPTCHA or GOG changes its login page, try `login --browser`.
- For scheduled tasks, remember that recovery prompts require an interactive terminal; unattended runs stop safely instead of waiting for input. Add `--usebackup` to let such a run use the backup copy of the manifest, and start the task in the folder that holds the manifest (a missing manifest stops it).

## Credits and links

- Current repository: [MarS301/gogrepo_delta](https://github.com/MarS301/gogrepo_delta)
- Original projects: `eddie3` and `kalanyr`
- Current version contributors: `MarS301`, `claude.ai` and `chatgpt`
- GOG: [https://www.gog.com/](https://www.gog.com/)

See [CHANGELOG.md](CHANGELOG.md) for the changes documented for this version.

## Changelog

Every change, newest first, the known issues and the rule for the version number (`0.5.N`, where N is the number of the newest entry) are in [CHANGELOG.md](CHANGELOG.md).

---

<div align="center">

**Preserve your library. Verify your files. Keep control of your collection.**

</div>
