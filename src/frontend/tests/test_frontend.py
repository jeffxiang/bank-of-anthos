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

import unittest
from unittest.mock import MagicMock, patch, mock_open

import requests
from requests.exceptions import HTTPError, RequestException

from frontend.frontend import create_app
from frontend.tests.constants import (
    EXAMPLE_ACCOUNT_ID,
    EXAMPLE_BALANCE,
    EXAMPLE_CONTACTS,
    EXAMPLE_DEPOSIT_REQUEST,
    EXAMPLE_DISPLAY_NAME,
    EXAMPLE_LOGIN_REQUEST,
    EXAMPLE_PAYMENT_REQUEST,
    EXAMPLE_PUBLIC_KEY,
    EXAMPLE_RECIPIENT_ACCOUNT_ID,
    EXAMPLE_SIGNUP_REQUEST,
    EXAMPLE_TOKEN,
    EXAMPLE_TRANSACTIONS,
    EXAMPLE_USERNAME,
    EXPIRED_TOKEN,
    EXTERNAL_ROUTING_NUM,
    FOREIGN_TOKEN,
    INVALID_AMOUNTS,
    LOCAL_ROUTING_NUM,
    SLACK_CHANNEL,
    SLACK_WEBHOOK_URL,
)

EXAMPLE_ENVIRONMENT = {
    'VERSION': '1',
    'ENABLE_TRACING': 'false',
    'PUB_KEY_PATH': '/tmp/publickey',
    'LOCAL_ROUTING_NUM': LOCAL_ROUTING_NUM,
    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
    'USERSERVICE_API_ADDR': 'userservice:8080',
    'BALANCES_API_ADDR': 'balancereader:8080',
    'HISTORY_API_ADDR': 'transactionhistory:8080',
    'CONTACTS_API_ADDR': 'contacts:8080',
    'CLUSTER_NAME': 'test-cluster',
    'POD_ZONE': 'test-zone',
    'SCHEME': 'http',
}


def backend_get(url, **_kwargs):
    """Fake responses for the read-only backends queried by /home"""
    response = MagicMock()
    if '/balances' in url:
        response.json.return_value = EXAMPLE_BALANCE
    elif '/transactions' in url:
        response.json.return_value = EXAMPLE_TRANSACTIONS
    else:
        response.json.return_value = EXAMPLE_CONTACTS
    return response


def created_response():
    """A successful backend write response"""
    response = MagicMock()
    response.status_code = 201
    response.raise_for_status.return_value = None
    return response


def error_response(status_code=400, text='invalid transaction'):
    """A failing backend write response, as returned by ledgerwriter"""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.raise_for_status.side_effect = HTTPError(text)
    return response


class FrontendTestCase(unittest.TestCase):
    """
    Base test case that builds a frontend app with all external I/O mocked out
    """

    def build_app(self, environment=None, metadata_response=None):
        """Create a frontend app instance with mocked env vars and key material"""
        env = dict(EXAMPLE_ENVIRONMENT)
        env.update(environment or {})
        # the app reads env vars both at startup and per request
        env_patcher = patch('os.environ', env)
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        # mock reading the userservice public key from disk
        with patch('frontend.frontend.open',
                   mock_open(read_data=EXAMPLE_PUBLIC_KEY)):
            # mock the GCE metadata server lookups done at startup
            if metadata_response is None:
                metadata = patch('frontend.frontend.requests.get',
                                 side_effect=RequestException('no metadata server'))
            else:
                metadata = patch('frontend.frontend.requests.get',
                                 return_value=metadata_response)
            with metadata:
                return create_app()

    def patch_sleep(self):
        """Skip the propagation delay after a successful transaction"""
        sleep_patcher = patch('frontend.frontend.sleep')
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def set_token(self, token=EXAMPLE_TOKEN):
        """Set the auth cookie on the test client"""
        self.test_app.set_cookie('token', token, domain='localhost')


class FrontendAppTestCase(FrontendTestCase):
    """
    Base test case with a default frontend app and mocked read-only backends
    """

    def setUp(self):
        """Setup Flask TestClient with mocked key material and backends"""
        self.flask_app = self.build_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.patch_sleep()
        backend_patcher = patch('api_call.get', side_effect=backend_get)
        self.mocked_backend_get = backend_patcher.start()
        self.addCleanup(backend_patcher.stop)


