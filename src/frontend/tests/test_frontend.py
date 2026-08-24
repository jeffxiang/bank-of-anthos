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

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from requests.exceptions import HTTPError, RequestException
import jwt

# frontend.py is a flat module, its imports assume the service directory is
# importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import create_app  # pylint: disable=wrong-import-position

EXAMPLE_ACCOUNT_ID = '1234567890'
EXAMPLE_USERNAME = 'testuser'
LOCAL_ROUTING_NUM = '883745000'
SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/T000/B000/XXXX'


def _generate_keypair():
    """Generate an ephemeral RSA keypair as PEM strings"""
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
    """
    Test cases for the frontend service
    """

    @classmethod
    def setUpClass(cls):
        """Generate the keypair trusted by the app and an untrusted one"""
        cls.private_key, cls.public_key = _generate_keypair()
        cls.other_private_key, _ = _generate_keypair()

    def setUp(self):
        """Setup Flask TestClient with mocked key file and env vars"""
        env = {
            'VERSION': '1',
            'PUB_KEY_PATH': '1',
            'LOCAL_ROUTING_NUM': LOCAL_ROUTING_NUM,
            'ENABLE_TRACING': 'false',
        }
        # mock reading the userservice public key from disk
        with patch('frontend.open',
                   unittest.mock.mock_open(read_data=self.public_key)):
            with patch('os.environ', env):
                # the metadata server is unreachable outside of GCP
                with patch('frontend.requests.get',
                           side_effect=RequestException('no metadata server')):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

    def _token(self, private_key=None):
        """Sign a token for the example account"""
        return jwt.encode(
            {
                'user': EXAMPLE_USERNAME,
                'acct': EXAMPLE_ACCOUNT_ID,
                'name': 'Test User',
                'iat': 1600000000,
                'exp': 4700000000,
            },
            private_key or self.private_key,
            algorithm='RS256',
        )

    def _payment_form(self, amount='10.00'):
        return {
            'account_num': '9876543210',
            'amount': amount,
            'uuid': 'e3f4e6a4-8f3a-4a1a-9a1a-000000000001',
        }

    def test_payment_without_token_401_status_code(self):
        """test submitting a payment with no auth cookie"""
        response = self.test_app.post('/payment', data=self._payment_form())
        # assert 401 response code
        self.assertEqual(response.status_code, 401)

    def test_payment_untrusted_token_401_status_code(self):
        """test submitting a payment with a token signed by another key"""
        self.test_app.set_cookie('token', self._token(self.other_private_key))
        response = self.test_app.post('/payment', data=self._payment_form())
        # assert the signature is verified, not just decoded
        self.assertEqual(response.status_code, 401)

    @patch('frontend.requests.post')
    def test_payment_invalid_amount_redirects_with_error(self, mock_post):
        """test submitting a payment with a non-numeric amount"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.test_app.set_cookie('token', self._token())
        response = self.test_app.post('/payment',
                                      data=self._payment_form(amount='abc'))
        # assert the user is redirected back home with a failure message
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        # assert the only outbound call was the Slack alert, no transaction
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_post.call_args.kwargs['url'], SLACK_WEBHOOK_URL)
        self.assertIn('[frontend] /payment failed',
                      mock_post.call_args.kwargs['json']['text'])

    @patch('frontend.requests.post')
    def test_payment_ledgerwriter_error_redirects_and_alerts(self, mock_post):
        """test a rejected transaction is surfaced to the user and to Slack"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        ledger_response = MagicMock()
        ledger_response.text = 'transaction failed: insufficient balance'
        ledger_response.raise_for_status.side_effect = HTTPError('400 error')
        mock_post.return_value = ledger_response
        self.test_app.set_cookie('token', self._token())
        response = self.test_app.post('/payment', data=self._payment_form())
        # assert the user is redirected back home with the ledger error
        self.assertEqual(response.status_code, 302)
        self.assertIn('insufficient+balance', response.headers['Location'])
        # assert the failure was reported to Slack
        slack_payload = mock_post.call_args.kwargs['json']
        self.assertIn('[frontend] /payment failed', slack_payload['text'])


if __name__ == '__main__':
    unittest.main()
