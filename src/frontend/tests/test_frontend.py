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
Tests for the frontend service: /payment error paths and auth cookie handling.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch, mock_open

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# the service is a flat module directory, not an installed package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import create_app  # pylint: disable=wrong-import-position

EXAMPLE_ACCOUNT_ID = '1011226111'
EXAMPLE_RECIPIENT = '1055757655'
EXAMPLE_USER = 'testuser'
LOCAL_ROUTING = '883745000'
SCREENING_DECLINE = 'bad request: recipient screening declined (SCREEN-403)'


def _generate_keypair():
    """Generate an ephemeral RSA keypair for signing test tokens."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


class TestFrontend(unittest.TestCase):
    """Test cases for the frontend service"""

    @classmethod
    def setUpClass(cls):
        cls.private_key, cls.public_key = _generate_keypair()

    def setUp(self):
        """Setup Flask TestClient with mocked env, public key and metadata server"""
        # mock reading the public key file
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            # mock env vars
            with patch(
                'os.environ',
                {
                    'VERSION': '1',
                    'ENABLE_TRACING': 'false',
                    'PUB_KEY_PATH': '1',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
                    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
                    'USERSERVICE_API_ADDR': 'userservice:8080',
                    'BALANCES_API_ADDR': 'balancereader:8080',
                    'HISTORY_API_ADDR': 'transactionhistory:8080',
                    'CONTACTS_API_ADDR': 'contacts:8080',
                },
            ):
                # the metadata server is unreachable outside GCP
                with patch('frontend.requests.get') as mock_get:
                    mock_get.return_value.ok = False
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.token = self._make_token()

    def _make_token(self, expiry=3600):
        issued_at = int(time.time())
        return jwt.encode(
            {
                'user': EXAMPLE_USER,
                'acct': EXAMPLE_ACCOUNT_ID,
                'name': 'Test User',
                'iat': issued_at,
                'exp': issued_at + expiry,
            },
            self.private_key,
            algorithm='RS256',
        )

    def _authenticate(self):
        self.test_app.set_cookie('token', self.token)

    def _assert_no_token_leak(self, response):
        """The raw JWT must never be echoed back to the browser."""
        self.assertNotIn(self.token, response.get_data(as_text=True))
        self.assertNotIn(self.token, response.headers.get('Location', ''))

    def test_payment_ledgerwriter_400_surfaces_decline_without_leaking_token(self):
        """a 400 from ledgerwriter is surfaced to the user as a payment failure"""
        self._authenticate()
        ledger_response = MagicMock()
        ledger_response.status_code = 400
        ledger_response.text = SCREENING_DECLINE
        ledger_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            '400 Client Error'
        )
        with patch('frontend.requests.post') as mock_post:
            mock_post.return_value = ledger_response
            response = self.test_app.post(
                '/payment',
                data={
                    'account_num': EXAMPLE_RECIPIENT,
                    'amount': '10.00',
                    'uuid': 'test-uuid',
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        self.assertIn('SCREEN-403', response.headers['Location'])
        self._assert_no_token_leak(response)

    def test_payment_invalid_amount_redirects_with_failure_message(self):
        """a non-numeric amount fails before any call to ledgerwriter"""
        self._authenticate()
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post(
                '/payment',
                data={
                    'account_num': EXAMPLE_RECIPIENT,
                    'amount': 'not-a-number',
                    'uuid': 'test-uuid',
                },
            )
        mock_post.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        self._assert_no_token_leak(response)

    def test_payment_unauthenticated_401_no_transaction_submitted(self):
        """an unauthenticated payment is rejected without reaching ledgerwriter"""
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post(
                '/payment',
                data={
                    'account_num': EXAMPLE_RECIPIENT,
                    'amount': '10.00',
                    'uuid': 'test-uuid',
                },
            )
        mock_post.assert_not_called()
        self.assertEqual(response.status_code, 401)

    def test_login_sets_token_cookie_and_logout_clears_it(self):
        """login stores the JWT in a cookie and logout deletes it"""
        login_response = MagicMock()
        login_response.json.return_value = {'token': self.token}
        with patch('frontend.requests.get') as mock_get:
            mock_get.return_value = login_response
            response = self.test_app.post(
                '/login', data={'username': EXAMPLE_USER, 'password': 'password'}
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/home', response.headers['Location'])
        cookies = response.headers.getlist('Set-Cookie')
        self.assertTrue(any('token={}'.format(self.token) in c for c in cookies))
        self._assert_no_token_leak(response)

        logout_response = self.test_app.post('/logout')
        self.assertEqual(logout_response.status_code, 302)
        cleared = logout_response.headers.getlist('Set-Cookie')
        self.assertTrue(any(c.startswith('token=;') for c in cleared))
        self.assertTrue(any(c.startswith('consented=;') for c in cleared))

    def test_home_unauthenticated_redirects_to_login(self):
        """an invalid token cannot reach the authenticated home page"""
        self.test_app.set_cookie('token', 'not-a-valid-token')
        response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])


if __name__ == '__main__':
    unittest.main()
