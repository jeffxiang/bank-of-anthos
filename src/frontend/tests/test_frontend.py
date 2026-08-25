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
from unittest.mock import MagicMock, patch, mock_open

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from frontend import create_app

LOCAL_ROUTING = '883745000'
TRANSACTIONS_URI = 'http://ledgerwriter:8080/transactions'
SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/T000/B000/XXXX'
SLACK_CHANNEL = '#alerts'
EXAMPLE_ACCOUNT = '1011226111'
EXAMPLE_RECIPIENT = '1033623433'


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
        cls.private_key, cls.public_key = _generate_keypair()
        # a second, unrelated keypair to simulate a forged token
        cls.other_private_key, _ = _generate_keypair()

    def setUp(self):
        """Setup Flask TestClient with a mocked public key and env vars"""
        # mock opening the public key file
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            # mock env vars
            with patch(
                'os.environ',
                {
                    'VERSION': '1',
                    'PUB_KEY_PATH': '1',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
                    'ENABLE_TRACING': 'false',
                },
            ):
                # the metadata server is unreachable outside of GCP
                with patch('frontend.requests.get',
                           side_effect=requests.exceptions.RequestException()):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.flask_app.config['TRANSACTIONS_URI'] = TRANSACTIONS_URI
        self.test_app = self.flask_app.test_client()

    def _token(self, private_key=None, account_id=EXAMPLE_ACCOUNT):
        """Mint a token for the given account, signed by the given key"""
        return jwt.encode(
            {'acct': account_id, 'user': 'testuser', 'name': 'Test User'},
            private_key or self.private_key,
            algorithm='RS256',
        )

    def _payment_form(self, amount='10.00'):
        return {
            'account_num': EXAMPLE_RECIPIENT,
            'amount': amount,
            'uuid': '00000000-0000-0000-0000-000000000001',
        }

    def test_payment_401_status_code_no_token_cookie(self):
        """test submitting a payment without a token cookie"""
        response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 401)

    def test_payment_401_status_code_token_signed_by_unknown_key(self):
        """test submitting a payment with a token signed by an unknown key"""
        self.test_app.set_cookie('token', self._token(self.other_private_key))
        response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 401)

    def test_payment_302_status_code_malformed_amounts(self):
        """test submitting a payment with amounts that are not valid numbers"""
        self.test_app.set_cookie('token', self._token())
        for invalid_amount in ['', ' ', 'abc', '1.2.3', '10٫00', '💸']:
            with patch('frontend.requests.post') as mock_post:
                response = self.test_app.post(
                    '/payment', data=self._payment_form(invalid_amount))
                # assert the payment failed before reaching ledgerwriter
                self.assertEqual(response.status_code, 302,
                                 'amount {} returned incorrect status code'.format(
                                     invalid_amount))
                self.assertIn('msg=Payment+failed', response.headers['Location'])
                mock_post.assert_not_called()

    def test_payment_302_status_code_ledger_rejection_alerts_slack(self):
        """test a payment rejected by ledgerwriter alerts Slack and reports failure"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.flask_app.config['SLACK_CHANNEL'] = SLACK_CHANNEL
        self.test_app.set_cookie('token', self._token())

        ledger_response = MagicMock()
        ledger_response.text = 'transaction rejected'
        ledger_response.raise_for_status.side_effect = \
            requests.exceptions.HTTPError('400 Client Error')

        def fake_post(url, **_kwargs):
            if url == TRANSACTIONS_URI:
                return ledger_response
            return MagicMock()

        with patch('frontend.requests.post', side_effect=fake_post) as mock_post:
            response = self.test_app.post('/payment', data=self._payment_form())
        # assert the user is redirected home with the rejection reason
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        # assert the alert was posted to the configured webhook and channel
        slack_calls = [call for call in mock_post.call_args_list
                       if call.kwargs.get('url') == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_calls), 1)
        payload = slack_calls[0].kwargs['json']
        self.assertEqual(payload['channel'], SLACK_CHANNEL)
        self.assertIn('[frontend] /payment failed', payload['text'])
