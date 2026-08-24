# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Tests for frontend
"""

import json
import unittest
from unittest.mock import MagicMock, patch, mock_open
from urllib.parse import unquote_plus

from requests.exceptions import HTTPError, RequestException

from frontend.frontend import create_app
from frontend.tests.constants import (
    EXAMPLE_ACCOUNT_ID,
    EXAMPLE_CONTACTS,
    EXAMPLE_CONTACT_ACCOUNT_ID,
    EXAMPLE_DEPOSIT_FORM,
    EXAMPLE_DISPLAY_NAME,
    EXAMPLE_ENVIRON,
    EXAMPLE_LOGIN_FORM,
    EXAMPLE_PAYMENT_FORM,
    EXAMPLE_PUBLIC_KEY,
    EXAMPLE_SIGNUP_FORM,
    EXAMPLE_TRANSACTIONS,
    EXAMPLE_USERNAME,
    EXAMPLE_UUID,
    EXTERNAL_ROUTING,
    LOCAL_ROUTING,
    OTHER_PRIVATE_KEY,
    SLACK_CHANNEL,
    SLACK_WEBHOOK_URL,
    TOKEN_EXPIRY_SECONDS,
    make_token,
)


def make_backend_response(status_code=200, json_body=None, text=''):
    """Build a mocked requests.Response-like object"""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_body is not None:
        response.json.return_value = json_body
    if status_code >= 400:
        response.raise_for_status.side_effect = HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


class TestFrontend(unittest.TestCase):
    """
    Base test case that creates the frontend Flask app with mocked
    key file, environment, and metadata server
    """

    def setUp(self):
        """Setup Flask TestClient with mocked env and public key file"""
        # mock opening the public key file
        with patch('frontend.frontend.open',
                   mock_open(read_data=EXAMPLE_PUBLIC_KEY.decode('utf-8'))):
            # mock env vars
            with patch.dict('os.environ', EXAMPLE_ENVIRON, clear=True):
                # mock the GCP metadata server as unreachable
                with patch('frontend.frontend.requests.get',
                           side_effect=RequestException('metadata unavailable')):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

    def set_token_cookie(self, token):
        """Set the auth token cookie on the test client"""
        if token is not None:
            self.test_app.set_cookie('token', token)

    def invalid_tokens(self):
        """Tokens that must never pass verify_token"""
        return {
            'missing': None,
            'malformed': 'not.a.jwt',
            'expired': make_token(expired=True),
            'wrong-key': make_token(private_key=OTHER_PRIVATE_KEY),
        }


class TestAuth(TestFrontend):
    """Tests for token verification and auth cookie handling"""

    def test_root_without_token_renders_login_page(self):
        """test root shows the login page when no token cookie is present"""
        response = self.test_app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sign in', response.data)

    def test_home_redirects_to_login_for_invalid_tokens(self):
        """test /home redirects to /login for every invalid token class"""
        for kind, token in self.invalid_tokens().items():
            self.test_app.delete_cookie('token')
            self.set_token_cookie(token)
            response = self.test_app.get('/home')
            self.assertEqual(response.status_code, 302,
                             '{} token did not redirect'.format(kind))
            self.assertIn('/login', response.location,
                          '{} token did not redirect to login'.format(kind))

    def test_login_page_redirects_home_with_valid_token(self):
        """test /login redirects to /home when already authenticated"""
        self.set_token_cookie(make_token())
        response = self.test_app.get('/login')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.location)

    def test_signup_page_redirects_home_with_valid_token(self):
        """test /signup redirects to /home when already authenticated"""
        self.set_token_cookie(make_token())
        response = self.test_app.get('/signup')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.location)

    def test_signup_page_renders_without_token(self):
        """test /signup renders the signup form when unauthenticated"""
        response = self.test_app.get('/signup')
        self.assertEqual(response.status_code, 200)

    def test_logout_deletes_auth_cookies(self):
        """test /logout deletes the token and consent cookies"""
        self.set_token_cookie(make_token())
        response = self.test_app.post('/logout')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)
        cookies = response.headers.getlist('Set-Cookie')
        self.assertTrue(any(c.startswith('token=;') for c in cookies))
        self.assertTrue(any(c.startswith('consented=;') for c in cookies))


class TestLogin(TestFrontend):
    """Tests for /login and the auth cookie it sets"""

    @patch('frontend.frontend.requests.get')
    def test_login_success_sets_token_cookie_with_max_age(self, mock_get):
        """test successful login sets the token cookie for exp - iat seconds"""
        token = make_token()
        mock_get.return_value = make_backend_response(json_body={'token': token})
        response = self.test_app.post('/login', data=EXAMPLE_LOGIN_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.location)
        cookie = next(c for c in response.headers.getlist('Set-Cookie')
                      if c.startswith('token='))
        self.assertIn(token, cookie)
        self.assertIn('Max-Age={}'.format(TOKEN_EXPIRY_SECONDS), cookie)

    @patch('frontend.frontend.requests.get')
    def test_login_oauth_flow_redirects_to_consent(self, mock_get):
        """test login during an oauth flow redirects to the consent page"""
        token = make_token()
        mock_get.return_value = make_backend_response(json_body={'token': token})
        response = self.test_app.post(
            '/login?response_type=code&state=xyz'
            '&redirect_uri=https://client.example.com/cb&app_name=partner',
            data=EXAMPLE_LOGIN_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/consent', response.location)
        self.assertIn('state=xyz', response.location)

    @patch('frontend.frontend.requests.get')
    def test_login_backend_error_redirects_with_message(self, mock_get):
        """test failed login redirects back to /login with an error message"""
        mock_get.side_effect = RequestException('userservice down')
        response = self.test_app.post('/login', data=EXAMPLE_LOGIN_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)
        self.assertIn('Login Failed', unquote_plus(response.location))

    @patch('frontend.frontend.requests.get')
    def test_login_userservice_401_redirects_with_message(self, mock_get):
        """test login rejected by userservice redirects with error message"""
        mock_get.return_value = make_backend_response(status_code=401)
        response = self.test_app.post('/login', data=EXAMPLE_LOGIN_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Login Failed', unquote_plus(response.location))


class TestPayment(TestFrontend):
    """Tests for /payment"""

    def test_payment_401_for_invalid_tokens(self):
        """test /payment returns 401 for every invalid token class"""
        for kind, token in self.invalid_tokens().items():
            self.test_app.delete_cookie('token')
            self.set_token_cookie(token)
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
            self.assertEqual(response.status_code, 401,
                             '{} token was not rejected'.format(kind))

    @patch('frontend.frontend.sleep')
    @patch('frontend.frontend.requests.post')
    def test_payment_success_submits_transaction(self, mock_post, _mock_sleep):
        """test a valid payment posts the transaction and redirects"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=201)
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 303)
        self.assertIn('Payment successful', unquote_plus(response.location))
        transaction = json.loads(mock_post.call_args.kwargs['data'])
        self.assertEqual(transaction['fromAccountNum'], EXAMPLE_ACCOUNT_ID)
        self.assertEqual(transaction['fromRoutingNum'], LOCAL_ROUTING)
        self.assertEqual(transaction['toAccountNum'], EXAMPLE_CONTACT_ACCOUNT_ID)
        self.assertEqual(transaction['toRoutingNum'], LOCAL_ROUTING)
        # 25.50 dollars submitted as 2550 cents
        self.assertEqual(transaction['amount'], 2550)
        self.assertEqual(transaction['uuid'], EXAMPLE_UUID)

    @patch('frontend.frontend.sleep')
    @patch('frontend.frontend.requests.post')
    def test_payment_new_contact_adds_contact_then_pays(self, mock_post, _mock_sleep):
        """test paying a new labeled contact registers the contact first"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=201)
        form = EXAMPLE_PAYMENT_FORM.copy()
        form['account_num'] = 'add'
        form['contact_account_num'] = EXAMPLE_CONTACT_ACCOUNT_ID
        form['contact_label'] = 'New Friend'
        response = self.test_app.post('/payment', data=form)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(mock_post.call_count, 2)
        contact_url = mock_post.call_args_list[0].kwargs['url']
        self.assertIn('/contacts/{}'.format(EXAMPLE_USERNAME), contact_url)
        contact = json.loads(mock_post.call_args_list[0].kwargs['data'])
        self.assertEqual(contact['label'], 'New Friend')
        self.assertEqual(contact['account_num'], EXAMPLE_CONTACT_ACCOUNT_ID)
        self.assertEqual(contact['routing_num'], LOCAL_ROUTING)
        self.assertFalse(contact['is_external'])
        transaction = json.loads(mock_post.call_args_list[1].kwargs['data'])
        self.assertEqual(transaction['toAccountNum'], EXAMPLE_CONTACT_ACCOUNT_ID)

    @patch('frontend.frontend.sleep')
    @patch('frontend.frontend.requests.post')
    def test_payment_new_recipient_without_label_skips_contact(self, mock_post,
                                                               _mock_sleep):
        """test paying a new unlabeled account does not create a contact"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=201)
        form = EXAMPLE_PAYMENT_FORM.copy()
        form['account_num'] = 'add'
        form['contact_account_num'] = EXAMPLE_CONTACT_ACCOUNT_ID
        response = self.test_app.post('/payment', data=form)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(mock_post.call_count, 1)

    @patch('frontend.frontend.requests.post')
    def test_payment_contact_add_failure_shows_reason(self, mock_post):
        """test a rejected contact creation fails the payment with the reason"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=400,
                                                       text='invalid account number')
        form = EXAMPLE_PAYMENT_FORM.copy()
        form['account_num'] = 'add'
        form['contact_account_num'] = EXAMPLE_CONTACT_ACCOUNT_ID
        form['contact_label'] = 'New Friend'
        response = self.test_app.post('/payment', data=form)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment failed: invalid account number',
                      unquote_plus(response.location))
        # the transaction is never submitted when the contact add fails
        self.assertEqual(mock_post.call_count, 1)

    @patch('frontend.frontend.requests.post')
    def test_payment_invalid_amount_redirects_with_message(self, mock_post):
        """test a non-numeric amount fails without posting a transaction"""
        self.set_token_cookie(make_token())
        for bad_amount in ['not_a_number', '💰', '']:
            form = EXAMPLE_PAYMENT_FORM.copy()
            form['amount'] = bad_amount
            response = self.test_app.post('/payment', data=form)
            self.assertEqual(response.status_code, 302,
                             'amount {} was not rejected'.format(bad_amount))
            self.assertIn('Payment failed', unquote_plus(response.location))
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post')
    def test_payment_ledgerwriter_reject_shows_reason(self, mock_post):
        """test a ledgerwriter rejection surfaces the backend error message"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=400,
                                                       text='insufficient balance')
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment failed: insufficient balance',
                      unquote_plus(response.location))

    @patch('frontend.frontend.requests.post')
    def test_payment_backend_unreachable_redirects_failed(self, mock_post):
        """test an unreachable ledgerwriter redirects with generic failure"""
        self.set_token_cookie(make_token())
        mock_post.side_effect = RequestException('ledgerwriter down')
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment failed', unquote_plus(response.location))

    def test_payment_missing_form_fields_400(self):
        """test a payment with no form fields is rejected as a bad request"""
        self.set_token_cookie(make_token())
        response = self.test_app.post('/payment', data={})
        self.assertEqual(response.status_code, 400)


