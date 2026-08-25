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

import unittest
from unittest.mock import MagicMock, patch, mock_open

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from frontend import create_app

LOCAL_ROUTING = '883745000'
SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/T000/B000/XXX'
TRANSACTIONS_URI = 'http://ledgerwriter.example/transactions'
EXAMPLE_TOKEN_PAYLOAD = {
    'user': 'testuser',
    'acct': '1011226111',
    'name': 'Test User',
}
EXAMPLE_PAYMENT_FORM = {
    'account_num': '1033623433',
    'amount': '12.34',
    'uuid': '4b0a5d6e-1c4f-4f2a-9c2b-2a1f3c4d5e6f',
}


def _generate_keypair():
    """Generate an ephemeral RSA keypair as (private PEM, public PEM)."""
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
    Test cases for the frontend /payment auth and error paths
    """

    def setUp(self):
        """Setup Flask TestClient with an ephemeral signing keypair"""
        self.private_key, self.public_key = _generate_keypair()
        # a second keypair, used to forge tokens the frontend must reject
        self.foreign_private_key, _ = _generate_keypair()

        # mock reading the userservice public key off disk
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            # mock env vars
            with patch(
                'os.environ',
                {
                    'VERSION': '1',
                    'PUB_KEY_PATH': '1',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
                    'TRANSACTIONS_API_ADDR': 'ledgerwriter.example',
                    'SLACK_WEBHOOK_URL': SLACK_WEBHOOK_URL,
                    'ENABLE_TRACING': 'false',
                },
            ):
                # the metadata server is unreachable outside of GCP
                with patch('frontend.requests.get',
                           side_effect=requests.exceptions.RequestException()):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

    def _token(self, key):
        """Sign an example token payload with the given private key"""
        return jwt.encode(EXAMPLE_TOKEN_PAYLOAD, key, algorithm='RS256')

    def test_payment_401_no_token_cookie(self):
        """test that an unauthenticated payment is rejected with 401"""
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 401)

    def test_payment_401_token_signed_by_foreign_key(self):
        """test that a token with an unverifiable signature is rejected with 401"""
        self.test_app.set_cookie('token', self._token(self.foreign_private_key))
        response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 401)

    def test_payment_302_invalid_amount_notifies_slack(self):
        """test that a non-numeric amount fails the payment and alerts Slack"""
        self.test_app.set_cookie('token', self._token(self.private_key))
        form = dict(EXAMPLE_PAYMENT_FORM, amount='not-a-number')
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=form)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        # no transaction was submitted, only the Slack alert was posted
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.kwargs['url'], SLACK_WEBHOOK_URL)

    def test_payment_302_ledgerwriter_rejection_notifies_slack(self):
        """test that a ledgerwriter 4xx fails the payment and alerts Slack"""
        self.test_app.set_cookie('token', self._token(self.private_key))
        rejection = MagicMock()
        rejection.text = 'insufficient balance'
        rejection.raise_for_status.side_effect = requests.exceptions.HTTPError()

        def post(url, **_kwargs):
            return MagicMock() if url == SLACK_WEBHOOK_URL else rejection

        with patch('frontend.requests.post', side_effect=post) as mock_post:
            response = self.test_app.post('/payment', data=EXAMPLE_PAYMENT_FORM)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed:+insufficient+balance',
                      response.headers['Location'])
        slack_payloads = [call.kwargs['json']['text'] for call in mock_post.call_args_list
                          if call.kwargs['url'] == SLACK_WEBHOOK_URL]
        self.assertEqual(slack_payloads,
                         ['[frontend] /payment failed: insufficient balance'])


if __name__ == '__main__':
    unittest.main()
