"""Entry 0.5.63: movies. `update -movies` puts GOG's movies into the manifest, with the video variants chosen by -moviequality; the movie
files belong to no operating system, their folder ends in -movie, `update` without -movies leaves them alone, `list` and `export` have a
media column. The three JSON files in tests/data/movies are real answers of GOG's account API (a movie list and two movie details)."""
import contextlib
import copy
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'movies')
MOVIE_LIBRARY = 'library_movies.json'
WITCHER, DELIVERANCE = 1636895344, 1161629383
DELIVERANCE_SLUG = 'deliverance_the_making_of_kingdom_come'


def load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)


def movie_details(movie_id):
    path = 'movieDetails_%d.json' % movie_id
    if os.path.exists(os.path.join(DATA, path)):
        return load(path)
    return dict(load('movieDetails_%d.json' % WITCHER), title='Movie %d' % movie_id,      # the other movies of the list: one video and no extras
                downloads=[dict(manualUrl='/downloads/movie_%d/en1video1' % movie_id, playerUrl='', name='Movie (720p)', size='1 GB')])


class FakeResponse(object):
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def fake_fetch_file_info(d, fetch_md5, save_md5_xml, session, product_api_context=None, diagnostic=False):
    d.name, d.size, d.md5 = d.manualUrl.rsplit('/', 1)[1] + '.bin', 1000, None


class FakeGog(object):
    """GOG's account API: one game, and the four movies of the real answer unless `movies` says otherwise."""
    def __init__(self, movies=None, details=None, interrupt_on=None):
        self.library_pages = {'1': dict(products=[dict(id=1000, slug='game_000', title='Game 0', category='RPG', image='//i/0', url='/game/game_000',
                                                       rating=40, updates=0)], totalPages=1),
                              '2': load(MOVIE_LIBRARY) if movies is None else movies}
        self.details = details or {}
        self.interrupt_on = interrupt_on
        self.requests = []

    def request(self, session, url, args=None, **kwargs):
        self.requests.append((url, dict(args or {})))
        if '/movieDetails/' in url:
            movie_id = int(url.rsplit('/', 1)[1].split('.')[0])
            if movie_id == self.interrupt_on:
                raise KeyboardInterrupt()
            return FakeResponse(copy.deepcopy(self.details.get(movie_id) or movie_details(movie_id)))
        if '/gameDetails/' in url:
            if int(url.rsplit('/', 1)[1].split('.')[0]) == self.interrupt_on:
                raise KeyboardInterrupt()
            return FakeResponse(dict(backgroundImage='', cdKey='', forumLink='', changelog='', releaseTimestamp=1500000000, messages=[],
                                     downloads=[['English', {'windows': [dict(manualUrl='/downloads/game_000/en1installer0', name='Game', version='1', date='', size='1 MB')]}]],
                                     galaxyDownloads=[], extras=[], dlcs=[]))
        return FakeResponse(copy.deepcopy(self.library_pages[args['mediaType']]))

    def urls(self, part):
        return [url for url, args in self.requests if part in url]

    def library_types(self):
        return [args['mediaType'] for url, args in self.requests if 'getFilteredProducts' in url]


class Base(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset('update')

    @contextlib.contextmanager
    def gog(self, **kwargs):
        fake = FakeGog(**kwargs)
        self.fetched = []

        def tracking(d, *a, **k):
            self.fetched.append(d.manualUrl.rsplit('/', 1)[1])
            return fake_fetch_file_info(d, *a, **k)
        with mock.patch.object(g, 'request', fake.request), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})), \
                mock.patch.object(g, 'fetch_file_info', tracking):
            yield fake

    def update(self, movies=True, moviequality='best', os_list=('windows',), lang_list=('en',), full=False, ids=(), installers='both', resumemode='resume'):
        skipknown, updateonly, partial = (False, False, False) if full else (True, True, True)
        g.cmd_update(list(os_list), list(lang_list), skipknown, updateonly, partial, list(ids), [], False, installers, resumemode,
                     False, False, False, False, False, False, False, movies=movies, moviequality=moviequality)

    def manifest(self):
        return {game.title: game for game in g.load_manifest()}

    def files(self, game):
        return sorted(d.name for d in game.downloads)