class TestFrontend(FrontendAppTestCase):
    """
    Test cases for the probe and account overview endpoints of frontend
    """

    def test_version_endpoint_returns_200_status_code_correct_version(self):
        """test if correct version is returned"""
        response = self.test_app.get('/version')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'1')

    def test_ready_endpoint_200_status_code_ok_string(self):
        """test if correct response is returned from readiness probe"""
        response = self.test_app.get('/ready')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'ok')

    def test_whereami_endpoint_200_status_code_cluster_and_zone(self):
        """test the whereami endpoint reports cluster and zone"""
        response = self.test_app.get('/whereami')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cluster: test-cluster', response.data)
        self.assertIn(b'Zone: test-zone', response.data)

    def test_root_without_token_renders_login_page(self):
        """test the root path renders the login page when unauthenticated"""
        response = self.test_app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sign in', response.data)

    def test_root_with_valid_token_renders_home_page(self):
        """test the root path renders the home page when authenticated"""
        self.set_token()
        response = self.test_app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(EXAMPLE_ACCOUNT_ID.encode(), response.data)

    def test_home_without_token_redirects_to_login(self):
        """test /home redirects to the login page when no cookie is present"""
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_home_with_foreign_signed_token_redirects_to_login(self):
        """test /home rejects a valid token signed by an untrusted key"""
        self.set_token(FOREIGN_TOKEN)
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_home_with_expired_token_redirects_to_login(self):
        """test /home rejects a correctly signed but expired token"""
        self.set_token(EXPIRED_TOKEN)
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_home_with_malformed_token_redirects_to_login(self):
        """test /home rejects a token that is not a JWT at all"""
        self.set_token('not-a-jwt')
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_home_with_valid_token_renders_account_data(self):
        """test /home renders the balance, history and contacts of the user"""
        self.set_token()
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 200)
        self.assertIn(EXAMPLE_DISPLAY_NAME.encode(), response.data)
        self.assertIn(b'$123.45', response.data)
        # transactions with a known counterparty are labelled with the contact
        self.assertIn(b'Friend', response.data)

    def test_home_with_failing_backends_renders_page(self):
        """test /home still renders when the backend calls all fail"""
        self.mocked_backend_get.side_effect = RequestException('backend down')
        self.set_token()
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 200)
        # balance is unknown so the placeholder amount is rendered
        self.assertIn(b'$---', response.data)


