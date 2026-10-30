gogrepo_delta

Python-based tool for downloading and managing your GOG.com game collection and extras for full offline enjoyment.

gogrepo_delta.py is a standalone Python script based on gogrepoc. It allows you to maintain a local copy of your GOG library, including game installers, bonus content, metadata and optional game artwork.

The script can be run from anywhere using Python 3.10 or later. It uses a local manifest to keep track of your GOG library and downloaded files.

By default, game folders are saved in the directory from which the script is run. You can also specify another directory. Each game gets its own directory containing its installers and bonus files.

License: GPLv3+

Current version: 0.15.19

Features
Download games and extras from your GOG library.
Select games based on operating system (Windows, Linux, macOS) and language.
Automatically detect your system's operating system and language.
Automatically fall back to English when a game does not have an installer in your default language.
Support for standalone and GOG Galaxy installers, including shared files.
Save a !info.txt file in each game directory containing information about the game and its downloadable files.
Save a !serial.txt file when a game has serial numbers or CD keys.
Optionally download game cover images and background artwork.
Verify downloaded files using MD5 checksums, expected file sizes and ZIP integrity checks.
Support for multipart ZIP archives.
Automatically retry failed downloads when GOG servers report temporary errors.
Resume interrupted downloads where possible, using verified download chunks.
Import existing local collections by matching MD5 checksums.
Incrementally back up existing collections.
Identify and clean files that are no longer present in the manifest.
Remove orphaned files and obsolete installers.
Export your library information to a CSV spreadsheet.
Search and list games in your local manifest.
Configurable download threads, HTTP retries, timeouts and other settings.
Automatically generate a configuration file with explanations of available settings.
Detailed logging and end-of-run summaries.
Suitable for scheduled tasks and daily cronjobs.
Quick Start – Typical Use Case
1. Authenticate with GOG

Log in to GOG and save your authentication token locally.

bash
python gogrepo_delta.py login


You will be prompted for your GOG username/email and password.

Alternatively, use browser authentication:

bash
python gogrepo_delta.py login -browser


This opens the GOG sign-in page in your browser. After signing in, copy and paste the resulting browser URL when prompted.

Browser authentication is particularly useful when GOG requires a CAPTCHA or the automatic login process does not work.

Your authentication token is saved in gog-token.dat. You generally only need to authenticate once.

Security note: Avoid supplying your password directly on the command line, as it may be visible in shell history and process listings.

2. Update your local manifest

Fetch information about your GOG library, including game titles, download links, serial numbers, checksums and file sizes.

bash
python gogrepo_delta.py update


The manifest is saved as gog-manifest.dat.

By default, the update checks for new and updated games and uses your system's detected operating system and language.

Run this command whenever you want to discover newly added games or updated content.

3. Download your games

Download games and bonus content using the information stored in the manifest.

bash
python gogrepo_delta.py download


By default, only files matching your detected operating system and language are selected. English is used as a fallback when your default language is unavailable for a particular operating system.

You can specify another destination directory:

bash
python gogrepo_delta.py download /path/to/games

4. Verify your collection

Check your downloaded files against the manifest.

bash
python gogrepo_delta.py verify


Verification checks expected file sizes, MD5 checksums and ZIP archive integrity.

Files that fail verification are reported and, by default, moved out of the collection for cleanup.

5. Repeat regularly

To keep your collection up to date, periodically run:

bash
python gogrepo_delta.py update
python gogrepo_delta.py download
python gogrepo_delta.py verify


The script is designed to support incremental updates and interrupted downloads.

Advanced Usage – Common Tasks
Update only new games

Add games that are not already present in your manifest:

bash
python gogrepo_delta.py update -skipknown

Update only games marked as updated
bash
python gogrepo_delta.py update -updateonly

Update your entire GOG library
bash
python gogrepo_delta.py update -full

Update specific games
bash
python gogrepo_delta.py update -ids trine_2_complete_story


Multiple games can be specified:

bash
python gogrepo_delta.py update -ids trine_2_complete_story witcher_3

Download specific games
bash
python gogrepo_delta.py download -ids trine_2_complete_story

Download Windows games in English and German
bash
python gogrepo_delta.py download -os windows -lang en de

Download game artwork

Download cover images:

bash
python gogrepo_delta.py download -covers


Download background images:

bash
python gogrepo_delta.py download -backgrounds

Limit the amount downloaded

Limit downloads to approximately 1000 MB:

bash
python gogrepo_delta.py download -downloadlimit 1000

List games in your manifest

Display all games:

bash
python gogrepo_delta.py list


Search for games by words:

bash
python gogrepo_delta.py list witcher


Output only game titles/IDs, one per line:

bash
python gogrepo_delta.py list -format ids

