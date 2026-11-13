"""Entry 0.5.60: the `updated` column of the CSV export is two columns, the update date and the update time in UTC, so that a spreadsheet can show
them the way of the user's language; and the text of a refused price is GOG's message, not raw JSON cut off."""
import csv
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import requests

import _bootstrap  # noqa: F401
import gogrepo_delta as g
from test_clean_target import game


class SplitTests(unittest.TestCase):
    def test_a_stamp_with_an_offset_is_converted_to_utc(self):
        self.assertEqual(g.split_update_time('2026-06-23T18:59:00+02:00'), ('2026-06-23', '16:59:00'))
        self.assertEqual(g.split_update_time('2026-06-23T18:59:00+0200'), ('2026-06-23', '16:59:00'))

    def test_the_date_changes_when_the_offset_moves_the_time_over_midnight(self):
        self.assertEqual(g.split_update_time('2026-06-23T00:30:00+05:30'), ('2026-06-22', '19:00:00'))
        self.assertEqual(g.split_update_time('2026-06-23T23:30:00-03:00'), ('2026-06-24', '02:30:00'))
        self.assertEqual(g.split_update_time('2025-12-31T23:30:00-03:00'), ('2026-01-01', '02:30:00'))

    def test_utc_stamps_and_stamps_without_a_zone_stay_as_they_are(self):
        for text in ('2020-03-12T11:23:45+00:00', '2020-03-12T11:23:45Z', '2020-03-12T11:23:45', '2020-03-12 11:23:45', '2020-03-12T11:23:45.123456+00:00'):
            self.assertEqual(g.split_update_time(text), ('2020-03-12', '11:23:45'), text)

    def test_the_seconds_may_be_missing(self):
        self.assertEqual(g.split_update_time('2020-03-12T11:23'), ('2020-03-12', '11:23:00'))

    def test_what_is_no_stamp_comes_back_as_the_date_column_without_a_time(self):
        self.assertEqual(g.split_update_time('2021'), ('2021', ''))
        self.assertEqual(g.split_update_time('2020-03-12'), ('2020-03-12', ''))
        self.assertEqual(g.split_update_time('garbage'), ('garbage', ''))
        self.assertEqual(g.split_update_time('2026-13-45T25:61:00'), ('2026-13-45T25:61:00', ''))

    def test_nothing_gives_two_empty_cells(self):
        self.assertEqual(g.split_update_time(None), ('', ''))
        self.assertEqual(g.split_update_time(''), ('', ''))

    def test_the_formats_are_the_ones_every_spreadsheet_reads(self):
        date, time = g.split_update_time('2026-06-23T18:59:00+02:00')
        self.assertRegex(date, r'^\d{4}-\d{2}-\d{2}$')
        self.assertRegex(time, r'^\d{2}:\d{2}:\d{2}$')


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        item = game('alpha')
        item.downloads[0].updated = '2026-06-23T18:59:00+02:00'
        item.extras[0].updated = None
        g.save_manifest([item])

    def rows(self, savedir=None):
        g.cmd_export('out.csv', savedir, ',')
        with open('out.csv', encoding='utf-8-sig', newline='') as f:
            return list(csv.reader(f))

    def test_two_columns_replace_the_updated_column(self):
        header = self.rows()[0]
        self.assertNotIn('updated', header)
        self.assertEqual(header[-2:], ['update date', 'update time (UTC)'])

    def test_the_cells_hold_the_date_and_the_utc_time(self):
        rows = self.rows()
        installer = [r for r in rows if r[3] == 'standalone'][0]
        self.assertEqual(installer[-2:], ['2026-06-23', '16:59:00'])

    def test_a_file_without_an_update_stamp_has_two_empty_cells(self):
        extra = [r for r in self.rows() if r[3] == 'extra'][0]
        self.assertEqual(extra[-2:], ['', ''])

    def test_the_on_disk_column_stays_the_last_one(self):
        header = self.rows(savedir=self.dir)[0]
        self.assertEqual(header[-3:], ['update date', 'update time (UTC)', 'on disk'])


class PriceTextTests(unittest.TestCase):
    def refuse(self, body):
        response = requests.Response()
        response.status_code = 400
        response._content = body.encode('utf-8')
        session = mock.Mock()
        with mock.patch.object(g, 'request', side_effect=requests.HTTPError('400', response=response)):
            with self.assertRaises(g.PriceRefused) as caught:
                g.fetch_wishlist_price(session, '1293804420', 'DE')
        return caught.exception.text

    def test_the_message_of_gog_is_shown_not_the_raw_json(self):
        body = json.dumps({'_links': {'self': {'href': '/api/products/1293804420/prices?countryCode=DE'}}, 'message': 'Product 1293804420 not found'})
        self.assertEqual(self.refuse(body), 'Product 1293804420 not found')

    def test_a_long_message_is_cut_and_made_printable(self):
        text = self.refuse(json.dumps({'message': '\x1b[2Jbad ' + 'x' * 500}))
        self.assertLessEqual(len(text), 120)
        self.assertNotIn('\x1b', text)

    def test_text_that_is_not_json_or_has_no_message_is_shown_as_it_is(self):
        self.assertEqual(self.refuse('Bad Request'), 'Bad Request')
        self.assertIn('bad product', self.refuse(json.dumps({'error': 'bad product'})))
        self.assertEqual(self.refuse('[1, 2]'), '[1, 2]')
        self.assertEqual(self.refuse(json.dumps({'message': ''})), '{"message": ""}')
        self.assertEqual(self.refuse(''), 'HTTP 400')


if __name__ == '__main__':
    unittest.main()
