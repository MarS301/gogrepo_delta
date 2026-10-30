import unittest
import _bootstrap  # noqa: F401
from gogrepo_delta import md5_xml_url, find_product_downlink

NEW_CDN = ('https://gog-cdn-fastly.gog.com/token=nva=1791549284~dirs=4~token=0bb2409895bad6e13f0f9'
           '/secure/witcher_3/goty/lang/patch_witcher3_de_goty_2.0.0.51.exe')


class Md5XmlUrlTests(unittest.TestCase):
    def test_token_in_path_url_just_gets_xml_appended(self):
        # The URL shape from the "Could not locate query param 'prefix'" log lines.
        self.assertEqual(md5_xml_url(NEW_CDN), (NEW_CDN + '.xml', False))

    def test_prefix_parameter_is_extended_too(self):
        url = 'https://cdn.example/secure/a.exe?prefix=secure/a.exe&wsTime=1&wsSecret=abc'
        self.assertEqual(md5_xml_url(url),
                         ('https://cdn.example/secure/a.exe.xml?prefix=secure/a.exe.xml&wsTime=1&wsSecret=abc', True))

    def test_other_query_parameters_are_kept(self):
        self.assertEqual(md5_xml_url('https://h/p?x=1'), ('https://h/p.xml?x=1', False))

    def test_parentheses_are_not_percent_encoded(self):
        self.assertEqual(md5_xml_url('https://h/secure/a%28b%29.exe'), ('https://h/secure/a(b).exe.xml', False))

    def test_encoded_slash_in_prefix_is_restored(self):
        url = 'https://h/secure/a.exe?prefix=secure%2Fa.exe'
        self.assertEqual(md5_xml_url(url), ('https://h/secure/a.exe.xml?prefix=secure/a.exe.xml', True))


class FindProductDownlinkTests(unittest.TestCase):
    LINKS = {('slug', '123'): 'https://api.example/downlink/1'}

    def test_found_by_last_two_path_segments(self):
        self.assertEqual(find_product_downlink(self.LINKS, 'https://www.gog.com/downloads/slug/123'),
                         'https://api.example/downlink/1')

    def test_trailing_slash_is_ignored(self):
        self.assertEqual(find_product_downlink(self.LINKS, 'https://www.gog.com/downloads/slug/123/'),
                         'https://api.example/downlink/1')

    def test_unknown_file(self):
        self.assertIsNone(find_product_downlink(self.LINKS, 'https://www.gog.com/downloads/slug/999'))

    def test_empty_inputs(self):
        self.assertIsNone(find_product_downlink({}, 'https://www.gog.com/downloads/slug/123'))
        self.assertIsNone(find_product_downlink(self.LINKS, None))
        self.assertIsNone(find_product_downlink(self.LINKS, ''))
        self.assertIsNone(find_product_downlink(None, 'https://www.gog.com/downloads/slug/123'))


if __name__ == '__main__':
    unittest.main()