class TestFrontendTransactions(FrontendAppTestCase):
    """
    Test cases for the /payment and /deposit endpoints of frontend
    """

    @patch('frontend.frontend.requests.post', return_value=created_response())
    def test_payment_303_status_code_submits_transaction(self, mock_post):
        """test a valid payment is submitted to ledgerwriter"""
        self.set_token()
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 303)
        self.assertIn('msg=Payment+successful', response.headers['Location'])
        transaction = mock_post.call_args.kwargs['data']
        self.assertIn(b'"amount":1234', transaction)
        self.assertIn('"fromAccountNum":"{}"'.format(EXAMPLE_ACCOUNT_ID).encode(),
                      transaction)
        self.assertIn('"toAccountNum":"{}"'.format(EXAMPLE_RECIPIENT_ACCOUNT_ID).encode(),
                      transaction)

    @patch('frontend.frontend.requests.post', return_value=created_response())
    def test_payment_authorization_header_carries_token(self, mock_post):
        """test the user's token is forwarded to ledgerwriter"""
        self.set_token()
        self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(mock_post.call_args.kwargs['headers']['Authorization'],
                         'Bearer ' + EXAMPLE_TOKEN)

    @patch('frontend.frontend.requests.post')
    def test_payment_401_status_code_without_token(self, mock_post):
        """test an unauthenticated payment is rejected without calling backends"""
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post')
    def test_payment_401_status_code_with_foreign_signed_token(self, mock_post):
        """test a payment with a token signed by an untrusted key is rejected"""
        self.set_token(FOREIGN_TOKEN)
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post')
    def test_payment_401_status_code_with_expired_token(self, mock_post):
        """test a payment with an expired token is rejected"""
        self.set_token(EXPIRED_TOKEN)
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post', return_value=error_response())
    def test_payment_declined_by_ledgerwriter_redirects_with_reason(self, _mock_post):
        """test a payment rejected by ledgerwriter surfaces the reason"""
        self.set_token()
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed:+invalid+transaction',
                      response.headers['Location'])

    @patch('frontend.frontend.requests.post',
           side_effect=RequestException('ledgerwriter down'))
    def test_payment_backend_unreachable_redirects_with_generic_failure(self, _mock_post):
        """test a payment fails generically when ledgerwriter is unreachable"""
        self.set_token()
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])

    @patch('frontend.frontend.requests.post')
    def test_payment_invalid_amount_redirects_with_failure(self, mock_post):
        """test non-numeric payment amounts are rejected before any backend call"""
        self.set_token()
        for invalid_amount in INVALID_AMOUNTS:
            payment_request = EXAMPLE_PAYMENT_REQUEST.copy()
            payment_request['amount'] = invalid_amount
            response = self.test_app.post('/payment', data=payment_request)
            self.assertEqual(response.status_code, 302,
                             'amount {} returned incorrect status code'.format(
                                 invalid_amount))
            self.assertIn('msg=Payment+failed', response.headers['Location'],
                          'amount {} returned unexpected message'.format(invalid_amount))
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post', return_value=created_response())
    def test_payment_new_contact_adds_contact_then_transaction(self, mock_post):
        """test paying a new recipient with a label also creates the contact"""
        self.set_token()
        payment_request = EXAMPLE_PAYMENT_REQUEST.copy()
        payment_request['account_num'] = 'add'
        payment_request['contact_account_num'] = EXAMPLE_RECIPIENT_ACCOUNT_ID
        payment_request['contact_label'] = 'Friend'
        response = self.test_app.post('/payment', data=payment_request)
        self.assertEqual(response.status_code, 303)
        contact_url, transaction_url = [call.kwargs['url'] for call in mock_post.call_args_list]
        self.assertTrue(contact_url.endswith('/contacts/{}'.format(EXAMPLE_USERNAME)))
        self.assertTrue(transaction_url.endswith('/transactions'))

    @patch('frontend.frontend.requests.post', return_value=created_response())
    def test_payment_new_contact_without_label_is_not_saved(self, mock_post):
        """test paying a new recipient without a label saves no contact"""
        self.set_token()
        payment_request = EXAMPLE_PAYMENT_REQUEST.copy()
        payment_request['account_num'] = 'add'
        payment_request['contact_account_num'] = EXAMPLE_RECIPIENT_ACCOUNT_ID
        response = self.test_app.post('/payment', data=payment_request)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(mock_post.call_count, 1)

    @patch('frontend.frontend.requests.post', return_value=error_response(text='bad contact'))
    def test_payment_contact_rejected_redirects_with_reason(self, _mock_post):
        """test a payment fails when the contact service rejects the new contact"""
        self.set_token()
        payment_request = EXAMPLE_PAYMENT_REQUEST.copy()
        payment_request['account_num'] = 'add'
        payment_request['contact_account_num'] = EXAMPLE_RECIPIENT_ACCOUNT_ID
        payment_request['contact_label'] = 'Friend'
        response = self.test_app.post('/payment', data=payment_request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed:+bad+contact', response.headers['Location'])

    @patch('frontend.frontend.requests.post')
    def test_payment_missing_form_field_400_status_code(self, mock_post):
        """test a payment without the required form fields is a bad request"""
        self.set_token()
        for missing_field in EXAMPLE_PAYMENT_REQUEST:
            payment_request = EXAMPLE_PAYMENT_REQUEST.copy()
            payment_request.pop(missing_field)
            response = self.test_app.post('/payment', data=payment_request)
            self.assertEqual(response.status_code, 400,
                             'missing {} returned incorrect status code'.format(
                                 missing_field))
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post', return_value=created_response())
    def test_deposit_303_status_code_submits_transaction(self, mock_post):
        """test a deposit from an existing external account is submitted"""
        self.set_token()
        response = self.test_app.post('/deposit', data=EXAMPLE_DEPOSIT_REQUEST)
        self.assertEqual(response.status_code, 303)
        self.assertIn('msg=Deposit+successful', response.headers['Location'])
        transaction = mock_post.call_args.kwargs['data']
        self.assertIn(b'"amount":10000', transaction)
        self.assertIn('"fromRoutingNum":"{}"'.format(EXTERNAL_ROUTING_NUM).encode(),
                      transaction)
        self.assertIn('"toAccountNum":"{}"'.format(EXAMPLE_ACCOUNT_ID).encode(),
                      transaction)

    @patch('frontend.frontend.requests.post')
    def test_deposit_401_status_code_without_token(self, mock_post):
        """test an unauthenticated deposit is rejected without calling backends"""
        response = self.test_app.post('/deposit', data=EXAMPLE_DEPOSIT_REQUEST)
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post')
    def test_deposit_local_routing_number_redirects_with_reason(self, mock_post):
        """test a deposit from the bank's own routing number is rejected"""
        self.set_token()
        deposit_request = {
            'account': 'add',
            'external_account_num': '0000000000',
            'external_routing_num': LOCAL_ROUTING_NUM,
            'external_label': 'External',
            'amount': '100.00',
            'uuid': EXAMPLE_DEPOSIT_REQUEST['uuid'],
        }
        response = self.test_app.post('/deposit', data=deposit_request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Deposit+failed:+invalid+routing+number',
                      response.headers['Location'])
        mock_post.assert_not_called()

    @patch('frontend.frontend.requests.post', return_value=created_response())
    def test_deposit_new_external_account_adds_contact(self, mock_post):
        """test depositing from a new labelled external account saves it"""
        self.set_token()
        deposit_request = {
            'account': 'add',
            'external_account_num': '0000000000',
            'external_routing_num': EXTERNAL_ROUTING_NUM,
            'external_label': 'External',
            'amount': '100.00',
            'uuid': EXAMPLE_DEPOSIT_REQUEST['uuid'],
        }
        response = self.test_app.post('/deposit', data=deposit_request)
        self.assertEqual(response.status_code, 303)
        contact_data = mock_post.call_args_list[0].kwargs['data']
        self.assertIn(b'"is_external":true', contact_data)

    @patch('frontend.frontend.requests.post', return_value=created_response())
    def test_deposit_new_external_account_without_label_is_not_saved(self, mock_post):
        """test depositing from a new unlabelled external account saves nothing"""
        self.set_token()
        deposit_request = {
            'account': 'add',
            'external_account_num': '0000000000',
            'external_routing_num': EXTERNAL_ROUTING_NUM,
            'amount': '100.00',
            'uuid': EXAMPLE_DEPOSIT_REQUEST['uuid'],
        }
        response = self.test_app.post('/deposit', data=deposit_request)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(mock_post.call_count, 1)

    @patch('frontend.frontend.requests.post', return_value=error_response())
    def test_deposit_declined_by_ledgerwriter_redirects_with_reason(self, _mock_post):
        """test a deposit rejected by ledgerwriter surfaces the reason"""
        self.set_token()
        response = self.test_app.post('/deposit', data=EXAMPLE_DEPOSIT_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Deposit+failed:+invalid+transaction',
                      response.headers['Location'])

    @patch('frontend.frontend.requests.post',
           side_effect=RequestException('ledgerwriter down'))
    def test_deposit_backend_unreachable_redirects_with_generic_failure(self, _mock_post):
        """test a deposit fails generically when ledgerwriter is unreachable"""
        self.set_token()
        response = self.test_app.post('/deposit', data=EXAMPLE_DEPOSIT_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Deposit+failed', response.headers['Location'])


class TestFrontendAuthRoutes(FrontendAppTestCase):
    """
    Test cases for the login, logout and signup endpoints of frontend
    """

    @patch('frontend.frontend.requests.post')
    def test_login_200_status_code_sets_scoped_token_cookie(self, _mock_post):
        """test a successful login stores the token in a cookie"""
        login_response = MagicMock()
        login_response.raise_for_status.return_value = None
        login_response.json.return_value = {'token': EXAMPLE_TOKEN}
        with patch('frontend.frontend.requests.get', return_value=login_response):
            response = self.test_app.post('/login', data=EXAMPLE_LOGIN_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.headers['Location'])
        cookie = response.headers['Set-Cookie']
        self.assertIn('token={}'.format(EXAMPLE_TOKEN), cookie)
        # cookie lifetime matches the token lifetime
        self.assertIn('Max-Age=3600', cookie)

    def test_login_rejected_by_userservice_redirects_with_failure(self):
        """test a login rejected by userservice sets no cookie"""
        with patch('frontend.frontend.requests.get',
                   side_effect=HTTPError('401 Client Error')):
            response = self.test_app.post('/login', data=EXAMPLE_LOGIN_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Login+Failed', response.headers['Location'])
        self.assertNotIn('Set-Cookie', response.headers)

    def test_login_userservice_unreachable_redirects_with_failure(self):
        """test a login fails when userservice is unreachable"""
        with patch('frontend.frontend.requests.get',
                   side_effect=RequestException('userservice down')):
            response = self.test_app.post('/login', data=EXAMPLE_LOGIN_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Login+Failed', response.headers['Location'])

    def test_login_page_with_valid_token_redirects_to_home(self):
        """test the login page redirects an already authenticated user"""
        self.set_token()
        response = self.test_app.get('/login')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.headers['Location'])

    def test_login_page_shows_message_from_query_string(self):
        """test the login page renders the failure message it is given"""
        response = self.test_app.get('/login',
                                     query_string={'msg': 'Error: Invalid client_id'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Error: Invalid client_id', response.data)

    def test_logout_deletes_auth_cookies(self):
        """test logging out clears the token and consent cookies"""
        self.set_token()
        response = self.test_app.post('/logout')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])
        cookies = response.headers.getlist('Set-Cookie')
        self.assertTrue(any('token=;' in cookie for cookie in cookies))
        self.assertTrue(any('consented=;' in cookie for cookie in cookies))

    def test_signup_page_with_valid_token_redirects_to_home(self):
        """test the signup page redirects an already authenticated user"""
        self.set_token()
        response = self.test_app.get('/signup')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.headers['Location'])

    def test_signup_page_without_token_renders_form(self):
        """test the signup page renders for an anonymous user"""
        response = self.test_app.get('/signup')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Register a new account', response.data)

    def test_signup_201_status_code_logs_new_user_in(self):
        """test a successful signup logs the new user in"""
        login_response = MagicMock()
        login_response.raise_for_status.return_value = None
        login_response.json.return_value = {'token': EXAMPLE_TOKEN}
        with patch('frontend.frontend.requests.post', return_value=created_response()):
            with patch('frontend.frontend.requests.get', return_value=login_response):
                response = self.test_app.post('/signup', data=EXAMPLE_SIGNUP_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.headers['Location'])
        self.assertIn('token={}'.format(EXAMPLE_TOKEN), response.headers['Set-Cookie'])

    @patch('frontend.frontend.requests.post', return_value=error_response(status_code=409))
    def test_signup_rejected_by_userservice_redirects_with_failure(self, _mock_post):
        """test a signup rejected by userservice does not log the user in"""
        response = self.test_app.post('/signup', data=EXAMPLE_SIGNUP_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Error:+Account+creation+failed', response.headers['Location'])
        self.assertNotIn('Set-Cookie', response.headers)

    @patch('frontend.frontend.requests.post',
           side_effect=RequestException('userservice down'))
    def test_signup_userservice_unreachable_redirects_with_failure(self, _mock_post):
        """test a signup fails when userservice is unreachable"""
        response = self.test_app.post('/signup', data=EXAMPLE_SIGNUP_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Error:+Account+creation+failed', response.headers['Location'])


class TestFrontendFormatters(FrontendAppTestCase):
    """
    Test cases for the template formatting helpers of frontend
    """

    def test_format_currency_handles_none_and_negative_amounts(self):
        """test the currency filter formats missing and negative amounts"""
        format_currency = self.flask_app.jinja_env.globals['format_currency']
        self.assertEqual(format_currency(None), '$---')
        self.assertEqual(format_currency(0), '$0.00')
        self.assertEqual(format_currency(123456), '$1,234.56')
        self.assertEqual(format_currency(-500), '-$5.00')

    def test_format_timestamp_returns_day_and_month(self):
        """test the timestamp filters format the day and month"""
        format_day = self.flask_app.jinja_env.globals['format_timestamp_day']
        format_month = self.flask_app.jinja_env.globals['format_timestamp_month']
        timestamp = EXAMPLE_TRANSACTIONS[0]['timestamp']
        self.assertEqual(format_day(timestamp), '01')
        self.assertEqual(format_month(timestamp), 'Jan')


class TestFrontendSlackNotifications(FrontendTestCase):
    """
    Test cases for the error notifications posted by frontend
    """

    def setUp(self):
        """Setup Flask TestClient with Slack notifications enabled"""
        self.flask_app = self.build_app({'SLACK_WEBHOOK_URL': SLACK_WEBHOOK_URL,
                                         'SLACK_CHANNEL': SLACK_CHANNEL})
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.set_token()
        self.patch_sleep()

    @staticmethod
    def slack_calls(mock_post):
        """The Slack webhook calls made through the mocked requests.post"""
        return [call for call in mock_post.call_args_list
                if call.kwargs['url'] == SLACK_WEBHOOK_URL]

    def test_slack_notification_sent_when_payment_declined(self):
        """test a Slack notification is posted when a payment is declined"""
        with patch('frontend.frontend.requests.post') as mock_post:
            mock_post.side_effect = [error_response(), MagicMock()]
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 302)
        payload = self.slack_calls(mock_post)[0].kwargs['json']
        self.assertEqual(payload['channel'], SLACK_CHANNEL)
        self.assertIn('[frontend] /payment failed', payload['text'])

    def test_slack_notification_sent_when_payment_amount_invalid(self):
        """test a Slack notification is posted when a payment amount is invalid"""
        payment_request = EXAMPLE_PAYMENT_REQUEST.copy()
        payment_request['amount'] = 'abc'
        with patch('frontend.frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=payment_request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('[frontend] /payment failed',
                      self.slack_calls(mock_post)[0].kwargs['json']['text'])

    def test_slack_notification_sent_when_deposit_declined(self):
        """test a Slack notification is posted when a deposit is declined"""
        with patch('frontend.frontend.requests.post') as mock_post:
            mock_post.side_effect = [error_response(), MagicMock()]
            response = self.test_app.post('/deposit', data=EXAMPLE_DEPOSIT_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('[frontend] /deposit failed',
                      self.slack_calls(mock_post)[0].kwargs['json']['text'])

    def test_slack_notification_sent_when_login_fails(self):
        """test a Slack notification is posted when a login fails"""
        with patch('frontend.frontend.requests.post') as mock_post:
            with patch('frontend.frontend.requests.get',
                       side_effect=RequestException('userservice down')):
                response = self.test_app.post('/login', data=EXAMPLE_LOGIN_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('[frontend] /login failed',
                      self.slack_calls(mock_post)[0].kwargs['json']['text'])

    def test_slack_notification_sent_when_signup_fails(self):
        """test a Slack notification is posted when a signup fails"""
        with patch('frontend.frontend.requests.post') as mock_post:
            mock_post.side_effect = [RequestException('userservice down'), MagicMock()]
            response = self.test_app.post('/signup', data=EXAMPLE_SIGNUP_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('[frontend] /signup failed',
                      self.slack_calls(mock_post)[0].kwargs['json']['text'])

    def test_no_slack_notification_on_successful_payment(self):
        """test no Slack notification is sent when a payment succeeds"""
        with patch('frontend.frontend.requests.post',
                   return_value=created_response()) as mock_post:
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.slack_calls(mock_post), [])

    def test_no_slack_notification_when_webhook_unset(self):
        """test no Slack notification is sent when no webhook is configured"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = ''
        with patch('frontend.frontend.requests.post') as mock_post:
            mock_post.side_effect = [error_response(), MagicMock()]
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.slack_calls(mock_post), [])

    def test_slack_notification_omits_channel_when_unset(self):
        """test the Slack payload has no channel when none is configured"""
        self.flask_app.config['SLACK_CHANNEL'] = ''
        with patch('frontend.frontend.requests.post') as mock_post:
            mock_post.side_effect = [error_response(), MagicMock()]
            self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertNotIn('channel', self.slack_calls(mock_post)[0].kwargs['json'])

    def test_slack_failure_does_not_affect_response(self):
        """test a failing Slack webhook does not change the error response"""
        with patch('frontend.frontend.requests.post') as mock_post:
            mock_post.side_effect = [error_response(),
                                     RequestException('slack down')]
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed:+invalid+transaction',
                      response.headers['Location'])


class TestFrontendConfiguration(FrontendTestCase):
    """
    Test cases for the startup configuration of frontend
    """

    def test_platform_display_names_are_resolved(self):
        """test each supported platform gets a display name"""
        expected_display_names = {
            'alibaba': 'Alibaba Cloud',
            'aws': 'AWS',
            'azure': 'Azure',
            'gcp': 'Google Cloud',
            'local': 'Local',
            'onprem': 'On-Premises',
        }
        for platform, display_name in expected_display_names.items():
            app = self.build_app({'ENV_PLATFORM': platform.upper()})
            response = app.test_client().get('/login')
            self.assertIn(display_name.encode(), response.data,
                          'platform {} has no display name'.format(platform))

    def test_unsupported_platform_is_ignored(self):
        """test an unsupported platform does not fail startup"""
        app = self.build_app({'ENV_PLATFORM': 'mainframe'})
        response = app.test_client().get('/login')
        self.assertEqual(response.status_code, 200)

    def test_cluster_metadata_falls_back_to_env_when_metadata_not_ok(self):
        """test env values are kept when the metadata server returns an error"""
        metadata_response = MagicMock()
        metadata_response.ok = False
        app = self.build_app(metadata_response=metadata_response)
        response = app.test_client().get('/whereami')
        self.assertIn(b'Zone: test-zone', response.data)
        self.assertIn(b'Cluster: test-cluster', response.data)

    def test_cluster_metadata_read_from_metadata_server(self):
        """test cluster name and zone come from the metadata server"""
        metadata_response = MagicMock()
        metadata_response.ok = True
        metadata_response.text = 'projects/1/zones/metadata-zone'
        app = self.build_app(metadata_response=metadata_response)
        response = app.test_client().get('/whereami')
        self.assertIn(b'Zone: metadata-zone', response.data)

    def test_tracing_enabled_instruments_app(self):
        """test enabling tracing does not break app creation"""
        with patch('frontend.frontend.CloudTraceSpanExporter'):
            with patch('frontend.frontend.FlaskInstrumentor'):
                with patch('frontend.frontend.RequestsInstrumentor'):
                    with patch('frontend.frontend.Jinja2Instrumentor'):
                        app = self.build_app({'ENABLE_TRACING': 'true'})
        response = app.test_client().get('/ready')
        self.assertEqual(response.status_code, 200)


class TestOauthFlow(FrontendTestCase):
    """
    Test cases for the OAuth consent flow
    """

    REGISTERED_CLIENT_ID = 'registered-client'
    ALLOWED_REDIRECT_URI = 'http://client.example.com/callback'

    def setUp(self):
        """Setup Flask TestClient with an OAuth client registered"""
        self.flask_app = self.build_app({
            'REGISTERED_OAUTH_CLIENT_ID': self.REGISTERED_CLIENT_ID,
            'ALLOWED_OAUTH_REDIRECT_URI': self.ALLOWED_REDIRECT_URI,
        })
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

    def oauth_query(self, **overrides):
        """Query string for an OAuth authorization request"""
        query = {
            'response_type': 'code',
            'client_id': self.REGISTERED_CLIENT_ID,
            'redirect_uri': self.ALLOWED_REDIRECT_URI,
            'app_name': 'Example App',
            'state': 'state-123',
        }
        query.update(overrides)
        return query

    def test_oauth_login_invalid_client_id_redirects_with_error(self):
        """test an unregistered client_id is rejected"""
        response = self.test_app.get('/login',
                                     query_string=self.oauth_query(client_id='attacker'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Error:+Invalid+client_id', response.headers['Location'])

    def test_oauth_login_invalid_redirect_uri_redirects_with_error(self):
        """test an unregistered redirect_uri is rejected"""
        query = self.oauth_query(redirect_uri='http://attacker.example.com')
        response = self.test_app.get('/login', query_string=query)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Error:+Invalid+redirect_uri', response.headers['Location'])

    def test_oauth_login_authenticated_user_redirects_to_consent(self):
        """test an authenticated user is sent to the consent page"""
        self.set_token()
        response = self.test_app.get('/login', query_string=self.oauth_query())
        self.assertEqual(response.status_code, 302)
        self.assertIn('/consent', response.headers['Location'])

    def test_oauth_login_anonymous_user_renders_login_page(self):
        """test an anonymous user is shown the login page"""
        response = self.test_app.get('/login', query_string=self.oauth_query())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Example App', response.data)

    def test_oauth_login_post_redirects_to_consent_with_token_cookie(self):
        """test an OAuth login sends the user on to the consent page"""
        login_response = MagicMock()
        login_response.raise_for_status.return_value = None
        login_response.json.return_value = {'token': EXAMPLE_TOKEN}
        with patch('frontend.frontend.requests.get', return_value=login_response):
            response = self.test_app.post('/login',
                                          query_string=self.oauth_query(),
                                          data=EXAMPLE_LOGIN_REQUEST)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/consent', response.headers['Location'])
        self.assertIn('token={}'.format(EXAMPLE_TOKEN), response.headers['Set-Cookie'])

    def test_consent_page_without_token_redirects_to_login(self):
        """test the consent page redirects unauthenticated users to login"""
        response = self.test_app.get('/consent', query_string=self.oauth_query())
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_consent_page_with_token_renders_consent_form(self):
        """test the consent page renders for an authenticated user"""
        self.test_app.set_cookie('token', EXAMPLE_TOKEN, domain='localhost')
        response = self.test_app.get('/consent', query_string=self.oauth_query())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Example App', response.data)

    def test_consent_page_with_prior_consent_returns_auth_code(self):
        """test a user who already consented is redirected to the client"""
        self.test_app.set_cookie('token', EXAMPLE_TOKEN, domain='localhost')
        self.test_app.set_cookie('consented', 'true', domain='localhost')
        callback_response = MagicMock()
        callback_response.status_code = requests.codes.found
        callback_response.headers = {'Location': self.ALLOWED_REDIRECT_URI + '?code=abc'}
        with patch('frontend.frontend.requests.post', return_value=callback_response):
            response = self.test_app.get('/consent', query_string=self.oauth_query())
        self.assertEqual(response.status_code, 302)
        self.assertIn('code=abc', response.headers['Location'])

    def test_consent_granted_sets_consent_cookie(self):
        """test granting consent stores the consent cookie"""
        self.test_app.set_cookie('token', EXAMPLE_TOKEN, domain='localhost')
        callback_response = MagicMock()
        callback_response.status_code = requests.codes.found
        callback_response.headers = {'Location': self.ALLOWED_REDIRECT_URI + '?code=abc'}
        with patch('frontend.frontend.requests.post', return_value=callback_response):
            response = self.test_app.post('/consent',
                                          query_string={'consent': 'true',
                                                        'state': 'state-123',
                                                        'redirect_uri':
                                                            self.ALLOWED_REDIRECT_URI})
        self.assertEqual(response.status_code, 302)
        self.assertIn('consented=true', response.headers['Set-Cookie'])

    def test_consent_denied_redirects_with_access_denied(self):
        """test denying consent reports access_denied to the client"""
        self.test_app.set_cookie('token', EXAMPLE_TOKEN, domain='localhost')
        response = self.test_app.post('/consent',
                                      query_string={'consent': 'false',
                                                    'state': 'state-123',
                                                    'redirect_uri':
                                                        self.ALLOWED_REDIRECT_URI})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'],
                         self.ALLOWED_REDIRECT_URI + '#error=access_denied')

    def test_consent_unexpected_callback_status_redirects_with_server_error(self):
        """test an unexpected callback status reports server_error"""
        self.test_app.set_cookie('token', EXAMPLE_TOKEN, domain='localhost')
        callback_response = MagicMock()
        callback_response.status_code = 500
        with patch('frontend.frontend.requests.post', return_value=callback_response):
            response = self.test_app.post('/consent',
                                          query_string={'consent': 'true',
                                                        'state': 'state-123',
                                                        'redirect_uri':
                                                            self.ALLOWED_REDIRECT_URI})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'],
                         self.ALLOWED_REDIRECT_URI + '#error=server_error')

    def test_consent_callback_unreachable_redirects_with_server_error(self):
        """test an unreachable callback endpoint reports server_error"""
        self.test_app.set_cookie('token', EXAMPLE_TOKEN, domain='localhost')
        with patch('frontend.frontend.requests.post',
                   side_effect=RequestException('client down')):
            response = self.test_app.post('/consent',
                                          query_string={'consent': 'true',
                                                        'state': 'state-123',
                                                        'redirect_uri':
                                                            self.ALLOWED_REDIRECT_URI})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'],
                         self.ALLOWED_REDIRECT_URI + '#error=server_error')