Export your library

Generate a CSV spreadsheet containing information about all files in your manifest:

bash
python gogrepo_delta.py export


The default output is gog-library.csv.

You can specify another output filename:

bash
python gogrepo_delta.py export -output my-library.csv


You can also check which files exist in a particular game directory:

bash
python gogrepo_delta.py export -savedir /path/to/games


This adds an on disk column indicating whether each file exists, has the expected size, or is missing.

Commands

All commands support -h or --help for command-specific help.

Long options accept both the original single-dash syntax (for example, -skipos) and GNU-style double-dash syntax (for example, --skipos).

login

Authenticate with GOG and save the authentication token locally.

bash
python gogrepo_delta.py login [username] [password]


Arguments:

username: GOG username or email address.
password: GOG password (optional; prompted securely if omitted).

Options:

-browser: Use browser-based authentication instead of automatic username/password authentication.

The saved token is stored in gog-token.dat.

update

Fetch game information and update the local manifest.

bash
python gogrepo_delta.py update [options]


Options:

-os [OS ...]: Operating systems to include (windows, linux, mac). Default: detected system.
-skipos [OS ...]: Exclude specified operating systems.
-lang [LANG ...]: Languages to include (en, de, fr, etc.). Default: detected system language.
-skiplang [LANG ...]: Exclude specified languages.
-standard: Update new and updated games only (default unless -ids is used).
-skipknown: Only update games not already known to the manifest.
-updateonly: Only update games marked as updated by GOG.
-full: Update all games in your GOG account.
-ids [ID ...]: Update specific games by ID or title.
-skipids [ID ...]: Exclude specific games from updating.
-skiphidden: Skip games marked as hidden.
-installers [TYPE]: Installer selection (standalone or both). Deprecated.
-resumemode [MODE]: Resume handling: noresume, resume or onlyresume. Default: resume.
-strictverify: Clear previously verified status unless the MD5 matches.
-strictdupe: Apply stricter duplicate matching when MD5 information is missing.
-lenientdownloadsupdate: Do not mark installers for updating based solely on changed update timestamps when MD5 information is unavailable or does not match.
-strictextrasupdate: Mark extras for updating when their update timestamps change, even if names and sizes match.
-md5xmls: Download available MD5 XML files into the MD5 directory.
-nochangelogs: Do not save game changelogs.
-diagnostic: Perform more exhaustive checks of GOG data for subsequent diagnostics.
-wait HOURS: Wait the specified number of hours before starting.

Notes:

-os and -skipos are mutually exclusive.
-lang and -skiplang are mutually exclusive.
-standard, -skipknown, -updateonly and -full are mutually exclusive.
-ids and -skipids are mutually exclusive.
download

Download games and extras listed in the manifest.

bash
python gogrepo_delta.py download [savedir] [options]


Arguments:

savedir: Destination directory for downloaded games. Defaults to the current game storage directory.

Options:

-dryrun: Display what would be downloaded without downloading anything.
-skipextras: Skip bonus content.
-skipgames: Skip game installers (deprecated; use the individual installer options).
-skipgalaxy: Skip GOG Galaxy installers.
-skipstandalone: Skip standalone installers.
-skipshared: Skip installers shared between Galaxy and standalone.
-ids [ID ...]: Download only specified games.
-skipids [ID ...]: Exclude specified games.
-id ID: Specify a single game (deprecated; use -ids).
-os [OS ...]: Download game files only for specified operating systems.
-skipos [OS ...]: Exclude game files for specified operating systems.
-lang [LANG ...]: Download game files only for specified languages.
-skiplang [LANG ...]: Exclude specified languages.
-skipfiles [FILE ...]: Skip files matching the specified filenames or glob patterns.
-covers: Download game cover images.
-backgrounds: Download game background images.
-nocleanimages: Delete old artwork instead of cleaning it up.
-downloadlimit MB: Limit downloads to approximately the specified number of megabytes.
-skippreallocation: Do not preallocate disk space for downloads.
-wait HOURS: Wait the specified number of hours before starting.

Notes:

By default, the script selects the detected operating system and language.
When using the automatically detected language, English is used as a fallback for games without a matching language version.
Explicitly specifying -lang disables the automatic English fallback.
verify

Verify downloaded files against the manifest.

bash
python gogrepo_delta.py verify [gamedir] [options]


Arguments:

gamedir: Directory containing downloaded games. Defaults to the current game storage directory.

Options:

