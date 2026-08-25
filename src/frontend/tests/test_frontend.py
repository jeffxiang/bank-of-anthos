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
Tests for frontend authentication and /payment error handling.
"""

import datetime
import os
import sys
import unittest
from unittest.mock import patch, mock_open, MagicMock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from requests.exceptions import HTTPError, RequestException

# frontend.py lives in the parent directory and uses flat imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from frontend import create_app


def generate_rsa_key():
    """Generate an ephemeral priv,pub key pair for test"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_key, public_key


PRIVATE_KEY, PUBLIC_KEY = generate_rsa_key()
OTHER_PRIVATE_KEY, _ = generate_rsa_key()

# Synthetic account data only
EXAMPLE_ACCOUNT_ID = '1011226111'
EXAMPLE_RECIPIENT_ID = '9099791699'
LOCAL_ROUTING = '883745000'
EXAMPLE_ENV = {
    'VERSION': '1',
    'ENABLE_TRACING': 'false',
    'PUB_KEY_PATH': '/dev/null',
    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
    'USERSERVICE_API_ADDR': 'userservice:8080',
    'BALANCES_API_ADDR': 'balancereader:8080',
    'HISTORY_API_ADDR': 'transactionhistory:8080',
    'CONTACTS_API_ADDR': 'contacts:8080',
    'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/test',
    'SLACK_CHANNEL': '#alerts',
}


def make_token(private_key=PRIVATE_KEY, expired=False):
    """Sign a synthetic session token"""
    now = datetime.datetime.now(datetime.timezone.utc)
    expiry = now - datetime.timedelta(hours=1) if expired \
        else now + datetime.timedelta(hours=1)
    return jwt.encode(
        {
            'user': 'jdoe',
            'acct': EXAMPLE_ACCOUNT_ID,
            'name': 'John Doe',
            'iat': now - datetime.timedelta(hours=2),
            'exp': expiry,
        },
        private_key,
        algorithm='RS256',
    )


VALID_TOKEN = make_token()


class TestFrontend(unittest.TestCase):
    """
    Test cases for frontend auth and payment error paths
    """

    def setUp(self):
        """Setup Flask TestClient with a mocked public key and environment"""
        # mock reading the userservice public key
        with patch('frontend.open', mock_open(read_data=PUBLIC_KEY)):
            with patch('os.environ', EXAMPLE_ENV.copy()):
                # the metadata server is unreachable outside of GCP
                with patch('frontend.requests.get',
                           side_effect=RequestException('no metadata server')):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

    def _set_token(self, token):
        """Attach a session token cookie to the test client"""
        self.test_app.set_cookie(self.flask_app.config['TOKEN_NAME'], token)

    def _payment_form(self):
        """Build a valid payment form submission"""
        return {
            'account_num': EXAMPLE_RECIPIENT_ID,
            'amount': '12.34',
            'uuid': '0e1f8b0a-4d33-4a5f-9d2a-2b1f0c3d4e5f',
        }

    @patch('frontend.requests.post')
    def test_payment_401_status_code_for_unverifiable_tokens(self, mock_post):
        """test payments are rejected when the session token does not verify"""
        # missing, malformed, foreign-signed and expired tokens all fail auth
        invalid_tokens = [
            '',
            'not-a-jwt',
            make_token(private_key=OTHER_PRIVATE_KEY),
            make_token(expired=True),
        ]
        for invalid_token in invalid_tokens:
            self._set_token(invalid_token)
            response = self.test_app.post('/payment', data=self._payment_form())
            self.assertEqual(response.status_code, 401,
                             'token {} returned incorrect status code'.format(invalid_token))
        # assert no transaction reached ledgerwriter
        mock_post.assert_not_called()

    @patch('frontend.requests.post')
    def test_payment_ledgerwriter_400_does_not_echo_session_token(self, mock_post):
        """test the session token is not rendered back when ledgerwriter returns 400"""
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.text = 'invalid transaction: insufficient balance'
        error_response.raise_for_status.side_effect = HTTPError('400 Client Error')
        mock_post.return_value = error_response
        self._set_token(VALID_TOKEN)

        response = self.test_app.post('/payment', data=self._payment_form())

        # the user is redirected back home with a failure message
        self.assertEqual(response.status_code, 302)
        self.assertIn('insufficient+balance', response.headers['Location'])
        # the token must not leak into the redirect target or the rendered body
        self.assertNotIn(VALID_TOKEN, response.headers['Location'])
        self.assertNotIn(VALID_TOKEN, response.get_data(as_text=True))
        # nor into the Slack alert raised for the failure
        slack_payload = mock_post.call_args.kwargs['json']
        self.assertNotIn(VALID_TOKEN, slack_payload['text'])

    @patch('frontend.requests.post')
    def test_payment_invalid_amount_302_status_code_no_transaction(self, mock_post):
        """test a non-numeric amount fails before any transaction is submitted"""
        self._set_token(VALID_TOKEN)
        payment_form = self._payment_form()
        payment_form['amount'] = 'not-a-number'

        response = self.test_app.post('/payment', data=payment_form)

        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        # only the Slack alert was posted, no transaction was submitted
        posted_urls = [call.kwargs['url'] for call in mock_post.call_args_list]
        self.assertNotIn(self.flask_app.config['TRANSACTIONS_URI'], posted_urls)
        # the alert must describe the failure without carrying the token
        slack_payload = mock_post.call_args.kwargs['json']
        self.assertIn('/payment failed', slack_payload['text'])
        self.assertNotIn(VALID_TOKEN, slack_payload['text'])

    def test_home_expired_token_302_status_code_redirects_to_login(self):
        """test an expired session token is not decoded but sent back to login"""
        self._set_token(make_token(expired=True))

        response = self.test_app.get('/home')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])


if __name__ == '__main__':
    unittest.main()
