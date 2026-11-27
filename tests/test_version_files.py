"""The version of the script is written in three places that must agree: `__version__` in the script and the two places in README.md (the badge and the "Current version" row).
A patch that raised only the script's version left README.md one version behind (0.5.92), and nothing noticed."""
import os
import re
import unittest

import _bootstrap  # noqa: F401
import gogrepo_delta as g

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ReadmeVersionTests(unittest.TestCase):
    def readme(self):
        with open(os.path.join(ROOT, 'README.md'), encoding='utf-8') as f:
            return f.read()

    def test_the_badge_shows_the_version_of_the_script(self):
        self.assertEqual(re.findall(r'img\.shields\.io/badge/version-([0-9.]+)-', self.readme()), [g.__version__])

    def test_the_current_version_row_shows_the_version_of_the_script(self):
        self.assertEqual(re.findall(r'\*\*Current version\*\* \| `v([0-9.]+)`', self.readme()), [g.__version__])


if __name__ == '__main__':
    unittest.main()
