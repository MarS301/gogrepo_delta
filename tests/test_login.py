"""Login: captcha detection, the -browser switch, and the automatic (user name + password) flow.

Nothing here talks to GOG. `request` (the script's HTTP function) is replaced by a fake that answers like GOG's pages,
and the answers a person would type are supplied by the tests.

The login pages are small, well-formed HTML snippets. The script parses real pages with html5lib, which returns standard
ElementTree elements; if html5lib is not installed (the test bootstrap then uses an empty stand-in) the snippets are
parsed with ElementTree directly, which gives the same kind of element, so the checks are the same either way."""
import contextlib
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as gogrepoc

# --- login pages (shapes taken from the page the script reads: a form named "login" with a hidden token) -------------

PLAIN_FORM = """<html><body><form name="login" method="post">
  <input type="hidden" id="login__token" value="TOKEN123"/>
  <input type="text" id="login_username" name="login[username]"/>
  <input type="password" id="login_password" name="login[password]"/>
</form></body></html>"""

OLD_RECAPTCHA_FORM = """<html><body><form name="login" method="post">
  <input type="hidden" id="login__token" value="TOKEN123"/>
  <div class="g-recaptcha form__recaptcha" data-sitekey="x"></div>
</form></body></html>"""

NEW_CAPTCHA_FORM = """<html><body><form name="login" method="post">
  <input type="hidden" id="login__token" value="TOKEN123"/>
  <ol class="form__fieldset form__fieldset--captcha"><li>captcha here</li></ol>
</form></body></html>"""

NO_LOGIN_FORM = """<html><body><form name="something_else"><input type="text"/></form></body></html>"""

# a page with an input that has no id: the old code raised KeyError on it
INPUT_WITHOUT_ID_FORM = """<html><body><form name="login" method="post">
  <input type="text" name="no_id_here"/>
  <input type="hidden" id="login__token" value="TOKEN123"/>
</form></body></html>"""

SUCCESS_URL = 'https://embed.gog.com/on_login_success?origin=client&code=CODE_FROM_PASSWORD_LOGIN'
BROWSER_URL = 'https://embed.gog.com/on_login_success?origin=client&code=CODE_FROM_BROWSER'


def element(text):
    return ET.fromstring(text)


def sent_query(args):
    """The query string as it would go over the wire for these request arguments (a code may be a text or a one-item list)."""
    import requests
    from urllib.parse import urlparse, parse_qs
    return parse_qs(urlparse(requests.Request('GET', 'https://example.invalid/', params=args).prepare().url).query)


class FakeResponse(object):
    def __init__(self, text='', url='', payload=None):
        self.text = text
        self.url = url
        self._payload = payload

    def json(self):
        return self._payload


class FakeGog(object):
    """Stands in for gogrepoc.request. Records every call as (url, args, data)."""

    def __init__(self, login_page=PLAIN_FORM, login_check_url=SUCCESS_URL, token_error=None):
        self.login_page = login_page
        self.login_check_url = login_check_url
        self.token_error = token_error
        self.calls = []

    def __call__(self, session, url, args=None, data=None, **kwargs):
        self.calls.append((url, args, data))
        if url == gogrepoc.GOG_AUTH_URL:
            return FakeResponse(self.login_page, 'https://login.gog.com/auth?shown_page_url')
        if url == gogrepoc.GOG_LOGIN_URL:
            return FakeResponse('<html><body></body></html>', self.login_check_url)
        if url == gogrepoc.GOG_TOKEN_URL:
            if self.token_error:
                raise self.token_error
            return FakeResponse(payload={'access_token': 'ACCESS', 'refresh_token': 'REFRESH', 'expires_in': 3600})
        raise AssertionError('unexpected request to ' + url)

    def urls(self):
        return [c[0] for c in self.calls]


