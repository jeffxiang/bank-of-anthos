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
Tests for the frontend /payment error paths and auth token handling.
"""

import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import create_app  # pylint: disable=wrong-import-position

LOCAL_ROUTING = '883745000'
EXAMPLE_ACCOUNT = '1011226111'
RECIPIENT_ACCOUNT = '1033623433'


def _generate_keypair():
    """Generate an ephemeral RSA keypair for signing test tokens."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()).decode()
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private_key, public_key


class TestFrontendPayment(unittest.TestCase):
    """Test cases for /payment error handling and token confidentiality"""

    def setUp(self):
        self.private_key, self.public_key = _generate_keypair()
        env = {
            'VERSION': '1',
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
                patch('frontend.open',
                      unittest.mock.mock_open(read_data=self.public_key)), \
                patch('frontend.requests.get',
                      side_effect=requests.exceptions.RequestException('no metadata')):
            self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.token = jwt.encode(
            {'user': 'testuser', 'acct': EXAMPLE_ACCOUNT, 'name': 'Test User'},
            self.private_key,
            algorithm='RS256')

    def _payment_form(self):
        return {
            'account_num': RECIPIENT_ACCOUNT,
            'amount': '10.00',
            'uuid': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        }

    def test_payment_without_token_is_unauthorized(self):
        """An unauthenticated payment is rejected with 401"""
        response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 401)

    def test_payment_with_token_signed_by_other_key_is_unauthorized(self):
        """A well-formed token signed by an unknown key is rejected with 401"""
        other_private_key, _ = _generate_keypair()
        forged = jwt.encode({'user': 'testuser', 'acct': EXAMPLE_ACCOUNT},
                            other_private_key,
                            algorithm='RS256')
        self.test_app.set_cookie('token', forged)
        response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(forged, response.get_data(as_text=True))

    def test_payment_with_invalid_amount_redirects_without_calling_ledger(self):
        """A non-numeric amount fails before any transaction is submitted"""
        self.test_app.set_cookie('token', self.token)
        form = self._payment_form()
        form['amount'] = 'not-a-number'
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=form)
        mock_post.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])

    def test_payment_backend_failure_does_not_leak_token(self):
        """A ledgerwriter failure redirects without leaking the token anywhere"""
        self.test_app.set_cookie('token', self.token)
        failed = MagicMock()
        failed.text = 'ledger rejected transaction'
        failed.raise_for_status.side_effect = requests.exceptions.HTTPError('500')
        with patch('frontend.requests.post', return_value=failed), \
                self.assertLogs('frontend', level=logging.DEBUG) as logs:
            response = self.test_app.post('/payment', data=self._payment_form())

        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        body = response.get_data(as_text=True)
        self.assertNotIn(self.token, body)
        self.assertNotIn(self.token, response.headers['Location'])
        self.assertNotIn('Set-Cookie', response.headers)
        for record in logs.output:
            self.assertNotIn(self.token, record)


if __name__ == '__main__':
    unittest.main()
