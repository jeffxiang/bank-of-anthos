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
Tests for the frontend /payment error paths and auth token handling
"""

import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from frontend import create_app  # noqa: E402


def _generate_rsa_keypair():
    """Generate an ephemeral RSA keypair for signing test tokens"""
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


PRIVATE_KEY, PUBLIC_KEY = _generate_rsa_keypair()

ENVIRONMENT = {
    'VERSION': '1',
    'ENABLE_TRACING': 'false',
    'PUB_KEY_PATH': '/dev/null',
    'LOCAL_ROUTING_NUM': '883745000',
    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
    'USERSERVICE_API_ADDR': 'userservice:8080',
    'BALANCES_API_ADDR': 'balancereader:8080',
    'HISTORY_API_ADDR': 'transactionhistory:8080',
    'CONTACTS_API_ADDR': 'contacts:8080',
    'SLACK_WEBHOOK_URL': 'http://slack.example/webhook',
    'SCHEME': 'http',
}


class TestFrontendPayment(unittest.TestCase):
    """Test cases for /payment failures and token handling"""

    def setUp(self):
        """Setup Flask TestClient with mocked public key and metadata server"""
        with patch('frontend.open', mock_open(read_data=PUBLIC_KEY)):
            with patch('os.environ', dict(ENVIRONMENT)):
                # the metadata server is unreachable outside of GCP
                with patch('frontend.requests.get',
                           side_effect=requests.exceptions.RequestException()):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.token = self._make_token()

    @staticmethod
    def _make_token():
        """Sign a valid token for a synthetic test user"""
        now = datetime.datetime.now(datetime.timezone.utc)
        claims = {
            'user': 'testuser',
            'acct': '1011226111',
            'name': 'Test User',
            'iat': int(now.timestamp()),
            'exp': int((now + datetime.timedelta(hours=1)).timestamp()),
        }
        return jwt.encode(claims, PRIVATE_KEY, algorithm='RS256')

    def _payment_form(self, amount='10.00'):
        return {
            'account_num': '1033623433',
            'amount': amount,
            'uuid': 'ac0d0d31-0f30-4d8f-9d4b-1e2c8c5b8f7a',
        }

    def test_payment_without_token_returns_401_and_submits_nothing(self):
        """unauthenticated payments are rejected before reaching ledgerwriter"""
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    def test_payment_with_invalid_token_returns_401(self):
        """a token signed by another key is not accepted and is not echoed back"""
        other_private_key, _ = _generate_rsa_keypair()
        forged_token = jwt.encode({'user': 'attacker', 'acct': '1011226111'},
                                  other_private_key,
                                  algorithm='RS256')
        self.test_app.set_cookie('token', forged_token, domain='localhost')
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()
        self.assertNotIn(forged_token.encode(), response.data)

    def test_payment_with_invalid_amount_redirects_without_submitting(self):
        """a non-numeric amount fails validation and alerts, without a transaction"""
        self.test_app.set_cookie('token', self.token, domain='localhost')
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment',
                                          data=self._payment_form(amount='abc'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        posted_urls = [call.kwargs['url'] for call in mock_post.call_args_list]
        self.assertEqual(posted_urls, [ENVIRONMENT['SLACK_WEBHOOK_URL']])

    def test_payment_failure_does_not_leak_token_in_response_or_logs(self):
        """a rejected transaction surfaces the error without exposing the token"""
        error_response = MagicMock()
        error_response.text = 'insufficient balance'
        error_response.raise_for_status.side_effect = \
            requests.exceptions.HTTPError('400 Client Error')
        self.test_app.set_cookie('token', self.token, domain='localhost')

        with patch('frontend.requests.post', return_value=error_response) as mock_post:
            with self.assertLogs(self.flask_app.logger, level='DEBUG') as logs:
                response = self.test_app.post('/payment', data=self._payment_form())

        self.assertEqual(response.status_code, 302)
        self.assertIn('insufficient+balance', response.headers['Location'])
        self.assertNotIn(self.token, response.headers['Location'])
        self.assertNotIn(self.token.encode(), response.data)
        self.assertNotIn(self.token, '\n'.join(logs.output))

        slack_calls = [call for call in mock_post.call_args_list
                       if call.kwargs['url'] == ENVIRONMENT['SLACK_WEBHOOK_URL']]
        self.assertEqual(len(slack_calls), 1)
        self.assertNotIn(self.token, slack_calls[0].kwargs['json']['text'])


if __name__ == '__main__':
    unittest.main()