-forceverify: Also verify files that have not changed since their last successful verification.
-skipmd5: Skip MD5 checksum verification.
-skipsize: Skip file size verification.
-skipzip: Skip ZIP integrity verification.
-highmemory: Use memory instead of temporary files when testing multipart ZIP archives. At least 50 GB of available memory is recommended.
-lowtmpspace: Skip multipart ZIP archive tests when insufficient temporary disk space is available.
-delete: Delete files that fail integrity checks.
-noclean: Leave files that fail integrity checks in place.
-clean: Deprecated; cleaning is now the default behavior.
-ids [ID ...]: Verify only specified games.
-skipids [ID ...]: Exclude specified games.
-id ID: Verify a single game (deprecated; use -ids).
-skipfiles [FILE ...]: Skip files matching specified filenames or glob patterns.
-os [OS ...]: Verify files for specified operating systems.
-skipos [OS ...]: Exclude specified operating systems.
-lang [LANG ...]: Verify files for specified languages.
-skiplang [LANG ...]: Exclude specified languages.
-skipextras: Skip bonus content.
-skipgames: Skip game installers.
-skipgalaxy: Skip Galaxy installers.
-skipstandalone: Skip standalone installers.
-skipshared: Skip shared installers.

Important: The verify command returns exit status 1 when it finds verification problems, including missing files.

import

Import files from an existing GOG collection by matching their MD5 checksums against the manifest.

bash
python gogrepo_delta.py import src_dir dest_dir [options]


Arguments:

src_dir: Existing collection to import from.
dest_dir: Destination directory for imported files.

Options:

-os [OS ...]: Import files for specified operating systems.
-skipos [OS ...]: Exclude specified operating systems.
-lang [LANG ...]: Import files for specified languages.
-skiplang [LANG ...]: Exclude specified languages.
-skipgalaxy: Skip Galaxy installers.
-skipstandalone: Skip standalone installers.
-skipshared: Skip shared installers.
-ids [ID ...]: Import only specified games.
-skipids [ID ...]: Exclude specified games.

Files are imported when their MD5 checksums match the corresponding manifest entries.

backup

Perform an incremental backup of your existing collection.

bash
python gogrepo_delta.py backup src_dir dest_dir [options]


Arguments:

src_dir: Source directory containing your GOG collection.
dest_dir: Backup destination directory.

Options:

-ids [ID ...]: Back up only specified games.
-skipids [ID ...]: Exclude specified games.
-os [OS ...]: Back up files for specified operating systems.
-skipos [OS ...]: Exclude specified operating systems.
-lang [LANG ...]: Back up files for specified languages.
-skiplang [LANG ...]: Exclude specified languages.
-skipextras: Skip bonus content.
-skipgames: Skip game installers.
-skipgalaxy: Skip Galaxy installers.
-skipstandalone: Skip standalone installers.
-skipshared: Skip shared installers.

The backup is incremental and copies known files from the source collection to the destination.

list

List games in your manifest or search for games by ID, title or name.

bash
python gogrepo_delta.py list [words] [options]


Arguments:

words: Optional search terms. All supplied words must match, in any order.

Options:

-os [OS ...]: Show games with files for specified operating systems.
-skipos [OS ...]: Exclude games that only have files for specified operating systems.
-lang [LANG ...]: Show games with files for specified languages.
-skiplang [LANG ...]: Exclude games that only have files for specified languages.
-format [FORMAT]: Output format: table (default) or ids.

Example:

bash
python gogrepo_delta.py list witcher


To generate a list suitable for scripts:

bash
python gogrepo_delta.py list -format ids

export

Export manifest information to a CSV spreadsheet.

bash
python gogrepo_delta.py export [options]


Options:

-output FILE: Output filename. Default: gog-library.csv.
-savedir DIR: Check whether files exist in the specified directory and include an on disk column.
-delimiter CHAR: Specify the CSV column separator.

The CSV contains one row per file, including:

Game ID and title.
Game folder.
File type (standalone, Galaxy, shared or extra).
Filename.
Operating system and language.
Version and file size.
MD5 checksum.
Last updated information.
Optional on-disk status.

The CSV is written as UTF-8 with a byte order mark for improved compatibility with spreadsheet applications such as Microsoft Excel.

clean

Clean your game directory of files that are not present in the manifest.

bash
python gogrepo_delta.py clean cleandir [options]


Arguments:

cleandir: Root directory containing your GOG games.

Options:

-dryrun: Display files that would be moved without actually moving them.

Files unknown to the manifest are moved into the !orphaned directory rather than immediately deleted.

clear_partial_downloads

Remove partially downloaded files from your game directory.

bash
python gogrepo_delta.py clear_partial_downloads gamedir [options]


Arguments:

gamedir: Root directory containing your GOG games.

Options:

-dryrun: Display files that would be removed without actually removing them.
trash

Permanently remove orphaned files and optionally obsolete installers.

bash
python gogrepo_delta.py trash gamedir [options]


Arguments:

gamedir: Root directory containing your GOG games.

