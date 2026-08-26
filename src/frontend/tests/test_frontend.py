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
Tests for frontend /payment error handling and auth-cookie behavior
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from requests.exceptions import HTTPError, RequestException
import jwt

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import create_app  # pylint: disable=wrong-import-position


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


EXAMPLE_PRIVATE_KEY, EXAMPLE_PUBLIC_KEY = generate_rsa_key()
EXAMPLE_ACCOUNT_ID = '1234567890'
EXAMPLE_PAYMENT_REQUEST = {
    'account_num': '9876543210',
    'amount': '12.34',
    'uuid': 'f8c1b0e6-0000-4000-8000-000000000000',
}
LOCAL_ROUTING_NUM = '883745000'
SLACK_CHANNEL = '#bofa-alerts'
SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/T000/B000/XXXX'


class TestFrontend(unittest.TestCase):
    """
    Test cases for the frontend /payment endpoint
    """

    def setUp(self):
        """Setup Flask TestClient with a mocked public key and env vars"""
        # mock reading the userservice public key from disk
        with patch('frontend.open', mock_open(read_data=EXAMPLE_PUBLIC_KEY)):
            # mock env vars
            with patch(
                'os.environ',
                {
                    'VERSION': '1',
                    'ENABLE_TRACING': 'false',
                    'PUB_KEY_PATH': '1',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING_NUM,
                    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
                    'USERSERVICE_API_ADDR': 'userservice:8080',
                    'BALANCES_API_ADDR': 'balancereader:8080',
                    'HISTORY_API_ADDR': 'transactionhistory:8080',
                    'CONTACTS_API_ADDR': 'contacts:8080',
                    'SLACK_WEBHOOK_URL': SLACK_WEBHOOK_URL,
                    'SLACK_CHANNEL': SLACK_CHANNEL,
                },
            ):
                # the metadata server is unreachable outside of GCP
                with patch('frontend.requests.get', side_effect=RequestException()):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.token = jwt.encode(
            {
                'user': 'jdoe',
                'acct': EXAMPLE_ACCOUNT_ID,
                'name': 'John Doe',
                'iat': 0,
                'exp': 2 ** 31,
            },
            EXAMPLE_PRIVATE_KEY,
            algorithm='RS256',
        )

    def _authenticate(self):
        """Set a valid token cookie on the test client"""
        self.test_app.set_cookie('token', self.token, domain='localhost')

    def test_payment_401_when_token_cookie_is_invalid(self):
        """test that an unverifiable token cookie is rejected and never echoed"""
        # sign a token with a key the frontend does not trust
        foreign_private_key, _ = generate_rsa_key()
        forged_token = jwt.encode({'acct': EXAMPLE_ACCOUNT_ID},
                                  foreign_private_key,
                                  algorithm='RS256')
        self.test_app.set_cookie('token', forged_token, domain='localhost')
        # send payment request with the forged token
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        # assert 401 response code
        self.assertEqual(response.status_code, 401)
        # assert the rejected token is not echoed back to the client
        self.assertNotIn(forged_token, response.get_data(as_text=True))

    @patch('frontend.requests.post')
    def test_payment_ledgerwriter_error_redirect_omits_token(self, mock_post):
        """test that a ledgerwriter 4xx surfaces a message without the token"""
        self._authenticate()
        mock_post.return_value = MagicMock(
            status_code=400,
            text='transaction rejected: recipient screened',
        )
        mock_post.return_value.raise_for_status.side_effect = HTTPError()
        # send payment request with a valid token
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        # assert the user is redirected back home with the backend message
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        # assert the session token leaks into neither the redirect nor the body
        self.assertNotIn(self.token, response.headers['Location'])
        self.assertNotIn(self.token, response.get_data(as_text=True))

    @patch('frontend.requests.post')
    def test_payment_invalid_amount_redirect_omits_token(self, mock_post):
        """test that a non-numeric amount fails without leaking the token"""
        self._authenticate()
        invalid_payment = dict(EXAMPLE_PAYMENT_REQUEST, amount='not-a-number')
        # send payment request with an unparseable amount
        response = self.test_app.post('/payment', data=invalid_payment)
        # assert the transaction was never submitted to ledgerwriter
        self.assertEqual(mock_post.call_args.kwargs['url'], SLACK_WEBHOOK_URL)
        # assert the user is redirected back home with a generic failure
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        # assert the session token leaks into neither the redirect nor the body
        self.assertNotIn(self.token, response.headers['Location'])
        self.assertNotIn(self.token, response.get_data(as_text=True))

    @patch('frontend.requests.post')
    def test_payment_slack_notification_omits_token(self, mock_post):
        """test that the Slack alert for a failed payment excludes the token"""
        self._authenticate()
        mock_post.side_effect = [
            RequestException('ledgerwriter unreachable'),
            MagicMock(status_code=200),
        ]
        # send payment request while ledgerwriter is unreachable
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_REQUEST)
        # assert behavior on failure is unchanged
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        # assert the webhook was called with the endpoint and channel
        slack_call = mock_post.call_args
        self.assertEqual(slack_call.kwargs['url'], SLACK_WEBHOOK_URL)
        payload = slack_call.kwargs['json']
        self.assertEqual(payload['channel'], SLACK_CHANNEL)
        # assert the alert text does not carry the session token
        self.assertNotIn(self.token, payload['text'])


if __name__ == '__main__':
    unittest.main()
