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


def job_block(workflow_text, name):
    """The text of one job of a workflow: from `  name:` (two spaces) to the next job or the end."""
    match = re.search(r'^  %s:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)' % re.escape(name), workflow_text, re.M | re.S)
    assert match, 'no job %s' % name
    return match.group(1)


USES = re.compile(r'^\s*(?:-\s*)?uses:\s*(?P<action>[\w.-]+/[\w./-]+)@(?P<ref>\S+)(?:\s+#\s*(?P<comment>\S+))?\s*$', re.M)
FULL_HASH = re.compile(r'[0-9a-f]{40}')


def action_uses(workflow_text):
    """[(action, ref, comment)] for every `uses:` of a workflow: `uses: actions/checkout@v6` or `uses: actions/checkout@<hash> # v6.1.0`."""
    return [(m.group('action'), m.group('ref'), m.group('comment')) for m in USES.finditer(workflow_text)]


def major_version(ref, comment):
    """'v6' for the tag v6 and for a hash with the comment # v6.1.0."""
    version = comment if FULL_HASH.fullmatch(ref) else ref
    return re.match(r'v\d+', version).group(0) if version and re.match(r'v\d+', version) else None


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

    def test_the_workflows_use_the_same_major_version_of_each_action(self):
        # tests.yml names a tag (v6), build.yml a hash with the version in a comment (# v6.1.0): both are version 6
        for action in ('actions/checkout', 'actions/setup-python'):
            versions = {}
            for name, text in self.files.items():
                for used, ref, comment in action_uses(text):
                    if used == action:
                        versions.setdefault(major_version(ref, comment), set()).add(name)
            with self.subTest(action=action):
                self.assertEqual(1, len(versions), 'different major versions of %s: %s' % (action, versions))
                self.assertNotIn(None, versions)

    def test_every_action_of_the_release_workflow_is_pinned_to_a_commit_with_its_version_in_a_comment(self):
        uses = action_uses(self.build_yml)
        self.assertEqual(self.build_yml.count('uses:'), len(uses), 'a uses: line that this test cannot read')
        self.assertGreaterEqual(len(uses), 4)
        for action, ref, comment in uses:
            with self.subTest(action=action):
                self.assertRegex(ref, r'^[0-9a-f]{40}$', '%s is not pinned to a full commit hash' % action)
                self.assertRegex(comment or '', r'^v\d+\.\d+\.\d+$', 'the hash of %s needs a comment with its version (# v1.2.3)' % action)

    def test_the_same_action_has_the_same_hash_and_version_everywhere_in_the_release_workflow(self):
        seen = {}
        for action, ref, comment in action_uses(self.build_yml):
            seen.setdefault(action, set()).add((ref, comment))
        for action, versions in seen.items():
            with self.subTest(action=action):
                self.assertEqual(1, len(versions), '%s: %s' % (action, versions))

    def test_the_test_matrix_has_the_oldest_supported_python_and_the_one_of_the_binaries(self):
        readme = read('README.md')
        oldest = re.search(r'Python \*\*(\d+\.\d+) or newer\*\*', readme).group(1)
        test_job = job_block(self.tests_yml, 'test')                                  # the matrix of the main job, not of the other jobs
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

    def test_python_3_8_and_3_9_have_a_job_that_is_allowed_to_fail_and_it_is_the_only_one(self):
        job = job_block(self.tests_yml, 'best-effort')
        self.assertEqual({'3.8', '3.9'}, set(re.findall(r'^\s*-\s*"(\d+\.\d+)"', job, re.M)))
        self.assertRegex(job, r'(?m)^    continue-on-error: true$')
        self.assertIn('timeout-minutes:', job)
        self.assertRegex(job, r'(?m)^      fail-fast: false$')            # a failure on 3.8 must not cancel the run on 3.9
        self.assertRegex(job, r'(?m)^    runs-on: ubuntu-24\.04$')         # ubuntu-latest could not provide Python 3.9
        self.assertEqual(1, self.tests_yml.count('continue-on-error'), 'only the job for the best effort versions may fail without failing the run')
        for other in ('test', 'required-packages-only'):
            self.assertNotIn('continue-on-error', job_block(self.tests_yml, other))
        main_versions = re.findall(r'"(\d+\.\d+)"', job_block(self.tests_yml, 'test'))
        self.assertFalse({'3.8', '3.9'} & set(main_versions), 'the main matrix must not carry them: a failure there would fail the run')

    def test_the_readme_calls_python_3_8_and_3_9_best_effort(self):
        lines = [l for l in read('README.md').splitlines() if '3.8' in l and '3.9' in l]
        self.assertEqual(2, len(lines), 'the table and the list of requirements both say what is true of Python 3.8 and 3.9')
        for line in lines:
            self.assertIn('best effort', line)
            self.assertIn('allowed to fail', line)

    def test_the_test_workflow_installs_from_the_requirements_files(self):
        self.assertIn('-r requirements-dev.txt', self.tests_yml)
        self.assertNotRegex(self.tests_yml, r'pip install (?!-r|--upgrade)\w')   # no package list that could drift

    def test_one_job_has_only_the_required_packages(self):
        job = job_block(self.tests_yml, 'required-packages-only')
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


@unittest.skipUnless(os.path.isfile(os.path.join(ROOT, '.github', 'dependabot.yml')), 'no .github/dependabot.yml next to the tests')
class DependabotTests(unittest.TestCase):
    def setUp(self):
        self.text = read('.github', 'dependabot.yml')

    def test_it_is_valid_yaml_of_version_2(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML is not installed')
        data = yaml.safe_load(self.text)
        self.assertEqual(2, data['version'])
        self.assertEqual(1, len(data['updates']))

    def test_it_checks_the_github_actions_of_the_workflows_once_a_month(self):
        self.assertRegex(self.text, r'(?m)^  - package-ecosystem: github-actions$')
        self.assertRegex(self.text, r'(?m)^    directory: /$')            # /  means .github/workflows
        self.assertRegex(self.text, r'(?m)^      interval: monthly$')

    def test_it_waits_14_days_after_a_release(self):
        self.assertRegex(self.text, r'(?m)^    cooldown:\n      default-days: 14$')

    def test_the_yaml_values_are_those_of_the_text_checks(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML is not installed')
        update = yaml.safe_load(self.text)['updates'][0]
        self.assertEqual(('github-actions', '/', 'monthly', 14),
                         (update['package-ecosystem'], update['directory'], update['schedule']['interval'], update['cooldown']['default-days']))


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