Options:

-dryrun: Display files that would be removed without deleting them.
-installersonly: Deprecated alias for -installers.
-installers: Also delete installer file types, even if they are not duplicates.
-folders: Also delete orphaned game folders that have a corresponding game folder.
-images: Also delete orphaned !images directories that have a corresponding images directory.
-relaxed: Relax duplicate checks and deletion requirements. Use with care.

By default, trash removes strict duplicates of known game files, matching both file size and MD5 checksum.

Warning: This command permanently deletes files. Use -dryrun first to review what will be removed.

diagnostics

Generate diagnostic information for script maintenance and troubleshooting.

bash
python gogrepo_delta.py diagnostics [options]


Options:

-verbose: Include additional diagnostic information that is not normally necessary.

This command is particularly useful when investigating problems with GOG data retrieval or reporting issues.

Configuration

On its first run, the script automatically creates:

text
gogrepo_delta.cfg


This INI-style configuration file allows you to customize program settings and command-line defaults without modifying the Python script.

You can edit the file using any text editor.

Configuration sections
[settings]: Configure HTTP timeouts, retry counts, download threads, logging limits, download chunk sizes and other internal settings.
[common]: Configure default command-line options shared between commands.
[login], [update], [download], [verify], etc.: Configure defaults for individual commands.
Configuration precedence

Options are applied in the following order:

Explicit command-line arguments.
Command-specific configuration section.
Common configuration section.
Built-in defaults.

Command-line arguments override configuration file values.

Lists can be specified using commas or one entry per line.

Boolean values accept true, yes, on, 1, false, no, off and 0.

The configuration file is not overwritten if it already exists.

To use a different configuration file, set the environment variable:

text
GOGREPO_DELTA_CONFIG


For example, on Linux:

bash
export GOGREPO_DELTA_CONFIG=/path/to/my-config.cfg


On Windows:

cmd
set GOGREPO_DELTA_CONFIG=C:\path\to\my-config.cfg

Local Files

The script maintains several files in its working directory:

File	Description
gogrepo_delta.cfg	Program configuration and command defaults.
gog-token.dat	Saved GOG authentication token.
gog-manifest.dat	Main game manifest.
gog-manifest.dat.bak	Previous manifest backup.
gog-manifest.dat.legacy	Original manifest format, preserved when migrating to JSON.
gog-resume-manifest.dat	Manifest used for resuming interrupted updates.
gog-config.dat	Internal configuration data.
gogrepo.log	Log file.
gog-library.csv	Default CSV export filename.

The manifest is saved in JSON format by default. Existing legacy-format manifests can still be read.

To retain the old manifest format, use:

bash
python gogrepo_delta.py update -manifestformat legacy


A missing or damaged manifest is handled with additional safeguards. When a backup is available, the script offers to restore it rather than silently starting with an empty manifest.

Requirements
Python 3.10 or later.
html5lib 0.99999 or later.
requests.
psutil.

Install the required Python packages using pip:

bash
pip install html5lib requests psutil

Optional dependencies
html2text 2015.6.21 or later: Used to convert GOG game changelogs from HTML into readable text.

Install it with:

bash
pip install html2text

Platform-specific dependencies

Linux / Unix:

PyQt5 with QtDBus support is optional and can be used to prevent system suspend/sleep interruptions where supported.

macOS:

PyObjC components (pyobjc, including CoreFoundation support) are required for macOS-specific functionality.
The script uses macOS power-management functionality to prevent sleep interruptions where supported.

Windows:

Uses the Windows API through Python's built-in ctypes module where required.
Logging and Error Handling

The script writes its log to:

text
gogrepo.log


Logging includes timestamps and severity levels.

Logging can be disabled using:

bash
python gogrepo_delta.py download -nolog


The script also supports:

Automatic log rotation.
Configurable retry counts and delays.
HTTP timeout handling.
Resumable downloads.
Atomic manifest and configuration file saves.
Detailed end-of-run summaries.
Failure reporting with reasons.
Meaningful process exit codes.

A successful run returns exit status 0. A run that encounters failures returns exit status 1, even if other operations completed successfully.

This makes the script suitable for automated jobs and monitoring.

Other Arguments

These arguments are available across the commands where applicable:

-h, --help: Display help and exit.
-v, --version: Display script version and exit.
-nolog: Disable writing to gogrepo.log.
-debug: Enable additional debug logging.

Example:

bash
python gogrepo_delta.py --version

TODO
Additional improvements to GOG movie support.
Further improvements to GOG API compatibility.
Additional features and maintenance improvements.

Feel free to open an issue or submit a feature request on GitHub!

Links
gogrepo_delta GitHub repository
gogrepo_delta.py source code
Original gogrepoc project
GOG.com
