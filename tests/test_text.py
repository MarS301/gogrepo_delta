import unittest
import _bootstrap  # noqa: F401
from gogrepo_delta import slugify, pretty_size, is_numeric_id


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify('Hello World!'), 'hello-world')

    def test_punctuation_removed_and_words_joined(self):
        self.assertEqual(slugify('Game: The Sequel (2nd Ed.)'), 'game-the-sequel-2nd-ed')

    def test_accents_folded_to_ascii_by_default(self):
        self.assertEqual(slugify('Ünïcödé  Täst'), 'unicode-tast')

    def test_allow_unicode_keeps_letters(self):
        self.assertEqual(slugify('Ünïcödé Täst', allow_unicode=True), 'ünïcödé-täst')
        self.assertEqual(slugify('日本語 title', allow_unicode=True), '日本語-title')

    def test_non_latin_dropped_without_allow_unicode(self):
        self.assertEqual(slugify('日本語 title'), 'title')

    def test_leading_and_trailing_dashes_underscores_and_spaces_stripped(self):
        self.assertEqual(slugify('  --a__b-- '), 'a__b')

    def test_repeated_dashes_and_spaces_collapse(self):
        self.assertEqual(slugify('a  -  b---c'), 'a-b-c')

    def test_path_characters_removed(self):
        self.assertEqual(slugify('a/b\\c:d*e?'), 'abcde')

    def test_non_strings_are_converted(self):
        self.assertEqual(slugify(123), '123')

    def test_empty(self):
        self.assertEqual(slugify(''), '')


class PrettySizeTests(unittest.TestCase):
    def test_bytes_have_no_decimals(self):
        self.assertEqual(pretty_size(0), '0B')
        self.assertEqual(pretty_size(1023), '1023B')

    def test_units_step_by_1024(self):
        self.assertEqual(pretty_size(1024), '1.00KB')
        self.assertEqual(pretty_size(1536), '1.50KB')
        self.assertEqual(pretty_size(5 * 1024 ** 2), '5.00MB')
        self.assertEqual(pretty_size(3 * 1024 ** 3), '3.00GB')
        self.assertEqual(pretty_size(2 * 1024 ** 4), '2.00TB')

    def test_terabytes_is_the_largest_unit(self):
        self.assertEqual(pretty_size(5000 * 1024 ** 4), '5000.00TB')


class IsNumericIdTests(unittest.TestCase):
    def test_numeric_strings(self):
        for value in ('1', '007', '-5', ' 7 '):
            self.assertTrue(is_numeric_id(value), value)

    def test_non_numeric_strings(self):
        for value in ('abc', '', '1.5', '12a'):
            self.assertFalse(is_numeric_id(value), value)

    def test_non_strings_are_not_ids_and_do_not_raise(self):
        for value in (None, [], {}, object()):
            self.assertFalse(is_numeric_id(value), repr(value))

    def test_numbers_are_ids(self):
        self.assertTrue(is_numeric_id(5))


if __name__ == '__main__':
    unittest.main()