class LoginTestCase(unittest.TestCase):
    """Sets up the fake GOG, records the saved token and gives a way to supply typed answers."""

    def setUp(self):
        self.saved_tokens = []
        self.typed = []        # answers returned by input(), in order
        self.prompts = []
        self.getpass_calls = []
        self.browser_opened = []
        self.browser_result = True
        self.gog = FakeGog()
        self.patches = [
            mock.patch.object(gogrepoc, 'request', self._request),
            mock.patch.object(gogrepoc, 'save_token', self.saved_tokens.append),
            mock.patch('builtins.input', self._input),
            mock.patch.object(gogrepoc.getpass, 'getpass', self._getpass),
            mock.patch.object(gogrepoc.webbrowser, 'open', self._open),
        ]
        if not hasattr(gogrepoc.html5lib, 'parse'):
            self.patches.append(mock.patch.object(gogrepoc.html5lib, 'parse',
                                                  lambda text, namespaceHTMLElements=False: ET.fromstring(text), create=True))
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    # indirection so tests can swap self.gog after setUp
    def _request(self, *args, **kwargs):
        return self.gog(*args, **kwargs)

    def _input(self, prompt=''):
        self.prompts.append(prompt)
        if not self.typed:
            raise AssertionError('the program asked for input that the test did not expect: %r' % prompt)
        answer = self.typed.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def _getpass(self, prompt='Password: '):
        self.getpass_calls.append(prompt)
        return 'secret-password'

    def _open(self, url):
        self.browser_opened.append(url)
        if isinstance(self.browser_result, BaseException):
            raise self.browser_result
        return self.browser_result

    def login(self, *args, **kwargs):
        # the console messages are not interesting here; assertLogs keeps them out of the test output and lets us read them
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            result = gogrepoc.cmd_login(*args, **kwargs)
            gogrepoc.info('end of test')   # assertLogs fails when nothing at all was logged
        self.log_text = '\n'.join(logs.output)
        return result


# --- captcha detection ---------------------------------------------------------------------------------------------

class CaptchaDetectionTests(unittest.TestCase):
    def test_old_recaptcha_box_is_detected(self):
        self.assertTrue(gogrepoc.login_form_has_captcha(element(OLD_RECAPTCHA_FORM).find('.//form')))

    def test_new_captcha_field_list_is_detected(self):
        self.assertTrue(gogrepoc.login_form_has_captcha(element(NEW_CAPTCHA_FORM).find('.//form')))

    def test_a_normal_login_form_is_not_a_captcha(self):
        self.assertFalse(gogrepoc.login_form_has_captcha(element(PLAIN_FORM).find('.//form')))

    def test_captcha_inside_nested_markup_is_found(self):
        form = element('<form name="login"><div><fieldset><ol class="form__fieldset form__fieldset--captcha"/></fieldset></div></form>')
        self.assertTrue(gogrepoc.login_form_has_captcha(form))

    def test_a_different_element_or_class_is_not_a_captcha(self):
        for snippet in ('<form><div class="form__fieldset form__fieldset--captcha"/></form>',    # right class, wrong element
                        '<form><ol class="form__fieldset"/></form>',                              # right element, other class
                        '<form><div class="g-recaptcha"/></form>'):                               # not the exact old class string
            self.assertFalse(gogrepoc.login_form_has_captcha(element(snippet)), snippet)


# --- reading the signed-in address ---------------------------------------------------------------------------------

class LoginCodeFromUrlTests(unittest.TestCase):
    def test_code_is_taken_from_the_address(self):
        self.assertEqual(gogrepoc.login_code_from_url(BROWSER_URL), 'CODE_FROM_BROWSER')
        self.assertEqual(gogrepoc.login_code_from_url('https://embed.gog.com/on_login_success?code=abc'), 'abc')

    def test_spaces_and_line_breaks_around_a_pasted_address_are_ignored(self):
        self.assertEqual(gogrepoc.login_code_from_url('  ' + BROWSER_URL + ' \r\n'), 'CODE_FROM_BROWSER')

    def test_no_code_gives_none(self):
        for text in ('', '   ', 'hello', 'https://embed.gog.com/on_login_success?origin=client',
                     'https://embed.gog.com/on_login_success?code=', None):
            self.assertIsNone(gogrepoc.login_code_from_url(text), text)

    def test_first_code_wins_if_there_are_several(self):
        self.assertEqual(gogrepoc.login_code_from_url('https://x/?code=one&code=two'), 'one')


