# Read-only survey of the file and folder names in gog-manifest.dat.
# Run it in the folder that holds the manifest, with gogrepo_delta.py next to it:
#     python3 gogrepo_survey_names.py [LIBRARY_PATH]
# With LIBRARY_PATH (the folder you download to) it also checks the Windows limit of 259 characters for every path the script builds.
import collections, os, sys, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gogrepo_delta as g

WINDOWS_LIMIT = 259          # MAX_PATH is 260 including the terminating NUL; Windows 10 and later can lift it (LongPathsEnabled), older setups cannot
library = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
downloading = g.DOWNLOADING_DIR_NAME
provisional = os.path.join(g.DOWNLOADING_DIR_NAME, g.PROVISIONAL_DIR_NAME)
extra_for_folder = len(provisional) + 1          # '!downloading\!provisional\' is the longest of the three places a file can be while it is handled

clash, non_ascii, longest, over = [], [], [], []
for game in g.load_manifest():
    folder = game.folder_name
    if not folder.isascii():
        non_ascii.append(('folder', folder))
    groups = collections.defaultdict(set)
    for f in g._game_files(game):
        name = f.get('name')
        if not name:
            continue
        groups[unicodedata.normalize('NFC', name).casefold()].add(name)
        if not name.isascii():
            non_ascii.append((folder, name))
        part = len(folder) + 1 + len(name)                         # GAMEFOLDER\NAME, the part the script decides
        longest.append((part, folder, name))
        if library:
            paths = [os.path.join(library, folder, name), os.path.join(library, downloading, folder, name), os.path.join(library, provisional, folder, name)]
            worst = max(len(p) for p in paths)
            if worst > WINDOWS_LIMIT:
                over.append((worst, folder, name))
    for names in groups.values():
        if len(names) > 1:
            clash.append((folder, sorted(names)))

print('names that differ only in case or Unicode form (the same file on Windows/macOS): %d' % len(clash))
for row in clash:
    print('   ', row)
print('non-ASCII folder or file names: %d' % len(non_ascii))
for row in non_ascii[:20]:
    print('   ', row)
print('longest GAMEFOLDER\\NAME (characters):')
for row in sorted(longest, reverse=True)[:5]:
    print('   ', row)
if longest:
    top = max(longest)[0]
    budget = WINDOWS_LIMIT - 1 - extra_for_folder - top
    print('so the library path (e.g. C:\\GOG) may be at most %d characters for Windows without long path support; %s.' % (budget, 'that is already too little for a path like C:\\Users\\Name\\Documents\\GOG' if budget < 40 else 'that fits a normal path'))
if library:
    print('library path %s (%d characters): %d file(s) would need a path over %d characters' % (library, len(library), len(over), WINDOWS_LIMIT))
    for row in sorted(over, reverse=True)[:10]:
        print('   ', row)
