"""Entry 77: the files around the program (workflows, requirements, .gitattributes, .editorconfig, README) must agree with each other and with
the program. Nothing here runs a workflow; it reads the files, so that a change in one place that forgets another place fails a test.
Skipped when the tests are run from a copy of the folder that has no .github folder."""
import glob
import os
import re
import sys
import unittest

import _bootstrap  # noqa: F401

ROOT = _bootstrap.ROOT
WORKFLOWS = os.path.join(ROOT, '.github', 'workflows')


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as r:
        return r.read()


def package_names(text):
    """The names of the packages in a requirements file (without versions, markers and comments), in lower case."""
    names = []
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if line and not line.startswith('-'):
            names.append(re.match(r'[A-Za-z0-9_.\-]+', line).group(0).lower())
    return names


@unittest.skipUnless(os.path.isdir(WORKFLOWS), 'no .github/workflows folder next to the tests')
class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.files = {}
        for path in glob.glob(os.path.join(WORKFLOWS, '*.yml')):
            with open(path, encoding='utf-8') as r:
                self.files[os.path.basename(path)] = r.read()
        self.tests_yml = self.files['tests.yml']
        self.build_yml = self.files['build.yml']

    def test_every_workflow_is_valid_yaml_with_jobs(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML is not installed')
        for name, text in self.files.items():
            with self.subTest(workflow=name):
                data = yaml.safe_load(text)
                self.assertTrue(data.get('jobs'))

    def test_the_workflows_use_the_same_version_of_each_action(self):
        for action in ('actions/checkout', 'actions/setup-python'):
            versions = {}
            for name, text in self.files.items():
                for version in re.findall(r'uses:\s*%s@(\S+)' % re.escape(action), text):
                    versions.setdefault(version, set()).add(name)
            with self.subTest(action=action):
                self.assertEqual(1, len(versions), 'different versions of %s: %s' % (action, versions))

    def test_the_test_matrix_has_the_oldest_supported_python_and_the_one_of_the_binaries(self):
        readme = read('README.md')
        oldest = re.search(r'Python \*\*(\d+\.\d+) or newer\*\*', readme).group(1)
        test_job = self.tests_yml.split('\n  required-packages-only:', 1)[0]            # the matrix of the main job, not the job with fewer packages
        matrix = set(re.findall(r'^\s*(?:-\s*)?python-version:\s*"(\d+\.\d+)"|^\s*-\s*"(\d+\.\d+)"', test_job, re.M))
        versions = {a or b for a, b in matrix}
        self.assertIn(oldest, versions, 'the README says Python %s or newer, but the tests do not run on it' % oldest)
        binaries = re.search(r'python-version:\s*"(\d+\.\d+)"', self.build_yml).group(1)
        self.assertIn(binaries, versions, 'the release binaries use Python %s, which the tests do not run on' % binaries)
        newest_tested = max(versions, key=lambda v: tuple(int(x) for x in v.split('.')))
        self.assertEqual(binaries, newest_tested)

    def test_the_tests_run_on_every_operating_system_of_the_release(self):
        for system in ('ubuntu', 'windows', 'macos'):
            with self.subTest(system=system):
                self.assertRegex(self.tests_yml, r'-\s*%s-latest' % system)
                self.assertIn(system, self.build_yml)

    def test_jobs_have_a_time_limit(self):
        self.assertEqual(self.tests_yml.count('runs-on:'), self.tests_yml.count('timeout-minutes:'))

    def test_the_test_workflow_installs_from_the_requirements_files(self):
        self.assertIn('-r requirements-dev.txt', self.tests_yml)
        self.assertNotRegex(self.tests_yml, r'pip install (?!-r|--upgrade)\w')   # no package list that could drift

    def test_one_job_has_only_the_required_packages(self):
        job = self.tests_yml.split('\n  required-packages-only:', 1)[1]
        self.assertIn('-r requirements.txt', job)
        self.assertNotIn('requirements-optional', job)
        self.assertNotIn('requirements-dev', job)

    def test_the_release_build_installs_the_packages_of_the_requirements_files(self):
        installed = set()
        for line in self.build_yml.splitlines():
            match = re.match(r'\s*(?:python -m )?pip install (.*)', line)
            if match:
                installed |= {w.lower() for w in match.group(1).split() if not w.startswith('-') and w not in ('pip',)}
        installed -= {'pyinstaller'}                    # only the build needs it
        listed = set(package_names(read('requirements.txt')) + package_names(read('requirements-optional.txt')))
        self.assertEqual(listed, installed, 'build.yml installs %s, the requirements files list %s' % (sorted(installed), sorted(listed)))


class PackageListTests(unittest.TestCase):
    def test_the_files_have_no_package_twice(self):
        names = []
        for name in ('requirements.txt', 'requirements-optional.txt'):
            names += package_names(read(name))
        self.assertEqual(sorted(set(names)), sorted(names))

    def test_the_dev_file_includes_the_others_and_adds_pytest(self):
        text = read('requirements-dev.txt')
        self.assertIn('-r requirements.txt', text)
        self.assertIn('-r requirements-optional.txt', text)
        self.assertIn('pytest', package_names(text))

    @unittest.skipUnless(sys.version_info >= (3, 10), 'needs sys.stdlib_module_names')
    def test_every_package_the_program_imports_at_start_is_a_required_package(self):
        # a column-0 `import x` is run whenever the program starts; an optional package is imported inside try: or a function (indented)
        imported = set(re.findall(r'^(?:import|from) ([A-Za-z0-9_]+)', read('gogrepo_delta.py'), re.M))
        third_party = {m for m in imported if m not in sys.stdlib_module_names}
        self.assertEqual({'html5lib', 'requests', 'psutil'}, third_party)
        self.assertEqual(sorted(third_party), sorted(package_names(read('requirements.txt'))))

    def test_the_optional_packages_are_not_imported_at_start(self):
        source = read('gogrepo_delta.py')
        for module in ('cryptography', 'blake3', 'html2text', 'CoreFoundation', 'objc', 'PyQt5'):
            with self.subTest(module=module):
                self.assertNotRegex(source, r'(?m)^(?:import|from) %s\b' % module)

    def test_the_readme_names_every_package(self):
        readme = read('README.md')
        for name in package_names(read('requirements.txt')) + package_names(read('requirements-optional.txt')):
            with self.subTest(package=name):
                self.assertTrue(name in readme.lower(), 'the README does not mention %s' % name)

    def test_the_readme_names_the_requirements_files(self):
        readme = read('README.md')
        for name in ('requirements.txt', 'requirements-optional.txt'):
            self.assertTrue(name in readme, 'the README does not mention %s' % name)


class RepositoryConfigTests(unittest.TestCase):
    def test_gitattributes_makes_text_files_lf_everywhere(self):
        text = read('.gitattributes')
        self.assertRegex(text, r'(?m)^\* text=auto eol=lf$')
        for pattern in ('*.py', '*.md', '*.yml'):
            self.assertRegex(text, r'(?m)^%s\s+text eol=lf$' % re.escape(pattern))

    def test_editorconfig_is_utf8_lf_with_spaces(self):
        text = read('.editorconfig')
        for line in ('root = true', 'charset = utf-8', 'end_of_line = lf', 'insert_final_newline = true', 'trim_trailing_whitespace = true',
                     'indent_style = space', 'indent_size = 4'):
            self.assertIn(line, text)
        self.assertRegex(text, r'\[\*\.md\]\s+trim_trailing_whitespace = false')       # two spaces are a line break in Markdown

    def test_the_program_and_the_tests_follow_the_editorconfig(self):
        # the part of it that is true for the files in the repository, whatever the line endings of a checkout are
        for pattern in ('gogrepo_delta.py', 'tests/*.py', 'requirements*.txt', '.github/workflows/tests.yml'):
            for path in glob.glob(os.path.join(ROOT, pattern)):
                with open(path, 'rb') as r:
                    data = r.read()
                with self.subTest(file=os.path.relpath(path, ROOT)):
                    self.assertNotIn(b'\t', data)
                    self.assertTrue(data.endswith(b'\n'))
                    data.decode('utf-8')
                    self.assertFalse([l for l in data.splitlines() if l != l.rstrip()], 'trailing whitespace')


if __name__ == '__main__':
    unittest.main()