class TestDeposit(TestFrontend):
    """Tests for /deposit"""

    def test_deposit_401_for_invalid_tokens(self):
        """test /deposit returns 401 for every invalid token class"""
        for kind, token in self.invalid_tokens().items():
            self.test_app.delete_cookie('token')
            self.set_token_cookie(token)
            response = self.test_app.post('/deposit', data=EXAMPLE_DEPOSIT_FORM)
            self.assertEqual(response.status_code, 401,
                             '{} token was not rejected'.format(kind))

    @patch('frontend.frontend.sleep')
    @patch('frontend.frontend.requests.post')
    def test_deposit_success_submits_transaction(self, mock_post, _mock_sleep):
        """test a valid deposit posts the transaction and redirects"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=201)
        response = self.test_app.post('/deposit', data=EXAMPLE_DEPOSIT_FORM)
        self.assertEqual(response.status_code, 303)
        self.assertIn('Deposit successful', unquote_plus(response.location))
        transaction = json.loads(mock_post.call_args.kwargs['data'])
        self.assertEqual(transaction['fromAccountNum'], EXAMPLE_CONTACT_ACCOUNT_ID)
        self.assertEqual(transaction['fromRoutingNum'], EXTERNAL_ROUTING)
        self.assertEqual(transaction['toAccountNum'], EXAMPLE_ACCOUNT_ID)
        self.assertEqual(transaction['toRoutingNum'], LOCAL_ROUTING)
        self.assertEqual(transaction['amount'], 10000)

    @patch('frontend.frontend.sleep')
    @patch('frontend.frontend.requests.post')
    def test_deposit_new_external_account_adds_contact(self, mock_post, _mock_sleep):
        """test depositing from a new labeled external account adds a contact"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=201)
        form = {
            'account': 'add',
            'external_account_num': EXAMPLE_CONTACT_ACCOUNT_ID,
            'external_routing_num': EXTERNAL_ROUTING,
            'external_label': 'My Other Bank',
            'amount': '100.00',
            'uuid': EXAMPLE_UUID,
        }
        response = self.test_app.post('/deposit', data=form)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(mock_post.call_count, 2)
        contact = json.loads(mock_post.call_args_list[0].kwargs['data'])
        self.assertEqual(contact['label'], 'My Other Bank')
        self.assertTrue(contact['is_external'])

    @patch('frontend.frontend.sleep')
    @patch('frontend.frontend.requests.post')
    def test_deposit_new_external_account_without_label_skips_contact(
            self, mock_post, _mock_sleep):
        """test depositing from an unlabeled external account adds no contact"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=201)
        form = {
            'account': 'add',
            'external_account_num': EXAMPLE_CONTACT_ACCOUNT_ID,
            'external_routing_num': EXTERNAL_ROUTING,
            'amount': '100.00',
            'uuid': EXAMPLE_UUID,
        }
        response = self.test_app.post('/deposit', data=form)
        self.assertEqual(response.status_code, 303)
        # only the transaction call; no contact creation call
        self.assertEqual(mock_post.call_count, 1)

    @patch('frontend.frontend.requests.post')
    def test_deposit_local_routing_number_rejected(self, mock_post):
        """test depositing from the bank's own routing number is rejected"""
        self.set_token_cookie(make_token())
        form = {
            'account': 'add',
            'external_account_num': EXAMPLE_CONTACT_ACCOUNT_ID,
            'external_routing_num': LOCAL_ROUTING,
            'amount': '100.00',
            'uuid': EXAMPLE_UUID,
        }
        response = self.test_app.post('/deposit', data=form)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Deposit failed: invalid routing number',
                      unquote_plus(response.location))
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post')
    def test_deposit_backend_unreachable_redirects_failed(self, mock_post):
        """test an unreachable ledgerwriter redirects with generic failure"""
        self.set_token_cookie(make_token())
        mock_post.side_effect = RequestException('ledgerwriter down')
        response = self.test_app.post('/deposit', data=EXAMPLE_DEPOSIT_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Deposit failed', unquote_plus(response.location))


class TestHome(TestFrontend):
    """Tests for the authenticated home page"""

    def mock_backend_get(self, balance=105000, transactions=None, contacts=None):
        """Return a url-dispatching side effect for api_call.get"""
        if transactions is None:
            transactions = [dict(t) for t in EXAMPLE_TRANSACTIONS]
        if contacts is None:
            contacts = [dict(c) for c in EXAMPLE_CONTACTS]

        def backend_get(url, **_kwargs):
            if 'balances' in url:
                return make_backend_response(json_body=balance)
            if 'transactions' in url:
                return make_backend_response(json_body=transactions)
            return make_backend_response(json_body=contacts)
        return backend_get

    @patch('api_call.get')
    def test_home_renders_balance_history_and_contacts(self, mock_get):
        """test the home page renders backend data for the logged-in user"""
        self.set_token_cookie(make_token())
        mock_get.side_effect = self.mock_backend_get()
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'$1,050.00', response.data)
        self.assertIn(EXAMPLE_ACCOUNT_ID.encode(), response.data)
        self.assertIn(EXAMPLE_DISPLAY_NAME.split()[0].encode(), response.data)
        self.assertIn(b'Friend', response.data)

    @patch('api_call.get')
    def test_root_with_valid_token_renders_home(self, mock_get):
        """test the root path renders the home page when authenticated"""
        self.set_token_cookie(make_token())
        mock_get.side_effect = self.mock_backend_get()
        response = self.test_app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(EXAMPLE_ACCOUNT_ID.encode(), response.data)

    @patch('api_call.get')
    def test_home_renders_defaults_when_backends_unreachable(self, mock_get):
        """test the home page still renders when all backends are down"""
        self.set_token_cookie(make_token())
        mock_get.side_effect = RequestException('backends down')
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'$---', response.data)

    @patch('api_call.get')
    def test_home_renders_negative_balance(self, mock_get):
        """test a negative balance renders with a minus sign"""
        self.set_token_cookie(make_token())
        mock_get.side_effect = self.mock_backend_get(balance=-2500)
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'-$25.00', response.data)


