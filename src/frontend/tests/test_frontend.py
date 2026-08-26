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
Tests for the frontend /payment error paths and auth-cookie handling.
"""

import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from requests.exceptions import HTTPError, RequestException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import frontend  # noqa: E402  pylint: disable=wrong-import-position

EXAMPLE_ACCOUNT_ID = '1011226111'
EXAMPLE_USERNAME = 'testuser'
LOCAL_ROUTING_NUM = '883745000'
SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/TEST/FAKE'
SLACK_CHANNEL = '#bofa-alerts'
LEDGERWRITER_URI = 'http://ledgerwriter:8080/transactions'
LEDGERWRITER_400_BODY = 'transaction submission failed: recipient is screened'
EXAMPLE_PAYMENT_FORM = {
    'account_num': '9099791699',
    'amount': '10.00',
    'uuid': '3b3a7b64-1b3a-4f4e-9c2a-000000000000',
}
ENV = {
    'ENABLE_TRACING': 'false',
    'PUB_KEY_PATH': 'publickey',
    'LOCAL_ROUTING_NUM': LOCAL_ROUTING_NUM,
    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
    'USERSERVICE_API_ADDR': 'userservice:8080',
    'BALANCES_API_ADDR': 'balancereader:8080',
    'HISTORY_API_ADDR': 'transactionhistory:8080',
    'CONTACTS_API_ADDR': 'contacts:8080',
}


def generate_rsa_keypair():
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


class TestFrontendPayment(unittest.TestCase):
    """Tests for /payment failure branches and session-token handling"""

    def setUp(self):
        """Create the Flask app with mocked keys, env vars and metadata server"""
        self.private_key, self.public_key = generate_rsa_keypair()
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            with patch.dict(os.environ, ENV):
                # the metadata server is unreachable outside GCP
                with patch('frontend.requests.get',
                           side_effect=RequestException('no metadata server')):
                    self.flask_app = frontend.create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.token = self._make_token()
        self.test_app.set_cookie('token', self.token)

    def _make_token(self):
        """Sign a valid session token with the ephemeral private key"""
        now = datetime.datetime.now(datetime.timezone.utc)
        return jwt.encode(
            {
                'user': EXAMPLE_USERNAME,
                'acct': EXAMPLE_ACCOUNT_ID,
                'name': 'Test User',
                'iat': now,
                'exp': now + datetime.timedelta(hours=1),
            },
            self.private_key,
            algorithm='RS256',
        )

    def _mock_ledgerwriter_400(self, body=LEDGERWRITER_400_BODY):
        """Return a requests.post side effect where ledgerwriter answers 400"""
        def side_effect(*_args, **kwargs):
            if kwargs.get('url') == LEDGERWRITER_URI:
                resp = MagicMock(status_code=400, text=body)
                resp.raise_for_status.side_effect = HTTPError('400 Client Error')
                return resp
            return MagicMock(status_code=200, text='ok')
        return side_effect

    def _assert_token_absent(self, response):
        """Assert the session token appears nowhere in the response"""
        self.assertNotIn(self.token, response.headers.get('Location', ''))
        self.assertNotIn(self.token, str(response.headers))
        self.assertNotIn(self.token.encode(), response.data)

    def test_payment_ledgerwriter_400_302_status_code_no_token_in_redirect(self):
        """test a 400 from ledgerwriter redirects without echoing the token"""
        with patch('frontend.requests.post',
                   side_effect=self._mock_ledgerwriter_400()):
            response = self.test_app.post('/payment',
                                          data=EXAMPLE_PAYMENT_FORM.copy())
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        self._assert_token_absent(response)

    def test_payment_invalid_amount_302_status_code_no_token_in_flash_message(self):
        """test an unparseable amount redirects with no token in the message"""
        payment_form = EXAMPLE_PAYMENT_FORM.copy()
        payment_form['amount'] = 'not-a-number'
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment', data=payment_form)
        mock_post.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        self._assert_token_absent(response)

    def test_payment_invalid_token_401_status_code_no_token_in_body(self):
        """test a tampered token is rejected with 401 and is not echoed back"""
        self.token = self._make_token() + 'tampered'
        self.test_app.set_cookie('token', self.token)
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment',
                                          data=EXAMPLE_PAYMENT_FORM.copy())
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()
        self._assert_token_absent(response)

    def test_payment_ledgerwriter_400_slack_alert_excludes_token(self):
        """test the Slack alert for a failed payment carries no session token"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.flask_app.config['SLACK_CHANNEL'] = SLACK_CHANNEL
        with patch('frontend.requests.post',
                   side_effect=self._mock_ledgerwriter_400()) as mock_post:
            response = self.test_app.post('/payment',
                                          data=EXAMPLE_PAYMENT_FORM.copy())
        self.assertEqual(response.status_code, 302)
        slack_calls = [call for call in mock_post.call_args_list
                       if call.kwargs.get('url') == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_calls), 1)
        payload = slack_calls[0].kwargs['json']
        self.assertEqual(payload['channel'], SLACK_CHANNEL)
        self.assertIn('[frontend] /payment failed', payload['text'])
        self.assertNotIn(self.token, payload['text'])
