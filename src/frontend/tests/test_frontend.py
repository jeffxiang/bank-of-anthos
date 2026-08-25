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
Tests for the frontend service: auth cookie handling and the /payment path.
"""

import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import create_app  # pylint: disable=wrong-import-position

LOCAL_ROUTING = '883745000'
SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/T000/B000/synthetic'
TRANSACTIONS_URI = 'http://ledgerwriter.example/transactions'
EXAMPLE_PAYMENT = {
    'account_num': '9099791699',
    'amount': '10.00',
    'uuid': '11111111-2222-3333-4444-555555555555',
}


def _generate_keypair():
    """Generates an ephemeral RSA keypair for signing test tokens."""
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
    """Test cases for the frontend /payment path and auth cookies"""

    @classmethod
    def setUpClass(cls):
        cls.private_key, cls.public_key = _generate_keypair()
        cls.other_private_key, _ = _generate_keypair()

    def setUp(self):
        """Setup Flask TestClient with mocked public key, env vars and backends"""
        # mock reading the userservice public key from disk
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            # mock env vars
            with patch(
                'os.environ',
                {
                    'VERSION': '1',
                    'PUB_KEY_PATH': '1',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
                    'TRANSACTIONS_API_ADDR': 'ledgerwriter.example',
                    'ENABLE_TRACING': 'false',
                },
            ):
                # mock the metadata server lookups done at startup
                with patch('frontend.requests.get'):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.flask_app.config['TRANSACTIONS_URI'] = TRANSACTIONS_URI
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.test_app = self.flask_app.test_client()

    def _token(self, private_key=None):
        """Signs a synthetic session token"""
        now = datetime.datetime.now(datetime.timezone.utc)
        return jwt.encode(
            {
                'user': 'testuser',
                'acct': '1011226111',
                'name': 'Test User',
                'iat': now,
                'exp': now + datetime.timedelta(hours=1),
            },
            private_key or self.private_key,
            algorithm='RS256',
        )

    def _mock_backends(self, transaction_response):
        """Patches requests.post, routing the ledgerwriter call to a mock response"""
        def _post(url=None, **_kwargs):
            if url == TRANSACTIONS_URI:
                return transaction_response
            return MagicMock(status_code=200)
        return patch('frontend.requests.post', side_effect=_post)

    def test_payment_401_when_token_cookie_missing(self):
        """test that an unauthenticated payment is rejected without calling the backend"""
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT)
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    def test_payment_401_when_token_cookie_signature_invalid(self):
        """test that a token signed by an unknown key is rejected"""
        forged_token = self._token(private_key=self.other_private_key)
        self.test_app.set_cookie('token', forged_token, domain='localhost')
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT)
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    def test_payment_ledgerwriter_400_redirects_with_error_and_no_token_leak(self):
        """test that a ledgerwriter 400 is surfaced without leaking the session token"""
        token = self._token()
        self.test_app.set_cookie('token', token, domain='localhost')
        error_response = MagicMock(text='invalid transaction: insufficient balance')
        error_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            '400 Client Error')
        with self._mock_backends(error_response) as mock_post:
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT)
        self.assertEqual(response.status_code, 302)
        self.assertIn('insufficient+balance', response.headers['Location'])
        self.assertNotIn(token, response.headers['Location'])
        self.assertNotIn(token, response.get_data(as_text=True))
        # the failure is reported to Slack, and the token is not part of the alert
        slack_calls = [call for call in mock_post.call_args_list
                       if call.kwargs.get('url') == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_calls), 1)
        self.assertNotIn(token, slack_calls[0].kwargs['json']['text'])

    def test_payment_invalid_amount_not_submitted_to_ledgerwriter(self):
        """test that a malformed amount fails before any transaction is submitted"""
        self.test_app.set_cookie('token', self._token(), domain='localhost')
        payment = EXAMPLE_PAYMENT.copy()
        payment['amount'] = '1o.oo'
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=payment)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'],
                         'http://localhost/home?msg=Payment+failed')
        transaction_calls = [call for call in mock_post.call_args_list
                             if call.kwargs.get('url') == TRANSACTIONS_URI]
        self.assertEqual(transaction_calls, [])


if __name__ == '__main__':
    unittest.main()