class TestOAuth(TestFrontend):
    """Tests for the oauth login and consent flows"""

    OAUTH_ENV = {
        'REGISTERED_OAUTH_CLIENT_ID': 'test-client',
        'ALLOWED_OAUTH_REDIRECT_URI': 'https://client.example.com/cb',
    }
    OAUTH_ARGS = ('response_type=code&client_id=test-client&state=xyz'
                  '&redirect_uri=https://client.example.com/cb&app_name=partner')

    def test_login_page_rejects_invalid_client_id(self):
        """test the oauth login flow rejects an unregistered client id"""
        with patch.dict('os.environ', self.OAUTH_ENV):
            response = self.test_app.get(
                '/login?response_type=code&client_id=wrong&state=xyz'
                '&redirect_uri=https://client.example.com/cb')
        self.assertEqual(response.status_code, 302)
        self.assertIn('Invalid client_id', unquote_plus(response.location))

    def test_login_page_rejects_invalid_redirect_uri(self):
        """test the oauth login flow rejects an unregistered redirect uri"""
        with patch.dict('os.environ', self.OAUTH_ENV):
            response = self.test_app.get(
                '/login?response_type=code&client_id=test-client&state=xyz'
                '&redirect_uri=https://evil.example.com/cb')
        self.assertEqual(response.status_code, 302)
        self.assertIn('Invalid redirect_uri', unquote_plus(response.location))

    def test_login_page_oauth_authenticated_redirects_to_consent(self):
        """test the oauth login flow sends authenticated users to consent"""
        self.set_token_cookie(make_token())
        with patch.dict('os.environ', self.OAUTH_ENV):
            response = self.test_app.get('/login?{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/consent', response.location)

    def test_login_page_oauth_unauthenticated_renders_login(self):
        """test the oauth login flow renders login for anonymous users"""
        with patch.dict('os.environ', self.OAUTH_ENV):
            response = self.test_app.get('/login?{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sign in', response.data)

    def test_consent_page_unauthenticated_redirects_to_login(self):
        """test the consent page requires authentication"""
        response = self.test_app.get('/consent?{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)
        self.assertIn('response_type=code', response.location)

    def test_consent_page_renders_consent_form(self):
        """test the consent page renders for authenticated users"""
        self.set_token_cookie(make_token())
        response = self.test_app.get('/consent?{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'partner', response.data)

    @patch('frontend.frontend.requests.post')
    def test_consent_page_prior_consent_returns_auth_code(self, mock_post):
        """test prior consent immediately redirects with the auth code"""
        self.set_token_cookie(make_token())
        self.test_app.set_cookie('consented', 'true')
        callback = make_backend_response(status_code=302)
        callback.headers = {'Location': 'https://client.example.com/cb?code=abc'}
        mock_post.return_value = callback
        response = self.test_app.get('/consent?{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, 'https://client.example.com/cb?code=abc')

    @patch('frontend.frontend.requests.post')
    def test_consent_approval_sets_cookie_and_redirects(self, mock_post):
        """test approving consent sets the consent cookie"""
        self.set_token_cookie(make_token())
        callback = make_backend_response(status_code=302)
        callback.headers = {'Location': 'https://client.example.com/cb?code=abc'}
        mock_post.return_value = callback
        response = self.test_app.post('/consent?consent=true&{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 302)
        cookies = response.headers.getlist('Set-Cookie')
        self.assertTrue(any(c.startswith('consented=true') for c in cookies))

    def test_consent_denial_redirects_with_access_denied(self):
        """test denying consent redirects with an access_denied error"""
        self.set_token_cookie(make_token())
        response = self.test_app.post('/consent?consent=false&{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('#error=access_denied'))

    @patch('frontend.frontend.requests.post')
    def test_consent_callback_unexpected_status_is_server_error(self, mock_post):
        """test an unexpected auth callback status redirects with server_error"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=200)
        response = self.test_app.post('/consent?consent=true&{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('#error=server_error'))

    @patch('frontend.frontend.requests.post')
    def test_consent_callback_unreachable_is_server_error(self, mock_post):
        """test an unreachable auth callback redirects with server_error"""
        self.set_token_cookie(make_token())
        mock_post.side_effect = RequestException('callback down')
        response = self.test_app.post('/consent?consent=true&{}'.format(self.OAUTH_ARGS))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('#error=server_error'))


class TestSignup(TestFrontend):
    """Tests for /signup"""

    @patch('frontend.frontend.requests.get')
    @patch('frontend.frontend.requests.post')
    def test_signup_success_logs_user_in(self, mock_post, mock_get):
        """test a successful signup logs the new user in"""
        token = make_token()
        mock_post.return_value = make_backend_response(status_code=201)
        mock_get.return_value = make_backend_response(json_body={'token': token})
        response = self.test_app.post('/signup', data=EXAMPLE_SIGNUP_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.location)
        cookie = next(c for c in response.headers.getlist('Set-Cookie')
                      if c.startswith('token='))
        self.assertIn(token, cookie)

    @patch('frontend.frontend.requests.post')
    def test_signup_conflict_redirects_with_error(self, mock_post):
        """test a rejected signup redirects with an error message"""
        mock_post.return_value = make_backend_response(status_code=409)
        response = self.test_app.post('/signup', data=EXAMPLE_SIGNUP_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Error: Account creation failed',
                      unquote_plus(response.location))

    @patch('frontend.frontend.requests.post')
    def test_signup_backend_unreachable_redirects_with_error(self, mock_post):
        """test an unreachable userservice redirects with an error message"""
        mock_post.side_effect = RequestException('userservice down')
        response = self.test_app.post('/signup', data=EXAMPLE_SIGNUP_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Error: Account creation failed',
                      unquote_plus(response.location))


class TestSlackNotifications(TestFrontend):
    """Tests for Slack error notifications"""

    def enable_slack(self):
        """Configure the Slack webhook on the test app"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.flask_app.config['SLACK_CHANNEL'] = SLACK_CHANNEL

    @patch('frontend.frontend.requests.post')
    def test_payment_failure_sends_slack_notification(self, mock_post):
        """test a failed payment posts a Slack notification"""
        self.enable_slack()
        self.set_token_cookie(make_token())
        rejection = make_backend_response(status_code=400, text='declined')
        mock_post.side_effect = [rejection, make_backend_response()]
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_post.call_count, 2)
        slack_call = mock_post.call_args_list[1]
        self.assertEqual(slack_call.kwargs['url'], SLACK_WEBHOOK_URL)
        payload = slack_call.kwargs['json']
        self.assertEqual(payload['channel'], SLACK_CHANNEL)
        self.assertIn('[frontend] /payment failed', payload['text'])

    @patch('frontend.frontend.requests.post')
    def test_no_slack_notification_when_webhook_unset(self, mock_post):
        """test no Slack notification is sent when no webhook is configured"""
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=400,
                                                       text='declined')
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 302)
        # only the transaction call; no Slack webhook call
        self.assertEqual(mock_post.call_count, 1)

    @patch('frontend.frontend.sleep')
    @patch('frontend.frontend.requests.post')
    def test_no_slack_notification_on_success(self, mock_post, _mock_sleep):
        """test no Slack notification is sent for a successful payment"""
        self.enable_slack()
        self.set_token_cookie(make_token())
        mock_post.return_value = make_backend_response(status_code=201)
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(mock_post.call_count, 1)
        self.assertNotEqual(mock_post.call_args.kwargs['url'], SLACK_WEBHOOK_URL)

    @patch('frontend.frontend.requests.post')
    def test_slack_notification_omits_channel_when_unset(self, mock_post):
        """test the Slack payload omits the channel when none is configured"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.flask_app.config['SLACK_CHANNEL'] = ''
        self.set_token_cookie(make_token())
        rejection = make_backend_response(status_code=400, text='declined')
        mock_post.side_effect = [rejection, make_backend_response()]
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 302)
        payload = mock_post.call_args_list[1].kwargs['json']
        self.assertNotIn('channel', payload)

    @patch('frontend.frontend.requests.post')
    def test_slack_failure_does_not_change_response(self, mock_post):
        """test a failing Slack webhook does not change the user response"""
        self.enable_slack()
        self.set_token_cookie(make_token())
        rejection = make_backend_response(status_code=400, text='declined')
        mock_post.side_effect = [rejection, RequestException('slack down')]
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment failed: declined', unquote_plus(response.location))

    @patch('frontend.frontend.requests.post')
    @patch('frontend.frontend.requests.get')
    def test_login_failure_sends_slack_notification(self, mock_get, mock_post):
        """test a failed login posts a Slack notification"""
        self.enable_slack()
        mock_get.side_effect = RequestException('userservice down')
        mock_post.return_value = make_backend_response()
        response = self.test_app.post('/login', data=EXAMPLE_LOGIN_FORM)
        self.assertEqual(response.status_code, 302)
        payload = mock_post.call_args.kwargs['json']
        self.assertIn('[frontend] /login failed', payload['text'])


class TestProbesAndMetadata(TestFrontend):
    """Tests for probe endpoints and app startup metadata handling"""

    def test_ready_endpoint_200_ok(self):
        """test the readiness probe returns ok"""
        response = self.test_app.get('/ready')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'ok')

    def test_version_endpoint_returns_version(self):
        """test the version endpoint returns the VERSION env var"""
        with patch.dict('os.environ', {'VERSION': 'v0.1.0'}):
            response = self.test_app.get('/version')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'v0.1.0')

    def test_whereami_defaults_when_metadata_unavailable(self):
        """test whereami falls back to defaults without a metadata server"""
        response = self.test_app.get('/whereami')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cluster: unknown', response.data)
        self.assertIn(b'Zone: unknown', response.data)

    def test_whereami_reports_metadata_cluster_and_zone(self):
        """test whereami reports cluster and zone from the metadata server"""
        cluster_resp = MagicMock(ok=True, text='test-cluster')
        zone_resp = MagicMock(ok=True,
                              text='projects/1/zones/us-central1-a')
        with patch('frontend.frontend.open',
                   mock_open(read_data=EXAMPLE_PUBLIC_KEY.decode('utf-8'))):
            with patch.dict('os.environ', EXAMPLE_ENVIRON, clear=True):
                with patch('frontend.frontend.requests.get',
                           side_effect=[cluster_resp, zone_resp]):
                    flask_app = create_app()
        flask_app.config['TESTING'] = True
        response = flask_app.test_client().get('/whereami')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cluster: test-cluster', response.data)
        self.assertIn(b'Zone: us-central1-a', response.data)

    def test_whereami_defaults_when_metadata_responses_not_ok(self):
        """test whereami falls back to defaults on non-OK metadata responses"""
        cluster_resp = MagicMock(ok=False)
        zone_resp = MagicMock(ok=False)
        with patch('frontend.frontend.open',
                   mock_open(read_data=EXAMPLE_PUBLIC_KEY.decode('utf-8'))):
            with patch.dict('os.environ', EXAMPLE_ENVIRON, clear=True):
                with patch('frontend.frontend.requests.get',
                           side_effect=[cluster_resp, zone_resp]):
                    flask_app = create_app()
        flask_app.config['TESTING'] = True
        response = flask_app.test_client().get('/whereami')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cluster: unknown', response.data)
        self.assertIn(b'Zone: unknown', response.data)

    @patch('frontend.frontend.Jinja2Instrumentor')
    @patch('frontend.frontend.RequestsInstrumentor')
    @patch('frontend.frontend.FlaskInstrumentor')
    @patch('frontend.frontend.CloudTraceSpanExporter')
    def test_create_app_with_tracing_enabled(self, mock_exporter, mock_flask,
                                             mock_requests, mock_jinja):
        """test app creation wires up tracing when ENABLE_TRACING is true"""
        environ = EXAMPLE_ENVIRON.copy()
        environ['ENABLE_TRACING'] = 'true'
        with patch('frontend.frontend.open',
                   mock_open(read_data=EXAMPLE_PUBLIC_KEY.decode('utf-8'))):
            with patch.dict('os.environ', environ, clear=True):
                with patch('frontend.frontend.requests.get',
                           side_effect=RequestException('metadata unavailable')):
                    flask_app = create_app()
        self.assertIsNotNone(flask_app)
        mock_exporter.assert_called_once()
        mock_flask.return_value.instrument_app.assert_called_once()
        mock_requests.return_value.instrument.assert_called_once()
        mock_jinja.return_value.instrument.assert_called_once()

    def test_create_app_with_each_supported_platform(self):
        """test app creation succeeds for every supported ENV_PLATFORM"""
        for platform in ['alibaba', 'aws', 'azure', 'gcp', 'local', 'onprem',
                         'unsupported-platform']:
            environ = EXAMPLE_ENVIRON.copy()
            environ['ENV_PLATFORM'] = platform
            with patch('frontend.frontend.open',
                       mock_open(read_data=EXAMPLE_PUBLIC_KEY.decode('utf-8'))):
                with patch.dict('os.environ', environ, clear=True):
                    with patch('frontend.frontend.requests.get',
                               side_effect=RequestException('metadata unavailable')):
                        flask_app = create_app()
            self.assertIsNotNone(flask_app,
                                 'app creation failed for {}'.format(platform))
