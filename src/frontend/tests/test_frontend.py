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
Tests for the frontend /payment error paths and auth cookie handling.
"""

import os
import sys
import unittest
import uuid
from unittest.mock import MagicMock, patch

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from frontend import create_app  # noqa: E402

LOCAL_ROUTING = '883745000'
ACCOUNT_ID = '1011226111'
RECIPIENT = '1055757655'
SCREENING_DECLINE = 'bad request: recipient screening declined'


class TestFrontendPayment(unittest.TestCase):
    """Test cases for the /payment endpoint."""

    def setUp(self):
        """Create a Flask test client backed by a throwaway RSA key pair."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()).decode()
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()

        env = {
            'ENABLE_TRACING': 'false',
            'PUB_KEY_PATH': '/dev/null',
            'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
            'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
            'USERSERVICE_API_ADDR': 'userservice:8080',
            'BALANCES_API_ADDR': 'balancereader:8080',
            'HISTORY_API_ADDR': 'transactionhistory:8080',
            'CONTACTS_API_ADDR': 'contacts:8080',
        }
        with patch.dict(os.environ, env, clear=True), \
                patch('frontend.open', unittest.mock.mock_open(read_data=public_pem)), \
                patch('frontend.requests.get',
                      side_effect=requests.exceptions.RequestException()):
            self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

        self.token = jwt.encode({'user': 'testuser',
                                 'acct': ACCOUNT_ID,
                                 'name': 'Test User'},
                                self.private_pem,
                                algorithm='RS256')

    def _post_payment(self, amount='10.00', authenticated=True):
        """POST a payment to RECIPIENT, optionally with the auth cookie set."""
        if authenticated:
            self.test_app.set_cookie('token', self.token)
        return self.test_app.post('/payment',
                                  data={'account_num': RECIPIENT,
                                        'amount': amount,
                                        'uuid': str(uuid.uuid4())})

    def _assert_no_token_leak(self, response):
        """The session token must never reach the user agent in a response."""
        body = response.get_data(as_text=True)
        self.assertNotIn(self.token, body)
        for _, value in response.headers.items():
            self.assertNotIn(self.token, value)

    def _ledgerwriter_error(self, status_code, text):
        """Mock a ledgerwriter response that fails with the given status."""
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            '{} Client Error'.format(status_code), response=response)
        return response

    def test_payment_without_token_is_unauthorized(self):
        """An unauthenticated payment is rejected before hitting ledgerwriter."""
        with patch('frontend.requests.post') as mock_post:
            response = self._post_payment(authenticated=False)
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()
        self.assertNotIn(self.token, response.get_data(as_text=True))

    def test_payment_declined_by_ledgerwriter_does_not_leak_token(self):
        """A 400 decline surfaces the reason but never the session token."""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = 'https://hooks.slack.test/abc'
        slack_calls = []

        def post_side_effect(*_args, **kwargs):
            if kwargs.get('url', '').startswith('https://hooks.slack.test'):
                slack_calls.append(kwargs)
                return MagicMock(status_code=200)
            return self._ledgerwriter_error(400, SCREENING_DECLINE)

        with patch('frontend.requests.post', side_effect=post_side_effect):
            response = self._post_payment()

        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        self.assertIn('screening+declined', response.headers['Location'])
        self._assert_no_token_leak(response)
        self.assertEqual(len(slack_calls), 1)
        self.assertNotIn(self.token, str(slack_calls[0]['json']))

    def test_payment_with_invalid_amount_does_not_leak_token(self):
        """A non-numeric amount is rejected before any transaction is sent."""
        with patch('frontend.requests.post') as mock_post:
            response = self._post_payment(amount='not-a-number')
        mock_post.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        self._assert_no_token_leak(response)

    def test_payment_when_ledgerwriter_unreachable_does_not_leak_token(self):
        """A transport failure redirects with a generic message only."""
        with patch('frontend.requests.post',
                   side_effect=requests.exceptions.RequestException(
                       'connection refused to ledgerwriter')):
            response = self._post_payment()
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        self.assertNotIn('connection+refused', response.headers['Location'])
        self._assert_no_token_leak(response)


if __name__ == '__main__':
    unittest.main()
