"""Import gogrepo_delta.py (the single-file script next to this folder) as the module 'gogrepo_delta'.

The script needs requests, html5lib and psutil at import time. If html5lib/psutil are not installed
(for example in a bare CI container) harmless empty stand-ins are used so the pure-logic tests can
still run; none of the code under test touches them."""
import atexit, importlib.util, os, shutil, sys, tempfile, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The script keeps its data (gog-manifest.dat, gogrepo.log, the config file, ...) in the folder it is started from, and a command that
# saves the manifest writes there. A test must never do that in the folder the tests were started from: that may be the folder of a
# real library, and its manifest would be overwritten. So the whole test run happens in a scratch folder that is removed at the end.
# This is done before the script is imported (it opens gogrepo.log in the current folder when it is loaded).
LAUNCH_DIR = os.getcwd()
SCRATCH_DIR = os.path.realpath(tempfile.mkdtemp(prefix='gogrepo_delta_cwd_'))
os.chdir(SCRATCH_DIR)
atexit.register(shutil.rmtree, SCRATCH_DIR, True)
for _name in ('html5lib', 'psutil'):
    try:
        __import__(_name)
    except ImportError:
        sys.modules[_name] = types.ModuleType(_name)

# The tests must not be influenced by (or write into) a real gogrepo_delta.cfg in the folder they are started from.
# The script looks for its config file at the path in this variable; scripts started by the tests inherit it.
_CONFIG_DIR = tempfile.mkdtemp(prefix='gogrepo_delta_tests_')
os.environ['GOGREPO_DELTA_CONFIG'] = os.path.join(_CONFIG_DIR, 'gogrepo_delta.cfg')

if 'gogrepo_delta' not in sys.modules:
    _spec = importlib.util.spec_from_file_location('gogrepo_delta', os.path.join(ROOT, 'gogrepo_delta.py'))
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules['gogrepo_delta'] = _mod
    _spec.loader.exec_module(_mod)

# The script logs to the console while it runs; that is only noise between test results. Tests that check log
# output (assertLogs, the download rig) attach their own handlers and are not affected.
gogrepoc = sys.modules['gogrepo_delta']   # the name gogrepoc is kept in the tests as a short alias


def _assert_no_logs(self, logger=None, level=None):
    """unittest.TestCase.assertNoLogs (Python 3.10 and newer) for older Pythons: a context manager that fails the test if the logger logs
    anything at `level` or above while it is active. Used as TestCase.assertNoLogs when the running Python does not have it."""
    import contextlib
    import logging

    @contextlib.contextmanager
    def watching():
        target = logging.getLogger(logger) if (logger is None or isinstance(logger, str)) else logger
        threshold = logging.getLevelName(level) if isinstance(level, str) else (level or logging.INFO)
        records = []

        class Collect(logging.Handler):
            def emit(self, record):
                records.append(record)
        handler = Collect(threshold)
        old_level, old_propagate = target.level, target.propagate
        target.addHandler(handler)
        target.setLevel(min(threshold, old_level) if old_level else threshold)
        target.propagate = False
        try:
            yield
        finally:
            target.removeHandler(handler)
            target.setLevel(old_level)
            target.propagate = old_propagate
        if records:
            self.fail('Unexpected logs found: %r' % ['%s:%s' % (r.levelname, r.getMessage()) for r in records])
    return watching()


import unittest as _unittest
if not hasattr(_unittest.TestCase, 'assertNoLogs'):
    _unittest.TestCase.assertNoLogs = _assert_no_logs


def without_old_python_warning(stderr):
    """stderr (bytes) of a run of the program without the one line that it prints on a Python older than 3.10 (README: best effort)."""
    return b''.join(line for line in stderr.splitlines(True) if not line.startswith(b'Warning: Python '))


def has_cryptography():
    """True if the optional `cryptography` package is installed (the tests of the password-encrypted token need it and are skipped without)."""
    try:
        gogrepoc._token_crypto()
        return True
    except gogrepoc.TokenModuleMissing:
        return False


gogrepoc.RETRY_JITTER = 0   # the waits before a retry vary by up to 20 percent in the program; the tests expect exact waits (tests of the jitter set it themselves)
gogrepoc.rootLogger.removeHandler(gogrepoc.consoleHandler)
gogrepoc.rootLogger.addHandler(__import__('logging').NullHandler())   # no handler would make Python print warnings to stderr

# No test may ever wait for someone to type an answer: the recovery questions are only asked on a terminal, and the tests
# that exercise them pretend to be on one (and to type the answers) explicitly.
gogrepoc._real_stdin_is_interactive = gogrepoc._stdin_is_interactive    # for the tests of the check itself (test_interactive)
gogrepoc._stdin_is_interactive = lambda: False

# Nor may any test ever prompt for a password on the console (token encryption asks for one). Tests that care about the
# prompt patch getpass themselves; every other test silently gets this fixed throw-away password.
gogrepoc.getpass.getpass = lambda prompt='Password: ', stream=None: 'test-password'
