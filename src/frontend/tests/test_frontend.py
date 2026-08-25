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
Tests for frontend auth cookies, /payment and error handling
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

# pylint: disable=wrong-import-position
from frontend import create_app

EXAMPLE_ACCOUNT_ID = '1011226111'
EXAMPLE_USERNAME = 'jdoe'
EXAMPLE_DISPLAY_NAME = 'John Doe'
LOCAL_ROUTING_NUM = '883745000'
LEDGER_ERROR_TEXT = 'transaction submission failed: insufficient balance'


def generate_rsa_key():
    """Generate an ephemeral priv,pub key pair for test"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key


class TestFrontend(unittest.TestCase):
    """
    Test cases for the frontend service
    """

    def setUp(self):
        """Setup Flask TestClient with an ephemeral signing key"""
        self.private_key, self.public_key = generate_rsa_key()
        # mock reading the userservice public key and the metadata server
        with patch('frontend.open', mock_open(read_data=self.public_key.decode())):
            with patch('frontend.requests.get',
                       side_effect=requests.exceptions.RequestException('no metadata')):
                # mock env vars
                with patch.dict('os.environ', {
                    'VERSION': '1',
                    'PUB_KEY_PATH': '1',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING_NUM,
                    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
                    'USERSERVICE_API_ADDR': 'userservice:8080',
                    'BALANCES_API_ADDR': 'balancereader:8080',
                    'HISTORY_API_ADDR': 'transactionhistory:8080',
                    'CONTACTS_API_ADDR': 'contacts:8080',
                    'ENABLE_TRACING': 'false',
                }, clear=True):
                    self.flask_app = create_app()
                    self.flask_app.config['TESTING'] = True
                    self.test_app = self.flask_app.test_client()

    def _make_token(self, expiry_seconds=3600, key=None):
        """Sign a synthetic session token with the ephemeral private key"""
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            'user': EXAMPLE_USERNAME,
            'acct': EXAMPLE_ACCOUNT_ID,
            'name': EXAMPLE_DISPLAY_NAME,
            'iat': now,
            'exp': now + datetime.timedelta(seconds=expiry_seconds),
        }
        return jwt.encode(payload,
                          key if key is not None else self.private_key,
                          algorithm='RS256')

    def test_payment_ledgerwriter_400_error_does_not_echo_token(self):
        """test a rejected payment renders the backend error without the token"""
        token = self._make_token()
        self.test_app.set_cookie('token', token)
        # mock ledgerwriter rejecting the transaction with a 400
        mocked_response = MagicMock()
        mocked_response.status_code = 400
        mocked_response.text = LEDGER_ERROR_TEXT
        mocked_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
        with patch('frontend.requests.post', return_value=mocked_response) as mock_post:
            response = self.test_app.post('/payment', data={
                'account_num': '9099791699',
                'amount': '10.00',
                'uuid': 'a1b2c3d4',
            })
        # assert the user is redirected back home with the failure message
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        # assert the session token is not leaked into the rendered error
        self.assertNotIn(token, response.headers['Location'])
        self.assertNotIn(token, response.get_data(as_text=True))
        # assert the token was only sent to ledgerwriter, in the auth header
        self.assertEqual(mock_post.call_args.kwargs['headers']['Authorization'],
                         'Bearer ' + token)

    def test_payment_invalid_amount_redirects_with_error_message(self):
        """test a non-numeric payment amount is rejected before any backend call"""
        self.test_app.set_cookie('token', self._make_token())
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data={
                'account_num': '9099791699',
                'amount': 'not-a-number',
                'uuid': 'a1b2c3d4',
            })
        self.assertEqual(response.status_code, 302)
        # the per-input message is built but unused, so the generic one is rendered
        self.assertEqual(response.headers['Location'],
                         'http://localhost/home?msg=Payment+failed')
        # assert no transaction was submitted
        mock_post.assert_not_called()

    def test_payment_tampered_token_401_status_code(self):
        """test a token signed by an unknown key cannot submit a payment"""
        foreign_private_key, _ = generate_rsa_key()
        self.test_app.set_cookie('token', self._make_token(key=foreign_private_key))
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data={
                'account_num': '9099791699',
                'amount': '10.00',
                'uuid': 'a1b2c3d4',
            })
        # assert unauthenticated requests are rejected
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    def test_home_expired_token_redirects_to_login(self):
        """test an expired token fails verification and never reaches the backends"""
        self.test_app.set_cookie('token', self._make_token(expiry_seconds=-60))
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.get('/home')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])
        mock_post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
