import os
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as app
from gogrepo_delta import AttrDict


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.closed = False

    def close(self):
        self.closed = True


class ImageHandlingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = self.temp.name
        self.images = os.path.join(self.root, '!images')
        self.orphans = os.path.join(self.root, '!orphaned', '!images')
        os.makedirs(self.images)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as stream:
            stream.write(content)
        return path

    def read(self, path):
        with open(path, 'rb') as stream:
            return stream.read()

    def test_failed_replacement_keeps_existing_single_image(self):
        item = AttrDict(image_url='images.gog.com/new-cover')
        directory = os.path.join(self.images, 'image_url', 'images.gog.com')
        old = self.write(os.path.join(directory, 'old-cover.jpg'), b'old cover')
        with mock.patch.object(app, 'request', side_effect=OSError('network unavailable')):
            with self.assertRaises(OSError):
                app._download_image_from_item_key(None, item, 'image_url', self.images, self.orphans, False)
        self.assertEqual(self.read(old), b'old cover')

    def test_empty_response_keeps_existing_image_and_cleans_temp_file(self):
        item = AttrDict(image_url='images.gog.com/new-cover')
        old = self.write(os.path.join(self.images, 'image_url', 'images.gog.com', 'old.jpg'), b'old')
        response = FakeResponse(b'')
        with mock.patch.object(app, 'request', return_value=response):
            with self.assertRaises(IOError):
                app._download_image_from_item_key(None, item, 'image_url', self.images, self.orphans, False)
        self.assertEqual(self.read(old), b'old')
        self.assertTrue(response.closed)
        self.assertFalse(any(name.startswith('.gogrepo-image-') for _, _, files in os.walk(self.images) for name in files))

    def test_successful_replacement_is_atomic_and_old_image_is_cleaned_afterward(self):
        item = AttrDict(image_url='images.gog.com/new-cover')
        old = self.write(os.path.join(self.images, 'image_url', 'images.gog.com', 'old-cover.jpg'), b'old')
        response = FakeResponse(b'new image bytes')
        with mock.patch.object(app, 'request', return_value=response):
            app._download_image_from_item_key(None, item, 'image_url', self.images, self.orphans, False)
        new = os.path.join(self.images, 'image_url', 'images.gog.com', 'new-cover.jpg')
        self.assertEqual(self.read(new), b'new image bytes')
        self.assertFalse(os.path.exists(old))
        self.assertTrue(response.closed)

    def test_existing_current_image_still_allows_cleanup_of_obsolete_files(self):
        item = AttrDict(image_url='images.gog.com/current-cover')
        current = self.write(os.path.join(self.images, 'image_url', 'images.gog.com', 'current-cover.jpg'), b'current')
        old = self.write(os.path.join(self.images, 'image_url', 'images.gog.com', 'old-cover.jpg'), b'old')
        with mock.patch.object(app, 'request') as request_mock:
            app._download_image_from_item_key(None, item, 'image_url', self.images, self.orphans, False)
        request_mock.assert_not_called()
        self.assertEqual(self.read(current), b'current')
        self.assertFalse(os.path.exists(old))

    def test_clean_existing_moves_old_image_only_after_replacement_succeeds(self):
        item = AttrDict(image_url='images.gog.com/new-cover')
        old = self.write(os.path.join(self.images, 'image_url', 'images.gog.com', 'old-cover.jpg'), b'old')
        response = FakeResponse(b'new image')
        with mock.patch.object(app, 'request', return_value=response):
            app._download_image_from_item_key(None, item, 'image_url', self.images, self.orphans, True)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(any(os.path.isfile(os.path.join(root, name)) for root, _, files in os.walk(self.orphans) for name in files))

    def test_incomplete_background_metadata_does_not_prune_old_keys_or_old_files(self):
        item = AttrDict(bg_urls=AttrDict(Game='images.gog.com/new-bg'), bg_urls_complete=False)
        key_dir = os.path.join(self.images, 'bg_urls', app.slugify('Game', True))
        old = self.write(os.path.join(key_dir, 'images.gog.com', 'old-bg.jpg'), b'old background')
        with mock.patch.object(app, 'request', return_value=FakeResponse(b'new background')):
            app._download_image_from_item_keys(None, item, 'bg_urls', self.images, self.orphans, False,
                                               metadata_complete=False)
        self.assertEqual(self.read(old), b'old background')
        self.assertTrue(os.path.isfile(os.path.join(key_dir, 'images.gog.com', 'new-bg.jpg')))

    def test_complete_background_metadata_prunes_stale_keys_after_success(self):
        item = AttrDict(bg_urls=AttrDict(Current='images.gog.com/current-bg'), bg_urls_complete=True)
        old_dir = os.path.join(self.images, 'bg_urls', 'removed-key')
        old = self.write(os.path.join(old_dir, 'images.gog.com', 'removed.jpg'), b'old background')
        with mock.patch.object(app, 'request', return_value=FakeResponse(b'current background')):
            app._download_image_from_item_keys(None, item, 'bg_urls', self.images, self.orphans, False,
                                               metadata_complete=True)
        self.assertFalse(os.path.exists(old_dir))
        self.assertTrue(os.path.isfile(os.path.join(self.images, 'bg_urls', 'current', 'images.gog.com', 'current-bg.jpg')))

    def test_later_background_failure_prevents_earlier_key_cleanup(self):
        item = AttrDict(bg_urls=AttrDict(First='images.gog.com/new-first',
                                         Second='images.gog.com/new-second'), bg_urls_complete=True)
        first_dir = os.path.join(self.images, 'bg_urls', 'first', 'images.gog.com')
        old_first = self.write(os.path.join(first_dir, 'old-first.jpg'), b'old first')
        responses = [FakeResponse(b'new first'), OSError('second image failed')]
        with mock.patch.object(app, 'request', side_effect=responses):
            with self.assertRaises(OSError):
                app._download_image_from_item_keys(None, item, 'bg_urls', self.images, self.orphans, False,
                                                   metadata_complete=True)
        self.assertEqual(self.read(old_first), b'old first')

    def test_complete_empty_background_list_cleans_old_keys(self):
        item = AttrDict(bg_urls=AttrDict(), bg_urls_complete=True)
        old_dir = os.path.join(self.images, 'bg_urls', 'removed-key')
        old = self.write(os.path.join(old_dir, 'images.gog.com', 'removed.jpg'), b'old background')
        self.assertTrue(app._download_image_from_item_keys(None, item, 'bg_urls', self.images, self.orphans, False,
                                                            metadata_complete=True))
        self.assertFalse(os.path.exists(old_dir))
        self.assertFalse(os.path.exists(old))

    def test_failed_current_background_prevents_stale_key_cleanup(self):
        item = AttrDict(bg_urls=AttrDict(Current='images.gog.com/current-bg'), bg_urls_complete=True)
        old_dir = os.path.join(self.images, 'bg_urls', 'removed-key')
        old = self.write(os.path.join(old_dir, 'images.gog.com', 'removed.jpg'), b'old background')
        with mock.patch.object(app, 'request', side_effect=OSError('network failure')):
            with self.assertRaises(OSError):
                app._download_image_from_item_keys(None, item, 'bg_urls', self.images, self.orphans, False,
                                                   metadata_complete=True)
        self.assertEqual(self.read(old), b'old background')

    def test_image_path_traversal_is_rejected(self):
        item = AttrDict(image_url='../outside')
        with self.assertRaises(ValueError):
            app._download_image_from_item_key(None, item, 'image_url', self.images, self.orphans, False)
        self.assertFalse(os.path.exists(os.path.join(self.root, 'outside.jpg')))


if __name__ == '__main__':
    unittest.main()