class QualityTests(unittest.TestCase):
    def test_the_ranking_of_the_labels(self):
        rank = g.movie_quality_rank
        self.assertEqual([rank('1080p'), rank('720p'), rank('576p'), rank('480p'), rank('396p')], [1080, 720, 576, 480, 396])
        self.assertEqual([rank('4k'), rank('4K'), rank('2k'), rank('8k'), rank('dvd'), rank('DVD')], [2160, 2160, 1440, 4320, 576, 576])
        self.assertEqual([rank(''), rank(None), rank('hd'), rank('1080'), rank('3k')], [0, 0, 0, 0, 0])

    def test_sizes_as_gog_writes_them(self):
        self.assertEqual(g.parse_size_text('1 MB'), 1024 ** 2)
        self.assertEqual(g.parse_size_text('1.4 GB'), int(1.4 * 1024 ** 3))
        self.assertEqual(g.parse_size_text('675 MB'), 675 * 1024 ** 2)
        self.assertEqual(g.parse_size_text('1,5 gb'), int(1.5 * 1024 ** 3))
        for bad in ('', None, 'big', '12', 'GB'):
            self.assertEqual(g.parse_size_text(bad), 0, bad)

    def test_valid_values(self):
        self.assertEqual(g.parse_movie_quality('best'), ['best'])
        self.assertEqual(g.parse_movie_quality('ALL'), ['all'])
        self.assertEqual(g.parse_movie_quality(' 1080p , 720p ,'), ['1080p', '720p'])
        self.assertEqual(g.parse_movie_quality('max:1080p,dvd'), ['max:1080p', 'dvd'])
        self.assertEqual(g.parse_movie_quality('396p'), ['396p'])

    def test_invalid_values_say_why(self):
        for bad, words in (('', 'needs a value'), (None, 'needs a value'), (' , ', 'needs a value'), ('max:', 'max:'), ('max:best', 'not a quality I can compare'),
                           ('max:foo', 'foo'), ('1080 p', 'not a quality name'), ('720p;x', 'not a quality name'), ('<=1080p', 'not a quality name')):
            with self.assertRaises(ValueError) as caught:
                g.parse_movie_quality(bad)
            self.assertIn(words, str(caught.exception), bad)

    def videos(self, *labels_and_sizes):
        return [{'label': label, 'rank': g.movie_quality_rank(label), 'size_bytes': size} for label, size in labels_and_sizes]

    def labels(self, chosen):
        return [v['label'] for v in chosen]

    def test_best_is_the_highest_resolution_and_a_tie_goes_to_the_bigger_file(self):
        videos = self.videos(('720p', 5), ('4k', 20), ('1080p', 10), ('dvd', 1))
        self.assertEqual(self.labels(g.choose_movie_videos(videos, ['best'])[0]), ['4k'])
        tie = self.videos(('1080p', 5), ('1080p', 9))
        self.assertEqual([v['size_bytes'] for v in g.choose_movie_videos(tie, ['best'])[0]], [9])

    def test_all_gives_every_variant(self):
        videos = self.videos(('720p', 5), ('1080p', 10))
        self.assertEqual(self.labels(g.choose_movie_videos(videos, ['all'])[0]), ['720p', '1080p'])

    def test_a_list_is_an_order_of_preference(self):
        videos = self.videos(('720p', 5), ('4k', 20), ('1080p', 10))
        self.assertEqual(self.labels(g.choose_movie_videos(videos, ['1080p', '720p'])[0]), ['1080p'])
        self.assertEqual(self.labels(g.choose_movie_videos(videos, ['576p', '720p', '1080p'])[0]), ['720p'])
        self.assertEqual(g.choose_movie_videos(videos, ['720p'])[1], False)

    def test_max_is_the_best_that_is_not_above(self):
        videos = self.videos(('720p', 5), ('4k', 20), ('1080p', 10))
        self.assertEqual(self.labels(g.choose_movie_videos(videos, ['max:1080p'])[0]), ['1080p'])
        self.assertEqual(self.labels(g.choose_movie_videos(videos, ['max:900p'])[0]), ['720p'])

    def test_when_nothing_fits_the_best_is_taken_and_it_is_said(self):
        videos = self.videos(('720p', 5), ('4k', 20))
        self.assertEqual(g.choose_movie_videos(videos, ['480p']), ([videos[1]], True))
        self.assertEqual(g.choose_movie_videos(videos, ['max:480p']), ([videos[1]], True))
        self.assertEqual(g.choose_movie_videos([], ['best']), ([], False))

    def test_unknown_labels_are_ordered_by_size_and_can_be_asked_for_by_name(self):
        videos = self.videos(('hd', 5), ('weird', 9))
        self.assertEqual(self.labels(g.choose_movie_videos(videos, ['best'])[0]), ['weird'])
        self.assertEqual(self.labels(g.choose_movie_videos(videos, ['hd'])[0]), ['hd'])


