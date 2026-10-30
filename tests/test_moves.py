import os
import shutil
import tempfile
import unittest
import _bootstrap  # noqa: F401
from gogrepo_delta import move_with_increment_on_clash


class MoveWithIncrementOnClashTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.src = os.path.join(self.root, 'src')
        self.dst = os.path.join(self.root, 'orphan')
        os.makedirs(self.src)
        os.makedirs(self.dst)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def put(self, folder, name, text):
        with open(os.path.join(folder, name), 'w') as f:
            f.write(text)

    def read(self, folder, name):
        with open(os.path.join(folder, name)) as f:
            return f.read()

    def move(self, name):
        with self.assertLogs('gogrepoc', level='WARNING') if os.path.exists(os.path.join(self.dst, name)) else _Null():
            move_with_increment_on_clash(os.path.join(self.src, name), os.path.join(self.dst, name))

    def test_no_clash_moves_the_file_as_is(self):
        self.put(self.src, 'setup.exe', 'new')
        self.move('setup.exe')
        self.assertEqual(self.read(self.dst, 'setup.exe'), 'new')

    def test_clash_gets_a_counter_before_the_extension(self):
        self.put(self.src, 'setup.exe', 'new')
        self.put(self.dst, 'setup.exe', 'old')
        self.move('setup.exe')
        self.assertEqual(sorted(os.listdir(self.dst)), ['setup(1).exe', 'setup.exe'])
        self.assertEqual(self.read(self.dst, 'setup(1).exe'), 'new')
        self.assertEqual(self.read(self.dst, 'setup.exe'), 'old')

    def test_file_without_extension_no_longer_crashes(self):
        # Regression: used to raise IndexError (e.g. an orphaned README moved onto an existing README)
        self.put(self.src, 'README', 'new')
        self.put(self.dst, 'README', 'old')
        self.move('README')
        self.assertEqual(sorted(os.listdir(self.dst)), ['README', 'README(1)'])
        self.assertEqual(self.read(self.dst, 'README(1)'), 'new')

    def test_counter_keeps_increasing_until_a_free_name_is_found(self):
        for name in ('README', 'README(1)', 'README(2)'):
            self.put(self.dst, name, 'old')
        self.put(self.src, 'README', 'new')
        self.move('README')
        self.assertEqual(self.read(self.dst, 'README(3)'), 'new')

    def test_dotfile_clash(self):
        self.put(self.src, '.hidden', 'new')
        self.put(self.dst, '.hidden', 'old')
        self.move('.hidden')
        self.assertEqual(self.read(self.dst, '.hidden(1)'), 'new')

    def test_bin_set_part_numbers_stay_last(self):
        self.put(self.src, 'setup-1.bin', 'new')
        self.put(self.dst, 'setup-1.bin', 'old')
        self.move('setup-1.bin')
        self.assertEqual(self.read(self.dst, 'setup(1)-1.bin'), 'new')

    def test_existing_destination_directory_receives_the_source_inside_it(self):
        # Unchanged behaviour: for a directory destination shutil.move nests the source, no counter is added.
        os.makedirs(os.path.join(self.src, 'extras'))
        os.makedirs(os.path.join(self.dst, 'extras'))
        self.put(os.path.join(self.src, 'extras'), 'a.txt', 'x')
        move_with_increment_on_clash(os.path.join(self.src, 'extras'), os.path.join(self.dst, 'extras'))
        self.assertEqual(self.read(os.path.join(self.dst, 'extras', 'extras'), 'a.txt'), 'x')


class _Null(object):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


if __name__ == '__main__':
    unittest.main()
