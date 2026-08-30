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

import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import create_app  # pylint: disable=wrong-import-position

LOCAL_ROUTING = '883745000'
SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/T000/B000/XXXX'
TRANSACTIONS_URI = 'http://ledgerwriter:8080/transactions'


def _generate_keypair():
    """Generate an ephemeral RSA keypair for signing test tokens."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


class TestFrontend(unittest.TestCase):
    """
    Test cases for the frontend service
    """

    def setUp(self):
        """Setup Flask TestClient with a mocked public key and backend URIs"""
        self.private_key, self.public_key = _generate_keypair()
        env = {
            'VERSION': '1',
            'PUB_KEY_PATH': '1',
            'ENABLE_TRACING': 'false',
            'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
            'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
            'USERSERVICE_API_ADDR': 'userservice:8080',
            'BALANCES_API_ADDR': 'balancereader:8080',
            'HISTORY_API_ADDR': 'transactionhistory:8080',
            'CONTACTS_API_ADDR': 'contacts:8080',
            'SLACK_WEBHOOK_URL': SLACK_WEBHOOK_URL,
        }
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            with patch('os.environ', env):
                # the metadata server is unreachable outside of GCP
                with patch('frontend.requests.get',
                           side_effect=requests.exceptions.RequestException()):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

    def _valid_token(self):
        """Sign a token the app's public key accepts."""
        now = datetime.datetime.now(datetime.timezone.utc)
        return jwt.encode(
            {
                'user': 'testuser',
                'acct': '1011226111',
                'name': 'Test User',
                'iat': now,
                'exp': now + datetime.timedelta(hours=1),
            },
            self.private_key,
            algorithm='RS256',
        )

    def test_payment_without_token_returns_401_and_submits_nothing(self):
        """unauthenticated payments are rejected before reaching ledgerwriter"""
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment',
                                          data={'account_num': '9099791699',
                                                'amount': '10.00',
                                                'uuid': 'abc-123'})
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    def test_payment_with_invalid_amount_alerts_slack_and_submits_nothing(self):
        """a non-numeric amount fails validation, alerts Slack, sends no transaction"""
        token = self._valid_token()
        self.test_app.set_cookie('token', token)
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment',
                                          data={'account_num': '9099791699',
                                                'amount': 'not-a-number',
                                                'uuid': 'abc-123'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        slack_calls = [call for call in mock_post.call_args_list
                       if call.kwargs['url'] == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_calls), 1)
        self.assertNotIn(TRANSACTIONS_URI,
                         [call.kwargs['url'] for call in mock_post.call_args_list])

    def test_payment_ledgerwriter_error_alerts_slack_without_leaking_token(self):
        """a ledgerwriter rejection surfaces to the user and leaks no token to Slack"""
        token = self._valid_token()
        self.test_app.set_cookie('token', token)
        ledger_response = MagicMock()
        ledger_response.text = 'account not found'
        ledger_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        def post(url, **_kwargs):
            if url == SLACK_WEBHOOK_URL:
                return MagicMock()
            return ledger_response

        with patch('frontend.requests.post', side_effect=post) as mock_post:
            response = self.test_app.post('/payment',
                                          data={'account_num': '9099791699',
                                                'amount': '10.00',
                                                'uuid': 'abc-123'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('account+not+found', response.headers['Location'])
        slack_calls = [call for call in mock_post.call_args_list
                       if call.kwargs['url'] == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_calls), 1)
        self.assertNotIn(token, slack_calls[0].kwargs['json']['text'])

    def test_logout_clears_auth_cookies_and_does_not_echo_token(self):
        """logout expires the token and consent cookies without echoing the token"""
        token = self._valid_token()
        self.test_app.set_cookie('token', token)
        self.test_app.set_cookie('consented', 'true')
        response = self.test_app.post('/logout')
        set_cookies = response.headers.getlist('Set-Cookie')
        cleared = {header.split('=')[0]: header for header in set_cookies}
        self.assertIn('token', cleared)
        self.assertIn('consented', cleared)
        for header in cleared.values():
            self.assertIn('Expires=Thu, 01 Jan 1970', header)
        self.assertNotIn(token, response.get_data(as_text=True))
        self.assertNotIn(token, str(set_cookies))


if __name__ == '__main__':
    unittest.main()
