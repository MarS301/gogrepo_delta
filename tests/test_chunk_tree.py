"""fetch_chunk_tree: gets the checksum data (an XML 'chunk tree') of a file from GOG, or None if there is none.

GOG is replaced by a fake `request`; every way out of the function is covered, including the one that used to raise NameError."""
import unittest
from unittest import mock

import requests

import _bootstrap  # noqa: F401
import gogrepo_delta as g

XML = b'<file name="a.exe"><chunk id="0" from="0" to="9" method="md5">abc</chunk></file>'


class Response(object):
    def __init__(self, url, content=XML):
        self.url, self.content = url, content


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError('%d error' % status, response=response)


class ChunkTreeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.noted = []
        self.answer = Response('unused')
        self.patches = [mock.patch.object(g, 'request', self.fake_request),
                        mock.patch.object(g, 'note_summarised', lambda key, item, message: self.noted.append((key, item, message)))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_request(self, session, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer

    def no_md5_notes(self):
        # (an address in the old style without 'prefix' is also noted, under another key, by the code that builds the xml address)
        return [note for note in self.noted if note[0] == 'no md5 data']

    def run_it(self, url, api_downlink=None):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            result = g.fetch_chunk_tree(Response(url), 'session', api_downlink)
            g.info('end of test')
        return result, '\n'.join(logs.output)

    # --- files that have no checksum data ---

    def test_file_types_without_checksums_are_not_asked_for(self):
        for name in ('manual.pdf', 'extra.zip', 'cover.JPG', 'big.003'):
            self.calls[:] = []
            result, log = self.run_it('https://cdn.example/files/%s?token=1' % name)
            self.assertIsNone(result, name)
            self.assertEqual(self.calls, [], name)

    # --- with the download link of the product API ---

    def test_checksum_address_from_the_api_link_gives_the_tree(self):
        with mock.patch.object(g, 'fetch_checksum_url', return_value='https://cdn.example/checksums/a.xml'):
            result, log = self.run_it('https://cdn.example/files/setup.exe?token=1', api_downlink='https://api.example/downlink/1')
        self.assertEqual(result.tag, 'file')
        self.assertEqual(result[0].get('method'), 'md5')
        self.assertEqual(self.calls, [('https://cdn.example/checksums/a.xml', {'quiet_statuses': (404,)})])

    def test_an_api_link_without_a_checksum_address_warns_and_gives_none(self):
        with mock.patch.object(g, 'fetch_checksum_url', return_value=None):
            result, log = self.run_it('https://cdn.example/files/setup%20game.exe?token=1', api_downlink='https://api.example/d/1')
        self.assertIsNone(result)
        self.assertIn('no checksum URL found for setup game.exe', log)
        self.assertEqual(self.calls, [])

    def test_an_error_while_asking_the_api_link_is_reported_with_the_file_name(self):
        with mock.patch.object(g, 'fetch_checksum_url', side_effect=http_error(500)):
            result, log = self.run_it('https://cdn.example/files/setup%20game.exe?token=1', api_downlink='https://api.example/d/1')
        self.assertIsNone(result)
        self.assertIn('invalid downlink found for setup game.exe', log)
        self.assertIn('unexpected error fetching md5 data for setup game.exe', log)

    # --- manifests made before the api link was stored ---

    def test_without_an_api_link_and_without_signature_the_xml_address_is_used(self):
        result, log = self.run_it('https://cdn.example/files/setup.exe?token=1')
        self.assertEqual(result.tag, 'file')
        self.assertEqual(self.calls[0][0], g.append_xml_extension_to_url_path('https://cdn.example/files/setup.exe?token=1'))
        self.assertTrue(self.calls[0][0].split('?')[0].endswith('.xml'))

    def test_without_an_api_link_and_with_a_signed_address_it_warns_with_the_file_name_and_gives_none(self):
        # this used to raise NameError (an undefined name in the warning), which ended the downloader thread
        url = 'https://cdn.example/files/setup%20game.exe?wsSecret=a&wsTime=1&prefix=p'
        result, log = self.run_it(url)
        self.assertIsNone(result)
        self.assertIn('signed prefix required to fetch checksum data for setup game.exe but secret could not be retrieved', log)
        self.assertEqual(self.calls, [])

    def test_a_partly_signed_address_is_not_taken_for_a_signed_one(self):
        result, log = self.run_it('https://cdn.example/files/setup.exe?wsSecret=a&wsTime=1')
        self.assertEqual(result.tag, 'file')

    # --- errors that are caught ---

    def test_no_checksum_file_on_the_server_is_noted_for_the_summary(self):
        self.answer = http_error(404)
        result, log = self.run_it('https://cdn.example/files/setup%20game.exe?token=1')
        self.assertIsNone(result)
        self.assertEqual(self.no_md5_notes(), [('no md5 data', 'setup game.exe', g.NO_MD5_MESSAGE)])
        self.assertNotIn('unexpected error', log)

    def test_any_other_http_error_is_a_warning(self):
        self.answer = http_error(500)
        result, log = self.run_it('https://cdn.example/files/setup.exe?token=1')
        self.assertIsNone(result)
        self.assertEqual(self.no_md5_notes(), [])
        self.assertIn('unexpected error fetching md5 data for', log)

    def test_xml_that_cannot_be_read_is_a_warning(self):
        self.answer = Response('x', content=b'<file><chunk')
        result, log = self.run_it('https://cdn.example/files/setup.exe?token=1')
        self.assertIsNone(result)
        self.assertIn('xml parsing error occurred trying to get md5 data for', log)

    def test_a_lost_connection_is_a_warning_that_says_to_retry_later(self):
        self.answer = requests.exceptions.ConnectionError('reset')
        result, log = self.run_it('https://cdn.example/files/setup.exe?token=1')
        self.assertIsNone(result)
        self.assertIn('unexpected connection error fetching md5 data for', log)
        self.assertIn('retry in 24 hours', log)

    def test_unreadable_content_is_a_warning_that_says_to_retry_later(self):
        self.answer = requests.exceptions.ContentDecodingError('bad gzip')
        result, log = self.run_it('https://cdn.example/files/setup.exe?token=1')
        self.assertIsNone(result)
        self.assertIn('unexpected content decoding error fetching md5 data for', log)
        self.assertIn('retry in 24 hours', log)

    def test_an_error_that_is_not_expected_is_not_hidden(self):
        self.answer = RuntimeError('a real bug')
        with self.assertRaises(RuntimeError):
            g.fetch_chunk_tree(Response('https://cdn.example/files/setup.exe?token=1'), 'session', None)


class WorkerSurvivesTests(unittest.TestCase):
    def test_no_name_in_the_function_is_used_without_being_defined(self):
        """A check of the kind that would have caught the bug: every name the function uses exists."""
        import dis
        code = g.fetch_chunk_tree.__code__
        defined = set(code.co_varnames) | set(vars(g)) | set(vars(__builtins__) if isinstance(__builtins__, dict) is False else __builtins__)
        used = {ins.argval for ins in dis.get_instructions(code) if ins.opname in ('LOAD_GLOBAL', 'LOAD_NAME')}
        self.assertEqual(sorted(name for name in used if name not in defined), [])


if __name__ == '__main__':
    unittest.main()
