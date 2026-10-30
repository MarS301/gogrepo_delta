import unittest
import _bootstrap  # noqa: F401
from gogrepo_delta import AttrDict


class AttrDictTests(unittest.TestCase):
    def test_keys_readable_as_attributes(self):
        d = AttrDict(id=7, title='x')
        self.assertEqual((d.id, d.title), (7, 'x'))

    def test_attribute_assignment_writes_the_item(self):
        d = AttrDict()
        d.name = 'a.exe'
        self.assertEqual(d['name'], 'a.exe')

    def test_missing_attribute_raises_attribute_error(self):
        d = AttrDict(a=1)
        with self.assertRaises(AttributeError):
            d.missing
        self.assertFalse(hasattr(d, 'missing'))        # manifest code relies on try/except AttributeError

    def test_behaves_like_a_dict(self):
        d = AttrDict(a=1, b=2)
        self.assertIsInstance(d, dict)
        self.assertEqual(d, {'a': 1, 'b': 2})
        self.assertEqual(sorted(d), ['a', 'b'])

    def test_copy_is_a_plain_dict_that_can_be_rewrapped(self):
        # handle_game_updates does AttrDict(**old.copy())
        original = AttrDict(a=1)
        copied = original.copy()
        self.assertIs(type(copied), dict)
        rewrapped = AttrDict(**copied)
        rewrapped.a = 2
        self.assertEqual(original.a, 1)


if __name__ == '__main__':
    unittest.main()
