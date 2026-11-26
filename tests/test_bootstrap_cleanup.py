"""Entry 0.5.92: a test run leaves nothing behind in the temporary folder. _bootstrap made a gogrepo_delta_tests_* folder for the configuration file of every test run and never removed it."""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class BootstrapCleanupTests(unittest.TestCase):
    def test_the_folders_made_by_the_bootstrap_are_gone_when_the_process_ends(self):
        code = "import _bootstrap, os; print(os.path.dirname(os.environ['GOGREPO_DELTA_CONFIG'])); print(os.getcwd())"
        out = subprocess.run([sys.executable, '-c', code], cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        config_dir, scratch_dir = out.stdout.splitlines()[-2:]
        self.assertIn('gogrepo_delta_tests_', os.path.basename(config_dir))
        self.assertIn('gogrepo_delta_cwd_', os.path.basename(scratch_dir))
        self.assertFalse(os.path.exists(config_dir), config_dir)
        self.assertFalse(os.path.exists(scratch_dir), scratch_dir)


    def test_the_cleanup_leaves_the_scratch_folder_and_closes_the_log_file_before_it_removes_it(self):
        """Windows cannot delete a folder that is the current folder of a process, nor a file that is open, so the scratch folder stayed behind there after every run (the removal ignores
        errors). A test that runs main() attaches the script's log handler, which then holds gogrepo.log in the scratch folder open (the child does what main() does). Linux and macOS do
        not mind, so this checks the two conditions instead of the deletion: before the cleanup the process is in the folder and the log file is open, afterwards neither."""
        code = ("import _bootstrap, json, os\n"
                "import gogrepo_delta as g\n"
                "g.rootLogger.addHandler(g.loggingHandler)       # what main() does unless -nolog\n"
                "g.rootLogger.warning('this opens gogrepo.log in the current folder')\n"
                "scratch = os.path.realpath(_bootstrap.SCRATCH_DIR)\n"
                "def inside():\n"
                "    cwd = os.path.realpath(os.getcwd())\n"
                "    return cwd == scratch or cwd.startswith(scratch + os.sep)\n"
                "before = dict(inside=inside(), log_open=g.loggingHandler.stream is not None, log_file=os.path.isfile(os.path.join(scratch, 'gogrepo.log')))\n"
                "_bootstrap.remove_scratch_dir()\n"
                "print(json.dumps(dict(before=before, inside=inside(), log_open=g.loggingHandler.stream is not None, exists=os.path.exists(scratch))))\n")
        out = subprocess.run([sys.executable, '-c', code], cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        state = json.loads(out.stdout.splitlines()[-1])
        self.assertEqual(state['before'], dict(inside=True, log_open=True, log_file=True))       # the situation that Windows cannot delete
        self.assertFalse(state['inside'])
        self.assertFalse(state['log_open'])
        self.assertFalse(state['exists'])


if __name__ == '__main__':
    unittest.main()