class PrepareTests(unittest.TestCase):
    def prepare(self, movie_id, tokens, langs=('en',)):
        return g.prepare_movie_downloads(movie_details(movie_id)['downloads'], list(langs), tokens, 'Movie')

    def names(self, result):
        return [d['manualUrl'].rsplit('/', 1)[1] for language, by_os in result for d in by_os[g.MOVIE_OS_TYPE]]

    def test_best_of_the_concert_is_the_4k_file_only(self):
        result, codes = self.prepare(WITCHER, ['best'])
        self.assertEqual(self.names(result), ['en1video4'])
        self.assertEqual(codes, ['en'])
        self.assertEqual(result[0][0], 'English')
        self.assertEqual(list(result[0][1]), [g.MOVIE_OS_TYPE])

    def test_the_files_have_what_filter_downloads_needs(self):
        entry = self.prepare(WITCHER, ['best'])[0][0][1][g.MOVIE_OS_TYPE][0]
        self.assertEqual(entry['version'], '')
        for key in ('manualUrl', 'name', 'size', 'playerUrl'):
            self.assertIn(key, entry)

    def test_all_four_variants_of_the_concert(self):
        self.assertEqual(self.names(self.prepare(WITCHER, ['all'])[0]), ['en1video1', 'en1video2', 'en1video3', 'en1video4'])

    def test_a_preference_list_picks_the_first_that_exists(self):
        self.assertEqual(self.names(self.prepare(WITCHER, ['1080p', '720p'])[0]), ['en1video3'])

    def test_the_subtitles_are_always_taken_with_the_chosen_video(self):
        self.assertEqual(self.names(self.prepare(DELIVERANCE, ['best'])[0]), ['en1patch1', 'en1video1'])
        self.assertEqual(self.names(self.prepare(DELIVERANCE, ['720p'])[0]), ['en1patch1', 'en1video2'])
        self.assertEqual(self.names(self.prepare(DELIVERANCE, ['all'])[0]), ['en1patch1', 'en1video1', 'en1video2'])

    def test_the_quality_is_read_from_the_name_in_parentheses(self):
        self.assertEqual(self.names(self.prepare(DELIVERANCE, ['max:720p'])[0]), ['en1patch1', 'en1video2'])

    def raw(self, *keys):
        return [dict(manualUrl='/downloads/m/%s' % key, name='M (%s)' % ('1080p' if 'video' in key else 'x'), size='1 GB') for key in keys]

    def test_a_movie_without_the_wanted_language_gives_english(self):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            result, codes = g.prepare_movie_downloads(self.raw('en1video1', 'de1video1'), ['fr'], ['best'], 'M')
        self.assertEqual(codes, ['en'])
        self.assertTrue(any('not offered in the wanted language' in r.getMessage() and 'English' in r.getMessage() for r in logs.records))

    def test_the_wanted_language_wins_over_english(self):
        result, codes = g.prepare_movie_downloads(self.raw('en1video1', 'de1video1'), ['de'], ['best'], 'M')
        self.assertEqual(codes, ['de'])
        self.assertEqual(self.names(result), ['de1video1'])

    def test_several_wanted_languages_each_get_their_own_variants(self):
        result, codes = g.prepare_movie_downloads(self.raw('en1video1', 'de1video1', 'fr1video1'), ['de', 'en'], ['best'], 'M')
        self.assertEqual(sorted(codes), ['de', 'en'])
        self.assertEqual(sorted(self.names(result)), ['de1video1', 'en1video1'])

    def test_without_english_either_what_is_offered_is_taken(self):
        result, codes = g.prepare_movie_downloads(self.raw('fr1video1', 'de1video1'), ['pl'], ['best'], 'M')
        self.assertEqual(sorted(codes), ['de', 'fr'])

    def test_an_unknown_language_code_is_skipped_with_a_warning(self):
        with self.assertLogs('gogrepoc', level='WARNING') as logs:
            result, codes = g.prepare_movie_downloads(self.raw('zz1video1', 'en1video1'), ['en'], ['best'], 'M')
        self.assertEqual(self.names(result), ['en1video1'])
        self.assertIn("unknown language code 'zz'", logs.records[0].getMessage())

    def test_an_address_in_an_unknown_form_is_taken_as_an_english_file(self):
        raw = [dict(manualUrl='/downloads/m/81856', name='poster', size='1 MB')]
        result, codes = g.prepare_movie_downloads(raw, ['en'], ['best'], 'M')
        self.assertEqual((codes, self.names(result)), (['en'], ['81856']))

    def test_nothing_in_nothing_out(self):
        self.assertEqual(g.prepare_movie_downloads(None, ['en'], ['best']), ([], []))
        self.assertEqual(g.prepare_movie_downloads([], ['en'], ['best']), ([], []))

    def test_a_variant_without_a_quality_in_its_name_can_still_be_chosen(self):
        raw = [dict(manualUrl='/downloads/m/en1video1', name='Movie', size='1 GB')]
        self.assertEqual(self.names(g.prepare_movie_downloads(raw, ['en'], ['best'], 'M')[0]), ['en1video1'])

    def test_the_input_is_not_changed(self):
        details = movie_details(DELIVERANCE)
        before = copy.deepcopy(details['downloads'])
        g.prepare_movie_downloads(details['downloads'], ['en'], ['best'], 'M')
        self.assertEqual(details['downloads'], before)