class AuthUrlTests(unittest.TestCase):
    def test_address_points_to_gog_and_carries_the_login_parameters(self):
        from urllib.parse import urlparse, parse_qs
        url = gogrepoc.galaxy_auth_url()
        parsed = urlparse(url)
        self.assertEqual('%s://%s%s' % (parsed.scheme, parsed.netloc, parsed.path), gogrepoc.GOG_AUTH_URL)
        query = parse_qs(parsed.query)
        self.assertEqual(query['client_id'], [gogrepoc.GOG_CLIENT_ID])
        self.assertEqual(query['response_type'], ['code'])
        self.assertEqual(query['redirect_uri'], [gogrepoc.GOG_GALAXY_REDIRECT_URL + '?origin=client'])

    def test_no_secret_is_in_the_address(self):
        self.assertNotIn(gogrepoc.GOG_SECRET, gogrepoc.galaxy_auth_url())

    def test_the_automatic_login_asks_for_the_same_page(self):
        # one definition of the parameters, used by both ways of logging in
        self.assertEqual(gogrepoc.galaxy_auth_args()['redirect_uri'], gogrepoc.GOG_GALAXY_REDIRECT_URL + '?origin=client')


# --- command line --------------------------------------------------------------------------------------------------

def parse(*argv):
    return gogrepoc.process_argv(['gogrepo_delta.py'] + list(argv) + ['-nolog'])


class LoginCommandLineTests(unittest.TestCase):
    def test_browser_is_off_by_default(self):
        self.assertFalse(parse('login').browser)
        self.assertFalse(parse('login', 'someone').browser)

    def test_browser_switch_in_both_spellings(self):
        self.assertTrue(parse('login', '-browser').browser)
        self.assertTrue(parse('login', '--browser').browser)

    def test_browser_can_be_combined_with_a_user_name(self):
        args = parse('login', 'someone', '-browser')
        self.assertTrue(args.browser)
        self.assertEqual(args.username, 'someone')

    def test_other_commands_do_not_have_the_switch(self):
        captured = __import__('io').StringIO()
        with contextlib.redirect_stderr(captured), self.assertRaises(SystemExit):
            gogrepoc.process_argv(['gogrepo_delta.py', 'update', '-browser', '-nolog'])


# --- the -browser login --------------------------------------------------------------------------------------------

class BrowserLoginTests(LoginTestCase):
    def test_signs_in_with_the_pasted_address_and_saves_the_token(self):
        self.typed = [BROWSER_URL]
        self.assertTrue(self.login(None, None, browser=True))
        self.assertEqual(len(self.saved_tokens), 1)
        self.assertEqual(self.saved_tokens[0]['access_token'], 'ACCESS')
        self.assertIn('expiry', self.saved_tokens[0])
        # the one request made is the code exchange, with the pasted code
        self.assertEqual(self.gog.urls(), [gogrepoc.GOG_TOKEN_URL])
        self.assertEqual(sent_query(self.gog.calls[0][1])['code'], ['CODE_FROM_BROWSER'])
        self.assertEqual(sent_query(self.gog.calls[0][1])['grant_type'], ['authorization_code'])

    def test_no_password_is_asked_for_and_the_login_page_is_not_read(self):
        self.typed = [BROWSER_URL]
        self.login(None, None, browser=True)
        self.assertEqual(self.getpass_calls, [])
        self.assertEqual(self.prompts, ['Signed In URL: '])          # no "Username: "
        self.assertNotIn(gogrepoc.GOG_AUTH_URL, self.gog.urls())      # so a changed login page cannot break it
        self.assertNotIn(gogrepoc.GOG_LOGIN_URL, self.gog.urls())

    def test_browser_is_opened_on_the_gog_sign_in_page_and_the_address_is_shown(self):
        self.typed = [BROWSER_URL]
        self.login(None, None, browser=True)
        self.assertEqual(self.browser_opened, [gogrepoc.galaxy_auth_url()])
        self.assertIn(gogrepoc.galaxy_auth_url(), self.log_text)

    def test_if_no_browser_can_be_opened_the_address_is_still_shown_and_login_works(self):
        for result in (False, RuntimeError('no display')):
            self.browser_result = result
            self.typed = [BROWSER_URL]
            self.saved_tokens.clear()
            self.assertTrue(self.login(None, None, browser=True), result)
            self.assertIn('Could not open a browser automatically', self.log_text)
            self.assertIn(gogrepoc.galaxy_auth_url(), self.log_text)
            self.assertEqual(len(self.saved_tokens), 1)

    def test_the_pasted_address_is_not_written_to_the_log(self):
        # the code in it is a one-time key to the account
        self.typed = [BROWSER_URL]
        self.login(None, None, browser=True)
        self.assertNotIn('CODE_FROM_BROWSER', self.log_text)

    def test_an_address_without_code_is_refused_and_nothing_is_saved(self):
        for bad in ('', 'not an address', 'https://embed.gog.com/on_login_success?origin=client'):
            self.typed = [bad]
            self.saved_tokens.clear()
            self.gog.calls.clear()
            self.assertFalse(self.login(None, None, browser=True), bad)
            self.assertIn('Could not parse entered URL', self.log_text)
            self.assertEqual(self.saved_tokens, [])
            self.assertEqual(self.gog.calls, [])

    def test_without_a_terminal_it_stops_with_a_message(self):
        self.typed = [EOFError()]
        self.assertFalse(self.login(None, None, browser=True))
        self.assertIn('no terminal', self.log_text.lower())
        self.assertEqual(self.saved_tokens, [])

    def test_a_username_and_password_given_with_browser_are_ignored_with_a_warning(self):
        self.typed = [BROWSER_URL]
        self.assertTrue(self.login('someone', 'secret', browser=True))
        self.assertIn('not used', self.log_text)
        self.assertNotIn('secret', self.log_text)
        self.assertEqual(self.getpass_calls, [])

    def test_a_code_gog_rejects_gives_a_message_not_a_traceback_and_saves_nothing(self):
        import requests
        self.gog = FakeGog(token_error=requests.HTTPError('400 Client Error: Bad Request'))
        self.typed = [BROWSER_URL]
        self.assertFalse(self.login(None, None, browser=True))
        self.assertIn('can only be used once', self.log_text)
        self.assertEqual(self.saved_tokens, [])

    def test_a_token_answer_without_expiry_is_reported_not_crashed_on(self):
        class NoExpiry(FakeGog):
            def __call__(self, session, url, args=None, data=None, **kw):
                self.calls.append((url, args, data))
                return FakeResponse(payload={'access_token': 'ACCESS'})
        self.gog = NoExpiry()
        self.typed = [BROWSER_URL]
        self.assertFalse(self.login(None, None, browser=True))
        self.assertEqual(self.saved_tokens, [])


