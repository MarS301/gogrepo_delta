import gc
import hashlib
import os
import shutil
import tempfile
import unittest
import warnings
import _bootstrap  # noqa: F401
import gogrepo_delta as g


class HashFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def make(self, data):
        path = os.path.join(self.dir, 'f.bin')
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def test_matches_md5_for_empty_small_and_multi_block_files(self):
        for data in (b'', b'abc', b'x' * 65536, b'y' * 65537, os.urandom(300000)):
            self.assertEqual(g.hashfile(self.make(data)), hashlib.md5(data).hexdigest(), len(data))

    def test_works_with_a_custom_block_size(self):
        data = os.urandom(10000)
        self.assertEqual(g.hashfile(self.make(data), blocksize=7), hashlib.md5(data).hexdigest())

    def test_the_file_is_closed_afterwards(self):
        path = self.make(b'data')
        with warnings.catch_warnings():
            warnings.simplefilter('error', ResourceWarning)
            g.hashfile(path)
            gc.collect()
        os.remove(path)                                  # also impossible on Windows while a handle is still open

    def test_missing_file_raises(self):
        with self.assertRaises(OSError):
            g.hashfile(os.path.join(self.dir, 'does-not-exist'))


if __name__ == '__main__':
    unittest.main()
