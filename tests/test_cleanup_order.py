"""Entry 0.5.92: a test that changes into a temporary folder must leave it before the folder is removed. Windows cannot remove the current folder of a process, and `shutil.rmtree(...,
ignore_errors=True)` hides that: the files were deleted and the folder stayed in the temporary folder, after every run (three test classes did that). `addCleanup` runs in reverse, so the
cleanup that changes back must be registered AFTER the one that removes the folder; in a `tearDown`, the change back must come first. This test reads all test files and checks it."""
import ast
import glob
import os
import unittest

import _bootstrap  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(__file__)


def functions(path):
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    return [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]


def dotted(node):
    """'os.chdir' for the node of os.chdir, '' for anything that is not a plain name (ast.unparse needs Python 3.9; the tests must run on 3.8)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return (dotted(node.value) + '.' if dotted(node.value) else '') + node.attr
    return ''


def cleanup_registrations(function):
    """((line, column), text of the first argument) of every addCleanup call in the function; the column tells the order of two calls on one line."""
    return [((node.lineno, node.col_offset), dotted(node.args[0])) for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'addCleanup' and node.args]


def call_lines(function, name):
    return [(node.lineno, node.col_offset) for node in ast.walk(function)
            if isinstance(node, ast.Call) and dotted(node.func) == name]


def problems_in(path):
    problems = []
    for function in functions(path):
        registered = cleanup_registrations(function)
        change_back = [line for line, text in registered if text == 'os.chdir']
        removals = [line for line, text in registered if text == 'shutil.rmtree' or text.endswith('.cleanup')]
        if change_back and removals and min(change_back) < max(removals):
            problems.append('%s:%s registers the change back (line %d) before the removal (line %d): the removal runs first' % (os.path.basename(path), function.name, min(change_back)[0], max(removals)[0]))
        if function.name == 'tearDown':
            chdir, rmtree = call_lines(function, 'os.chdir'), call_lines(function, 'shutil.rmtree')
            if chdir and rmtree and min(rmtree) < min(chdir):
                problems.append('%s:tearDown removes the folder (line %d) before it changes back (line %d)' % (os.path.basename(path), min(rmtree)[0], min(chdir)[0]))
    return problems


class CleanupOrderTests(unittest.TestCase):
    def test_no_test_removes_a_folder_it_is_still_in(self):
        problems = []
        for path in sorted(glob.glob(os.path.join(HERE, '*.py'))):
            if os.path.basename(path) not in (SELF, '_bootstrap.py'):
                problems.extend(problems_in(path))
        self.assertEqual(problems, [])

    def test_the_check_finds_the_wrong_order(self):
        import tempfile
        source = ('import os, shutil, unittest\n'
                  'class A(unittest.TestCase):\n'
                  '    def setUp(self):\n'
                  '        self.addCleanup(os.chdir, self.cwd)\n'
                  '        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)\n'
                  'class B(unittest.TestCase):\n'
                  '    def setUp(self):\n'
                  '        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)\n'
                  '        self.addCleanup(os.chdir, self.cwd)\n'
                  'class C(unittest.TestCase):\n'
                  '    def tearDown(self):\n'
                  '        shutil.rmtree(self.dir, ignore_errors=True); os.chdir(self.cwd)\n'
                  'class D(unittest.TestCase):\n'
                  '    def setUp(self):\n'
                  '        self.addCleanup(os.chdir, self.cwd)\n'
                  '        self.addCleanup(self.tempdir.cleanup)\n'
                  'class E(unittest.TestCase):\n'
                  '    def tearDown(self):\n'
                  '        os.chdir(self.cwd); shutil.rmtree(self.dir, ignore_errors=True)\n')
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'sample.py')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(source)
            found = problems_in(path)
        self.assertEqual(len(found), 3, found)
        self.assertTrue(any('setUp' in line and 'registers the change back' in line for line in found))
        self.assertTrue(any('tearDown removes the folder' in line for line in found))
        self.assertEqual(sum('registers the change back' in line for line in found), 2)          # setUp of A and of D (TemporaryDirectory.cleanup)


if __name__ == '__main__':
    unittest.main()
