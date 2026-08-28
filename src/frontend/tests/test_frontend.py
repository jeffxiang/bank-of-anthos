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
Tests for the frontend /payment error paths.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

import jwt
import markupsafe
import markupsafe._native
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# The markupsafe C speedup segfaults into SystemError on the CPython 3.14 alpha
# pinned for this service, which breaks every rendered/redirected response.
# Fall back to the pure-Python implementation before Flask is imported.
markupsafe._escape_inner = markupsafe._native._escape_inner  # pylint: disable=protected-access

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from frontend import create_app  # noqa: E402

EXAMPLE_ACCOUNT_ID = '1011226111'
EXAMPLE_RECIPIENT_ID = '9099791699'
EXAMPLE_USER = 'jdoe'
EXAMPLE_DISPLAY_NAME = 'J Doe'
LOCAL_ROUTING = '883745000'
EXAMPLE_UUID = '00000000-0000-0000-0000-000000000001'
LEDGERWRITER_400_BODY = 'insufficient balance'
INVALID_AMOUNTS = ['not-a-number', '', '1️⃣0']

ENV = {
    'VERSION': '1',
    'ENABLE_TRACING': 'false',
    'PUB_KEY_PATH': '1',
    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
    'USERSERVICE_API_ADDR': 'userservice:8080',
    'BALANCES_API_ADDR': 'balancereader:8080',
    'HISTORY_API_ADDR': 'transactionhistory:8080',
    'CONTACTS_API_ADDR': 'contacts:8080',
    'SCHEME': 'http',
}


def _generate_rsa_keypair():
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


class TestFrontendPayment(unittest.TestCase):
    """Test cases for the /payment endpoint's error handling."""

    def setUp(self):
        """Set up a Flask test client with an ephemeral signing keypair."""
        self.private_key, self.public_key = _generate_rsa_keypair()
        self.token = jwt.encode(
            {
                'user': EXAMPLE_USER,
                'acct': EXAMPLE_ACCOUNT_ID,
                'name': EXAMPLE_DISPLAY_NAME,
                'iat': 0,
                'exp': 9999999999,
            },
            self.private_key,
            algorithm='RS256',
        )
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            with patch('os.environ', ENV):
                with patch('frontend.requests.get',
                           side_effect=requests.exceptions.RequestException()):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

    def _payment_form(self, amount='10.00'):
        return {
            'account_num': EXAMPLE_RECIPIENT_ID,
            'amount': amount,
            'uuid': EXAMPLE_UUID,
        }

    def test_payment_401_when_auth_cookie_missing(self):
        """/payment must reject an unauthenticated request with 401."""
        response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 401)

    def test_payment_302_when_ledgerwriter_returns_400(self):
        """A 400 from ledgerwriter is surfaced to the user as a payment failure."""
        error_response = MagicMock(status_code=400, text=LEDGERWRITER_400_BODY)
        error_response.raise_for_status.side_effect = \
            requests.exceptions.HTTPError()
        self.test_app.set_cookie('token', self.token)
        with patch('frontend.requests.post',
                   return_value=error_response) as mock_post:
            response = self.test_app.post('/payment', data=self._payment_form())
        mock_post.assert_called_once()
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        self.assertIn(LEDGERWRITER_400_BODY.replace(' ', '+'),
                      response.headers['Location'])

    def test_payment_302_when_amount_is_not_a_valid_number(self):
        """Unparseable amounts fail before any call to ledgerwriter."""
        self.test_app.set_cookie('token', self.token)
        for amount in INVALID_AMOUNTS:
            with self.subTest(amount=amount):
                with patch('frontend.requests.post') as mock_post:
                    response = self.test_app.post(
                        '/payment', data=self._payment_form(amount=amount))
                mock_post.assert_not_called()
                self.assertEqual(response.status_code, 302)
                self.assertIn('msg=Payment+failed',
                              response.headers['Location'])

    def test_payment_error_responses_do_not_leak_the_auth_token(self):
        """Failure responses must not echo the JWT into headers or body."""
        error_response = MagicMock(status_code=400, text=LEDGERWRITER_400_BODY)
        error_response.raise_for_status.side_effect = \
            requests.exceptions.HTTPError()
        self.test_app.set_cookie('token', self.token)
        with patch('frontend.requests.post', return_value=error_response):
            responses = [
                self.test_app.post('/payment', data=self._payment_form()),
                self.test_app.post('/payment',
                                   data=self._payment_form(amount='abc')),
            ]
        for response in responses:
            with self.subTest(location=response.headers['Location']):
                rendered = response.get_data(as_text=True) + \
                    response.headers['Location']
                self.assertNotIn(self.token, rendered)
                self.assertNotIn(self.token.split('.')[1], rendered)


if __name__ == '__main__':
    unittest.main()