class HelperTests(unittest.TestCase):
    def entry(self, os_type, lang='English'):
        return SimpleNamespace(os_type=os_type, lang=lang)

    def test_a_movie_file_belongs_to_every_os_selection(self):
        self.assertTrue(g.os_selected(self.entry('video'), ['windows']))
        self.assertTrue(g.os_selected(self.entry('video'), []))
        self.assertTrue(g.os_selected(self.entry('windows'), ['windows', 'linux']))
        self.assertFalse(g.os_selected(self.entry('linux'), ['windows']))

    def test_movie_files_pass_the_language_filter_with_and_without_a_fallback(self):
        movie, game_en, game_de = self.entry('video', 'English'), self.entry('windows', 'English'), self.entry('windows', 'Deutsch')
        self.assertEqual(g.filter_languages([movie, game_en, game_de], ['Deutsch']), [movie, game_de])
        self.assertEqual(g.filter_languages([movie, game_en, game_de], ['Deutsch'], 'English'), [movie, game_de])
        self.assertEqual(g.filter_languages([movie, game_en], ['Deutsch'], 'English'), [movie, game_en])

    def test_media_of(self):
        self.assertEqual(g.media_of(SimpleNamespace()), g.GOG_MEDIA_TYPE_GAME)
        self.assertEqual(g.media_of(SimpleNamespace(media_type=None)), g.GOG_MEDIA_TYPE_GAME)
        self.assertEqual(g.media_of(SimpleNamespace(media_type='2')), g.GOG_MEDIA_TYPE_MOVIE)

    def test_no_place_filters_files_by_os_without_the_movie_rule(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gogrepo_delta.py'), encoding='utf-8') as f:
            source = f.read()
        self.assertNotIn('game_item.os_type in os_list', source)


class UpdateTests(Base):
    def test_without_movies_only_the_games_are_asked_for(self):
        with self.gog() as fake:
            self.update(movies=False)
        self.assertEqual(fake.library_types(), ['1'])
        self.assertEqual(fake.urls('movieDetails'), [])
        self.assertEqual(list(self.manifest()), ['game_000'])

    def test_with_movies_the_games_come_first_and_then_the_movies(self):
        with self.gog() as fake:
            self.update()
        self.assertEqual(fake.library_types(), ['1', '2'])
        self.assertEqual(sorted(self.manifest()), sorted(['game_000', 'deliverance_the_making_of_kingdom_come', 'the_art_of_playing',
                                                          'the_gamers_directors_cut', 'video_game_show_the_witcher_3_wild_hunt_concert']))
        self.assertEqual(len(fake.urls('/movieDetails/')), 4)
        self.assertEqual(len(fake.urls('/gameDetails/')), 1)

    def test_the_movie_item_has_its_own_media_type_and_folder(self):
        with self.gog(details={}) as fake:
            self.update()
        movie = self.manifest()[DELIVERANCE_SLUG]
        self.assertEqual((movie.media_type, movie.title, movie.folder_name), ('2', DELIVERANCE_SLUG, DELIVERANCE_SLUG + '-movie'))
        game = self.manifest()['game_000']
        self.assertEqual((game.media_type, game.folder_name), ('1', 'game_000'))

    def test_the_best_video_and_the_subtitles_are_in_the_manifest_without_an_os(self):
        with self.gog() as fake:
            self.update()
        movie = self.manifest()[DELIVERANCE_SLUG]
        self.assertEqual(self.files(movie), ['en1patch1.bin', 'en1video1.bin'])
        self.assertEqual({(d.os_type, d.lang) for d in movie.downloads}, {(g.MOVIE_OS_TYPE, 'English')})
        self.assertEqual(movie.galaxyDownloads, [])

    def test_only_the_chosen_files_are_asked_about(self):
        with self.gog():
            self.update()
        # Deliverance: the subtitles and the 1080p video (not the 720p one); the concert: the 4K video only
        self.assertEqual(sorted(self.fetched), sorted(['en1installer0', 'en1patch1', 'en1video1', '81856', 'en1video4', 'en1video1', 'en1video1']))

    def test_the_extras_of_a_movie_are_kept(self):
        with self.gog():
            self.update()
        movie = self.manifest()[DELIVERANCE_SLUG]
        self.assertEqual([x.name for x in movie.extras], ['81856.bin'])

    def test_the_quality_setting_decides(self):
        with self.gog():
            self.update(moviequality='720p')
        self.assertEqual(self.files(self.manifest()[DELIVERANCE_SLUG]), ['en1patch1.bin', 'en1video2.bin'])

    def test_the_quality_setting_all_takes_every_variant(self):
        with self.gog():
            self.update(moviequality='all')
        self.assertEqual(self.files(self.manifest()[DELIVERANCE_SLUG]), ['en1patch1.bin', 'en1video1.bin', 'en1video2.bin'])

    def test_movies_are_not_chosen_by_the_os(self):
        with self.gog():
            self.update(os_list=('linux',))
        self.assertEqual(self.files(self.manifest()[DELIVERANCE_SLUG]), ['en1patch1.bin', 'en1video1.bin'])
        self.assertEqual(self.files(self.manifest()['game_000']), [])           # the game has only a Windows installer

    def test_installers_galaxy_does_not_empty_a_movie(self):
        with self.gog():
            self.update(installers='galaxy')
        self.assertEqual(self.files(self.manifest()[DELIVERANCE_SLUG]), ['en1patch1.bin', 'en1video1.bin'])

    def test_a_movie_without_the_wanted_language_gives_the_english_files(self):
        with self.gog():
            self.update(lang_list=('de',))
        self.assertEqual(self.files(self.manifest()[DELIVERANCE_SLUG]), ['en1patch1.bin', 'en1video1.bin'])

    def test_ids_that_are_all_found_among_the_games_ask_for_no_movies(self):
        with self.gog() as fake:
            self.update(ids=['game_000'])
        self.assertEqual(fake.library_types(), ['1'])

    def test_a_movie_can_be_asked_for_by_its_slug(self):
        with self.gog() as fake:
            self.update(ids=[DELIVERANCE_SLUG])
        self.assertEqual(fake.library_types(), ['1', '2'])
        self.assertEqual(sorted(self.manifest()), [DELIVERANCE_SLUG])

    def test_a_full_update_without_movies_leaves_the_movies_of_the_manifest_alone(self):
        with self.gog():
            self.update()
            self.update(movies=False, full=True)
        self.assertIn(DELIVERANCE_SLUG, self.manifest())
        self.assertEqual(len(self.manifest()), 5)

    def test_the_message_says_that_the_movies_were_left(self):
        with self.gog():
            self.update()
        with self.gog(), self.assertLogs('gogrepoc', level='INFO') as logs:
            self.update(movies=False, full=True)
        self.assertTrue(any('4 movie(s) in the manifest are left as they are' in r.getMessage() for r in logs.records))

    def test_a_full_update_with_movies_removes_a_movie_that_is_gone_from_the_library(self):
        with self.gog():
            self.update()
        library = load(MOVIE_LIBRARY)
        library['products'] = [p for p in library['products'] if p['id'] != DELIVERANCE]
        with self.gog(movies=library):
            self.update(full=True)
        self.assertNotIn(DELIVERANCE_SLUG, self.manifest())
        self.assertEqual(len(self.manifest()), 4)

    def test_a_game_that_is_gone_is_still_removed_by_a_full_update_without_movies(self):
        with self.gog():
            self.update()
        with self.gog() as fake:
            fake.library_pages['1']['products'] = [dict(id=2000, slug='game_999', title='Game 9', category='RPG', image='//i/9', url='/game/game_999', rating=40, updates=0)]
            self.update(movies=False, full=True)
        self.assertNotIn('game_000', self.manifest())            # not in the library any more: removed
        self.assertIn('game_999', self.manifest())
        self.assertIn(DELIVERANCE_SLUG, self.manifest())         # not looked at: left

    def test_the_movie_settings_are_saved_with_the_resume_information_and_used_when_resuming(self):
        with self.gog(interrupt_on=1207665463), self.assertRaises(KeyboardInterrupt):
            self.update(moviequality='720p')
        properties = g.load_resume_manifest()[-1]
        self.assertEqual((properties['movies'], properties['moviequality']), (True, '720p'))
        with self.gog():
            self.update(movies=False, moviequality='best')            # the resumed run is started without them: the saved ones apply
        self.assertEqual(self.files(self.manifest()[DELIVERANCE_SLUG]), ['en1patch1.bin', 'en1video2.bin'])
        self.assertIn('the_art_of_playing', self.manifest())

    def test_an_old_resume_file_without_the_settings_means_no_movies(self):
        with self.gog(interrupt_on=1000), self.assertRaises(KeyboardInterrupt):
            self.update(movies=False)
        resume = g.load_resume_manifest()
        for key in ('movies', 'moviequality'):
            resume[-1].pop(key, None)                                 # a resume file of a version without movies
        g.save_resume_manifest(resume)
        with self.gog() as fake:
            self.update(movies=False)
        self.assertNotIn('2', fake.library_types())
        self.assertEqual(fake.urls('/movieDetails/'), [])
        self.assertEqual(list(self.manifest()), ['game_000'])

    def test_the_resume_pass_uses_the_saved_settings_and_then_the_request_runs_with_its_own(self):
        # entry 0.5.85: before, the restart after the resume pass dropped -movies and -moviequality, so this request fetched no movies at all
        with self.gog(interrupt_on=1000), self.assertRaises(KeyboardInterrupt):
            self.update(movies=False)                                 # the interrupted run had no movies
        resume = g.load_resume_manifest()
        for key in ('movies', 'moviequality'):
            resume[-1].pop(key, None)                                 # (a resume file of a version without movies: the pass has no movies either)
        g.save_resume_manifest(resume)
        with self.gog() as fake:
            self.update(movies=True, moviequality='720p')
        self.assertIn('/gameDetails/', fake.requests[0][0])           # the resume pass comes first and fetches no movie ...
        self.assertEqual(fake.library_types(), ['1', '2'])            # ... the shelves are read by the restart of this request, movies included
        self.assertEqual(self.files(self.manifest()[DELIVERANCE_SLUG]), ['en1patch1.bin', 'en1video2.bin'])      # with this request's -moviequality

    def test_a_resumed_update_with_movies_keeps_the_movies_of_the_request(self):
        with self.gog(interrupt_on=1000), self.assertRaises(KeyboardInterrupt):
            self.update(movies=False)                                 # an interrupted run without movies (its resume file says movies: false)
        self.assertEqual(g.load_resume_manifest()[-1]['movies'], False)
        with self.gog() as fake:
            self.update(movies=True, moviequality='720p')             # resumed by a request with movies
        self.assertEqual(fake.library_types(), ['1', '2'])
        self.assertEqual(self.files(self.manifest()[DELIVERANCE_SLUG]), ['en1patch1.bin', 'en1video2.bin'])
        self.assertIn('the_art_of_playing', self.manifest())

    def test_a_resumed_update_without_movies_leaves_the_movies_of_an_interrupted_run_alone(self):
        with self.gog():
            self.update(movies=True)                                  # the movies are in the manifest
        with self.gog(interrupt_on=1000), self.assertRaises(KeyboardInterrupt):
            self.update(movies=True, full=True)
        with self.gog() as fake:
            self.update(movies=False, full=True)                      # the resume pass finishes the interrupted run, the restart has no movies
        self.assertEqual(fake.library_types(), ['1'])                 # only the shelf of the games: the restart of this request has no movies
        self.assertIn(DELIVERANCE_SLUG, self.manifest())              # not looked at, so not removed

    def test_a_wrong_quality_stops_before_anything_is_fetched(self):
        with self.gog() as fake:
            with self.assertRaises(ValueError):
                self.update(moviequality='max:nonsense')
        self.assertEqual(fake.requests, [])


class NarrowingTests(Base):
    def test_a_movie_in_the_manifest_is_no_other_operating_system(self):
        with self.gog():
            self.update()
        found = g.update_narrowing(g.load_manifest(), ['windows'], ['en'], None, [], [])
        self.assertEqual(found.files, 0)
        self.assertEqual(found.os_types, set())


class ColumnTests(Base):
    def test_list_has_a_media_column(self):
        with self.gog():
            self.update()
        out, log = self.list_output()
        lines = out.splitlines()
        self.assertEqual(lines[0].split()[:4], ['ID', 'TITLE', 'NAME', 'MEDIA'])
        deliverance = [l for l in lines if DELIVERANCE_SLUG in l][0]
        self.assertIn(' movie ', deliverance)
        self.assertIn('vid', deliverance)
        game = [l for l in lines if 'game_000' in l][0]
        self.assertIn(' game ', game)

    def list_output(self, os_list=(), skipos_list=(), lang_list=(), skiplang_list=(), tags=(), skiptags=(), words=(), output_format='table', notags=False):
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_list(list(words), list(os_list), list(skipos_list), list(lang_list), list(skiplang_list), output_format, list(tags), list(skiptags), notags)
        return buffer.getvalue(), '\n'.join(r.getMessage() for r in logs.records)

    def tag_the_manifest(self, **tags_of):
        """Gives tag names to items of the manifest (by title); the movie is 'deliverance...', the game 'game_000'. Items not named get []."""
        items = g.load_manifest()
        for item in items:
            item.tag_names = list(tags_of.get(item.title, []))
        g.save_manifest(items)
        return items

    def test_list_tags_show_only_the_movies_that_are_tagged_movies(self):
        with self.gog():
            self.update()
        total = len(self.tag_the_manifest(**{DELIVERANCE_SLUG: ['Movies', 'Making of'], 'game_000': ['Favorites']}))
        out, log = self.list_output(tags=['movies'])                       # case does not matter
        self.assertIn(DELIVERANCE_SLUG, out)
        self.assertNotIn('game_000', out)
        self.assertEqual(len(out.splitlines()), 2)                         # the header and the movie: the other items have no tag
        self.assertIn('1 of %d games' % total, log)                        # the total is the whole manifest
        out, log = self.list_output(tags=['Making  of'])                   # an item with several tags is found by any of them
        self.assertIn(DELIVERANCE_SLUG, out)
        out, log = self.list_output(skiptags=['Movies'])
        self.assertNotIn(DELIVERANCE_SLUG, out)
        self.assertIn('game_000', out)
        out, log = self.list_output(tags=['Movies', 'Favorites'])          # any of the tags
        self.assertIn(DELIVERANCE_SLUG, out)
        self.assertIn('game_000', out)
        out, log = self.list_output(tags=['Movies', 'Favorites'], skiptags=['Favorites'])      # -skiptags wins
        self.assertIn(DELIVERANCE_SLUG, out)
        self.assertNotIn('game_000', out)
        self.assertNotIn('Movies', out.splitlines()[0])                    # no tags column: an item can have several tags

    def test_list_tags_work_with_the_other_filters_and_the_words(self):
        with self.gog():
            self.update()
        self.tag_the_manifest(**{DELIVERANCE_SLUG: ['Movies'], 'game_000': ['Movies']})
        out, log = self.list_output(tags=['Movies'], os_list=['linux'])    # the movie passes -os, the game has only windows files
        self.assertIn(DELIVERANCE_SLUG, out)
        self.assertNotIn('game_000', out)
        out, log = self.list_output(tags=['Movies'], words=['game_000'])
        self.assertIn('game_000', out)
        self.assertNotIn(DELIVERANCE_SLUG, out)
        out, log = self.list_output(tags=['Movies'], output_format='ids')
        self.assertEqual(sorted(out.split()), sorted([DELIVERANCE_SLUG, 'game_000']))

    def test_list_with_a_tag_that_no_item_has_says_so_and_fails(self):
        with self.gog():
            self.update()
        self.tag_the_manifest(**{DELIVERANCE_SLUG: ['Movies']})
        g.run_report.reset('list')
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_list([], [], [], [], [], 'table', ['Nope'], [])
        text = '\n'.join(r.getMessage() for r in logs.records)
        self.assertEqual(buffer.getvalue(), '')                            # nothing is listed, never "all games"
        self.assertIn("-tags 'Nope' matches no game", text)
        self.assertIn('Movies', text)                                      # the message lists the tags that exist
        self.assertNotEqual(g.run_report.exit_status(), 0)

    def add_games_without_installers(self):
        """Two games like 'gwent_the_witcher_card_game' and 'hotline_miami_2_wrong_number_digital_comics' of a real manifest: extras only, and no file at all."""
        items = g.load_manifest()
        extras = [g.AttrDict(name='comic1.zip', size=100, lang='', os_type=None), g.AttrDict(name='comic2.zip', size=200, lang='', os_type=None)]
        items.append(g.AttrDict(id=3001, title='extras_only', long_title='extras_only', media_type='1', downloads=[], galaxyDownloads=[], sharedDownloads=[],
                                extras=extras, tag_names=[]))
        items.append(g.AttrDict(id=3002, title='nothing_at_all', long_title='nothing_at_all', media_type='1', downloads=[], galaxyDownloads=[],
                                sharedDownloads=[], extras=[], tag_names=[]))
        g.save_manifest(items)

    def test_list_filters_keep_the_games_that_have_no_installer_at_all(self):
        # entry 0.5.85: -os/-lang decide about installers; a game with only extras (which belong to no system or language) or with nothing was hidden
        with self.gog():
            self.update()
        self.add_games_without_installers()
        for options in (dict(os_list=['windows']), dict(os_list=['linux']), dict(lang_list=['en']), dict(lang_list=['de']), dict(skipos_list=['windows']),
                        dict(skiplang_list=['en']), dict(os_list=['linux'], lang_list=['de'])):
            with self.subTest(**options):
                out, log = self.list_output(**options)
                rows = dict((line.split()[1], line.split()) for line in out.splitlines()[1:])
                self.assertIn('extras_only', rows)
                self.assertIn('nothing_at_all', rows)
                self.assertEqual(rows['extras_only'][3:7], ['game', '-', '-', '2'])        # no system, no language, two extras
                self.assertEqual(rows['nothing_at_all'][3:7], ['game', '-', '-', '0'])

    def test_list_filters_still_hide_the_games_whose_installers_do_not_fit(self):
        with self.gog():
            self.update()
        self.add_games_without_installers()
        out, log = self.list_output(os_list=['linux'])                     # game_000 has windows installers only
        self.assertNotIn('game_000', out)
        self.assertIn(DELIVERANCE_SLUG, out)                               # the movie files belong to every system
        out, log = self.list_output(os_list=['windows'])
        self.assertIn('game_000', out)
        out, log = self.list_output(lang_list=['de'])
        self.assertNotIn('game_000', out)
        out, log = self.list_output()                                      # no filter: everything, as before
        for title in ('game_000', 'extras_only', 'nothing_at_all', DELIVERANCE_SLUG):
            self.assertIn(title, out)

    def test_list_filters_work_with_words_ids_and_tags_for_games_without_installers(self):
        with self.gog():
            self.update()
        self.add_games_without_installers()
        out, log = self.list_output(os_list=['linux'], words=['extras_only'], output_format='ids')
        self.assertEqual(out.split(), ['extras_only'])
        out, log = self.list_output(lang_list=['en'], notags=True, output_format='ids')       # the real GOG answer tags every movie 'MOVIE': these three have no tag
        self.assertEqual(sorted(out.split()), sorted(['extras_only', 'nothing_at_all', 'game_000']))
        g.run_report.reset('list')
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_list(['game_000'], ['linux'], [], [], [], 'table', [], [], False)        # the words fit only a game whose installers do not
        self.assertEqual(buffer.getvalue(), '')
        self.assertIn("1 game matches 'game_000' (game_000) but none has files for the chosen operating system / language", '\n'.join(r.getMessage() for r in logs.records))
        self.assertNotEqual(g.run_report.exit_status(), 0)

    def test_list_notags_shows_the_movies_and_games_without_tags(self):
        with self.gog():
            self.update()
        total = len(self.tag_the_manifest(**{'game_000': ['Favorites']}))
        out, log = self.list_output(notags=True)
        self.assertIn(DELIVERANCE_SLUG, out)                               # the movie has no tag
        self.assertNotIn('game_000', out)
        self.assertEqual(len(out.splitlines()), total)                     # the header and every item but the tagged game
        self.assertIn('%d of %d games' % (total - 1, total), log)
        out, log = self.list_output(notags=True, os_list=['linux'])        # the movie passes -os, the other items have windows files only
        self.assertIn(DELIVERANCE_SLUG, out)
        self.assertNotIn('game_000', out)
        out, log = self.list_output(notags=True, skiptags=['Favorites'], words=[DELIVERANCE_SLUG], output_format='ids')
        self.assertEqual(out.split(), [DELIVERANCE_SLUG])

    def test_list_notags_with_nothing_left_says_so_and_fails(self):
        with self.gog():
            self.update()
        self.tag_the_manifest(**dict((item.title, ['Movies']) for item in g.load_manifest()))     # everything has a tag
        g.run_report.reset('list')
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_list([], [], [], [], [], 'table', [], [], True)
        self.assertEqual(buffer.getvalue(), '')
        self.assertIn('no game matches the tag filter: -notags.', '\n'.join(r.getMessage() for r in logs.records))
        self.assertNotEqual(g.run_report.exit_status(), 0)

    def test_list_with_tags_that_leave_nothing_says_so_and_fails(self):
        with self.gog():
            self.update()
        self.tag_the_manifest(**{DELIVERANCE_SLUG: ['Movies']})
        g.run_report.reset('list')
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_list([], [], [], [], [], 'table', ['Movies'], ['Movies'])
        self.assertEqual(buffer.getvalue(), '')
        self.assertIn('no game matches the tag filter: -tags Movies; -skiptags Movies.', '\n'.join(r.getMessage() for r in logs.records))
        self.assertNotEqual(g.run_report.exit_status(), 0)

    def test_list_with_tags_and_a_manifest_without_tag_data_says_to_run_update(self):
        with self.gog():
            self.update()
        items = g.load_manifest()
        for item in items:
            if hasattr(item, 'tag_names'):
                del item['tag_names']
        g.save_manifest(items)
        g.run_report.reset('list')
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertLogs('gogrepoc', level='INFO') as logs:
            g.cmd_list([], [], [], [], [], 'table', ['Movies'], [])
        self.assertEqual(buffer.getvalue(), '')
        self.assertIn("Run 'update' once", '\n'.join(r.getMessage() for r in logs.records))
        self.assertNotEqual(g.run_report.exit_status(), 0)

    def test_list_without_tag_options_is_unchanged(self):
        with self.gog():
            self.update()
        total = len(self.tag_the_manifest(**{DELIVERANCE_SLUG: ['Movies']}))
        out, log = self.list_output()
        self.assertIn(DELIVERANCE_SLUG, out)
        self.assertIn('game_000', out)
        self.assertIn('%d of %d games' % (total, total), log)

    def test_list_with_an_os_filter_still_shows_the_movies(self):
        # the config file's os = ... reaches `list` as -os; the files of a movie have the os 'video' and belong to every system
        with self.gog():
            self.update()
        for os_list in (['windows'], ['linux'], ['windows', 'linux', 'mac']):
            with self.subTest(os_list=os_list):
                out, log = self.list_output(os_list=os_list, lang_list=['en'])
                self.assertIn(DELIVERANCE_SLUG, out)
                self.assertIn('vid', [l for l in out.splitlines() if DELIVERANCE_SLUG in l][0].split())
        out, log = self.list_output(os_list=['linux'])
        self.assertNotIn('game_000', out)                     # the game has only windows files: the filter still works for games
        self.assertIn(DELIVERANCE_SLUG, out)

    def test_list_movies_are_still_chosen_by_language_and_skipos(self):
        with self.gog():
            self.update()
        out, log = self.list_output(os_list=['windows'], lang_list=['de'])
        self.assertNotIn(DELIVERANCE_SLUG, out)               # -lang is not relaxed for movies (they have a language)
        out, log = self.list_output(skipos_list=['windows'])
        self.assertIn(DELIVERANCE_SLUG, out)
        self.assertNotIn('game_000', out)

    def test_an_invisible_character_does_not_shift_the_columns(self):
        with self.gog():
            self.update()
        items = g.load_manifest()
        for item in items:
            if item.title == 'game_000':
                item.long_title = 'Game 0\ufeff'
        g.save_manifest(items)
        out, log = self.list_output()
        lines = out.splitlines()
        columns = set(g._display_width(l[:l.index(' game ')] if ' game ' in l else l[:l.index(' movie ')]) for l in lines[1:])
        self.assertEqual(len(columns), 1, out)

    def test_export_has_a_media_column_and_the_video_os(self):
        import csv
        with self.gog():
            self.update()
        g.cmd_export('out.csv', None, ',')
        with open('out.csv', encoding='utf-8-sig', newline='') as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0][:3], ['game id', 'title', 'media'])
        movie = [r for r in rows if r[1] == DELIVERANCE_SLUG and r[4] == 'standalone']
        self.assertEqual(len(movie), 2)
        self.assertTrue(all(r[2] == 'movie' and r[6] == g.MOVIE_OS_TYPE and r[7] == 'English' for r in movie))
        self.assertTrue(all(r[3] == DELIVERANCE_SLUG + '-movie' for r in movie))
        self.assertEqual({r[2] for r in rows if r[1] == 'game_000'}, {'game'})


class CommandLineTests(unittest.TestCase):
    def parse(self, *argv):
        return g.process_argv(['gogrepo_delta.py', 'update'] + list(argv) + ['-nolog'])

    def test_off_by_default_and_best(self):
        args = self.parse()
        self.assertFalse(args.movies)
        self.assertEqual(args.moviequality, 'best')

    def test_the_switches(self):
        args = self.parse('-movies', '-moviequality', '1080p,720p')
        self.assertTrue(args.movies)
        self.assertEqual(args.moviequality, '1080p,720p')
        self.assertTrue(self.parse('--movies').movies)

    def test_a_wrong_quality_is_refused_by_the_parser_with_the_reason(self):
        import io
        import contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            self.parse('-movies', '-moviequality', 'max:nonsense')
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('not a quality I can compare', err.getvalue())

    def test_the_other_commands_have_no_movie_switches(self):
        for command in ('download', 'verify', 'clean'):
            with self.assertRaises(SystemExit), mock.patch('sys.stderr'):
                g.process_argv(['gogrepo_delta.py', command, 'x', '-movies', '-nolog'])


if __name__ == '__main__':
    unittest.main()