# --- the automatic login -------------------------------------------------------------------------------------------

class AutomaticLoginTests(LoginTestCase):
    def test_normal_login_page_logs_in_with_user_and_password(self):
        # regression: the flow that worked before is unchanged
        self.assertTrue(self.login('someone', 'pw'))
        self.assertEqual(self.gog.urls(), [gogrepoc.GOG_AUTH_URL, gogrepoc.GOG_LOGIN_URL, gogrepoc.GOG_TOKEN_URL])
        login_post = self.gog.calls[1][2]
        self.assertEqual(login_post['login[username]'], 'someone')
        self.assertEqual(login_post['login[password]'], 'pw')
        self.assertEqual(login_post['login[_token]'], 'TOKEN123')
        self.assertEqual(sent_query(self.gog.calls[2][1])['code'], ['CODE_FROM_PASSWORD_LOGIN'])
        self.assertEqual(len(self.saved_tokens), 1)
        self.assertEqual(self.prompts, [])       # nothing typed: user and password were given

    def test_missing_user_and_password_are_prompted(self):
        self.typed = ['typed-user']
        self.assertTrue(self.login(None, None))
        self.assertEqual(self.prompts, ['Username: '])
        self.assertEqual(self.getpass_calls, ['Password: '])
        self.assertEqual(self.gog.calls[1][2]['login[username]'], 'typed-user')
        self.assertEqual(self.gog.calls[1][2]['login[password]'], 'secret-password')

    def test_new_captcha_page_does_not_send_the_password_and_falls_back_to_the_browser_address(self):
        self.gog = FakeGog(login_page=NEW_CAPTCHA_FORM)
        self.typed = [BROWSER_URL]
        self.assertTrue(self.login('someone', 'pw'))
        self.assertNotIn(gogrepoc.GOG_LOGIN_URL, self.gog.urls())     # the password is not sent to a page we cannot complete
        self.assertEqual(self.gog.urls(), [gogrepoc.GOG_AUTH_URL, gogrepoc.GOG_TOKEN_URL])
        self.assertEqual(sent_query(self.gog.calls[1][1])['code'], ['CODE_FROM_BROWSER'])
        self.assertIn('asking for a reCAPTCHA', self.log_text)
        self.assertIn('-browser', self.log_text)                      # tells about the switch
        self.assertEqual(len(self.saved_tokens), 1)

    def test_old_recaptcha_page_still_falls_back_the_same_way(self):
        self.gog = FakeGog(login_page=OLD_RECAPTCHA_FORM)
        self.typed = [BROWSER_URL]
        self.assertTrue(self.login('someone', 'pw'))
        self.assertNotIn(gogrepoc.GOG_LOGIN_URL, self.gog.urls())

    def test_page_without_login_form_falls_back_with_the_maintainer_message(self):
        self.gog = FakeGog(login_page=NO_LOGIN_FORM)
        self.typed = [BROWSER_URL]
        self.assertTrue(self.login('someone', 'pw'))
        self.assertIn('Could not locate login form', self.log_text)
        self.assertNotIn(gogrepoc.GOG_LOGIN_URL, self.gog.urls())

    def test_captcha_fallback_with_an_unusable_address_fails_cleanly(self):
        self.gog = FakeGog(login_page=NEW_CAPTCHA_FORM)
        self.typed = ['rubbish']
        self.assertFalse(self.login('someone', 'pw'))
        self.assertEqual(self.saved_tokens, [])
        self.assertEqual(self.gog.urls(), [gogrepoc.GOG_AUTH_URL])

    def test_the_automatic_flow_does_not_open_a_browser_by_itself(self):
        # only -browser does that; the captcha fallback keeps showing the address and asking, as before
        self.gog = FakeGog(login_page=NEW_CAPTCHA_FORM)
        self.typed = [BROWSER_URL]
        self.login('someone', 'pw')
        self.assertEqual(self.browser_opened, [])

    def test_wrong_password_reports_failure(self):
        self.gog = FakeGog(login_check_url='https://login.gog.com/login?error')
        self.assertFalse(self.login('someone', 'wrong'))
        self.assertIn('Galaxy login failed', self.log_text)
        self.assertEqual(self.saved_tokens, [])
        self.assertNotIn(gogrepoc.GOG_TOKEN_URL, self.gog.urls())

    def test_an_input_without_id_on_the_page_no_longer_crashes(self):
        self.gog = FakeGog(login_page=INPUT_WITHOUT_ID_FORM)
        self.assertTrue(self.login('someone', 'pw'))
        self.assertEqual(self.gog.calls[1][2]['login[_token]'], 'TOKEN123')

    def test_two_step_code_is_still_asked_for_and_sent(self):
        class TwoStep(FakeGog):
            def __call__(self, session, url, args=None, data=None, **kw):
                if url == gogrepoc.GOG_LOGIN_URL:
                    self.calls.append((url, args, data))
                    page = '<html><body><input id="second_step_authentication__token" value="STEP2"/></body></html>'
                    return FakeResponse(page, 'https://login.gog.com/login/two_step')
                if url == 'https://login.gog.com/login/two_step':
                    self.calls.append((url, args, data))
                    return FakeResponse('', SUCCESS_URL)
                return FakeGog.__call__(self, session, url, args=args, data=data, **kw)
        self.gog = TwoStep()
        self.typed = ['1234']        # GOG's e-mail two-step code has 4 digits (the authenticator code has 6)
        self.assertTrue(self.login('someone', 'pw'))
        step = [c for c in self.gog.calls if c[0].endswith('two_step')][0][2]
        self.assertEqual(step['second_step_authentication[token][letter_1]'], '1')
        self.assertEqual(step['second_step_authentication[token][letter_4]'], '4')
        self.assertEqual(step['second_step_authentication[_token]'], 'STEP2')


# --- exit status ---------------------------------------------------------------------------------------------------

class LoginExitStatusTests(unittest.TestCase):
    def run_main(self, result, *argv):
        args = gogrepoc.process_argv(['gogrepo_delta.py', 'login'] + list(argv) + ['-nolog'])
        with mock.patch.object(gogrepoc, 'cmd_login', return_value=result) as fake:
            status = gogrepoc.main(args)
        return status, fake

    def test_exit_status_is_0_after_a_successful_login(self):
        self.assertEqual(self.run_main(True)[0], 0)

    def test_exit_status_is_1_after_a_failed_login(self):
        self.assertEqual(self.run_main(False)[0], 1)

    def test_the_browser_switch_reaches_cmd_login(self):
        _, fake = self.run_main(True, 'someone', '-browser')
        fake.assert_called_once_with('someone', None, browser=True)
        _, fake = self.run_main(True)
        fake.assert_called_once_with(None, None, browser=False)


if __name__ == '__main__':
    unittest.main()
