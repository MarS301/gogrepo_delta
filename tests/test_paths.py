import os
import unittest
import _bootstrap  # noqa: F401
from gogrepo_delta import path_preserving_split_ext, process_path, check_skip_file


class SplitExtTests(unittest.TestCase):
    def test_directory_is_preserved(self):
        path = os.path.join('games', 'witcher', 'setup.exe')
        self.assertEqual(path_preserving_split_ext(path), [os.path.join('games', 'witcher', 'setup'), '.exe'])

    def test_only_the_last_extension_is_split(self):
        self.assertEqual(path_preserving_split_ext('archive.tar.gz'), ['archive.tar', '.gz'])

    def test_dots_in_directory_names_are_ignored(self):
        path = os.path.join('v1.2', 'setup.exe')
        self.assertEqual(path_preserving_split_ext(path), [os.path.join('v1.2', 'setup'), '.exe'])

    def test_file_without_extension_has_empty_extension(self):
        self.assertEqual(path_preserving_split_ext('README'), ['README', ''])
        path = os.path.join('some.dir', 'README')
        self.assertEqual(path_preserving_split_ext(path), [path, ''])

    def test_leading_dot_is_not_an_extension(self):
        self.assertEqual(path_preserving_split_ext('.hidden'), ['.hidden', ''])
        self.assertEqual(path_preserving_split_ext('.hidden.txt'), ['.hidden', '.txt'])

    def test_trailing_dot_gives_a_bare_dot_extension(self):
        self.assertEqual(path_preserving_split_ext('file.'), ['file', '.'])


class ProcessPathTests(unittest.TestCase):
    def test_returns_extended_length_path_of_absolute_path(self):
        self.assertEqual(process_path('some_dir'), '\\\\?\\' + os.path.abspath('some_dir'))

    def test_relative_segments_are_resolved(self):
        self.assertEqual(process_path(os.path.join('a', '..', 'b')), '\\\\?\\' + os.path.abspath('b'))


class CheckSkipFileTests(unittest.TestCase):
    def test_returns_the_matching_pattern(self):
        self.assertEqual(check_skip_file('manual.pdf', ['*.txt', '*.pdf']), '*.pdf')

    def test_first_match_wins(self):
        self.assertEqual(check_skip_file('a.txt', ['a.*', '*.txt']), 'a.*')

    def test_no_match_returns_none(self):
        self.assertIsNone(check_skip_file('setup.exe', ['*.txt', 'readme*']))

    def test_no_patterns(self):
        self.assertIsNone(check_skip_file('setup.exe', []))


if __name__ == '__main__':
    unittest.main()
