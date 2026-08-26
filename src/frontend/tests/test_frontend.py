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

import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from requests.exceptions import HTTPError
import jwt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from frontend import create_app

LOCAL_ROUTING = '883745000'
TRANSACTIONS_API_ADDR = 'ledgerwriter:8080'
TRANSACTIONS_URI = 'http://{}/transactions'.format(TRANSACTIONS_API_ADDR)
SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/T000/B000/XXXX'
SLACK_CHANNEL = '#alerts'
EXAMPLE_ACCOUNT_ID = '1234567890'
EXAMPLE_RECIPIENT_ID = '9876543210'


def _generate_keypair():
    """Generate an ephemeral RSA keypair for signing test tokens"""
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
    """
    Test cases for the frontend /payment endpoint
    """

    def setUp(self):
        """Setup Flask TestClient with a mocked public key and backend calls"""
        private_key, public_key = _generate_keypair()
        now = datetime.datetime.now(datetime.timezone.utc)
        self.token = jwt.encode(
            {
                'user': 'testuser',
                'acct': EXAMPLE_ACCOUNT_ID,
                'name': 'Test User',
                'iat': now,
                'exp': now + datetime.timedelta(hours=1),
            },
            private_key,
            algorithm='RS256',
        )
        # mock reading the userservice public key from disk
        with patch('frontend.open', mock_open(read_data=public_key)):
            # mock env vars
            with patch(
                'os.environ',
                {
                    'VERSION': '1',
                    'PUB_KEY_PATH': '1',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
                    'TRANSACTIONS_API_ADDR': TRANSACTIONS_API_ADDR,
                    'ENABLE_TRACING': 'false',
                },
            ):
                # mock the metadata server lookups done at startup
                with patch('frontend.requests.get'):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.test_app.set_cookie('token', self.token)

    def _payment_form(self, amount='10.00'):
        return {
            'account_num': EXAMPLE_RECIPIENT_ID,
            'amount': amount,
            'uuid': '11111111-1111-1111-1111-111111111111',
        }

    def _assert_no_token_leaked(self, response):
        """assert the session token never reaches the client in the response"""
        self.assertNotIn(self.token, response.headers.get('Location', ''))
        self.assertNotIn(self.token.encode(), response.data)

    def test_payment_unauthenticated_401_status_code_no_token_echoed(self):
        """test posting a payment without a token cookie is rejected"""
        self.test_app.delete_cookie('token')
        response = self.test_app.post('/payment', data=self._payment_form())
        # assert 401 response code
        self.assertEqual(response.status_code, 401)
        # assert no redirect leaks the user to the home page
        self.assertNotIn('Location', response.headers)

    def test_payment_expired_token_401_status_code_no_token_echoed(self):
        """test posting a payment with an expired token is rejected"""
        private_key, public_key = _generate_keypair()
        expired = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        self.token = jwt.encode(
            {
                'user': 'testuser',
                'acct': EXAMPLE_ACCOUNT_ID,
                'name': 'Test User',
                'iat': expired,
                'exp': expired + datetime.timedelta(hours=1),
            },
            private_key,
            algorithm='RS256',
        )
        self.flask_app.config['PUBLIC_KEY'] = public_key
        self.test_app.set_cookie('token', self.token)
        response = self.test_app.post('/payment', data=self._payment_form())
        # assert 401 response code
        self.assertEqual(response.status_code, 401)
        # assert the rejected token is not echoed back to the client
        self._assert_no_token_leaked(response)

    @patch('frontend.requests.post')
    def test_payment_invalid_amount_redirects_without_echoing_input(self, mock_post):
        """test an unparseable amount redirects home with a generic message"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.flask_app.config['SLACK_CHANNEL'] = SLACK_CHANNEL
        response = self.test_app.post('/payment',
                                      data=self._payment_form(amount='not-a-number'))
        # assert the user is redirected back home with the failure message and
        # that the rejected input is not reflected into the redirect
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('msg=Payment+failed'),
                        response.headers['Location'])
        # assert the only outbound call was the Slack alert, not a transaction
        self.assertEqual(mock_post.call_args.kwargs['url'], SLACK_WEBHOOK_URL)
        self.assertEqual(mock_post.call_args.kwargs['json']['channel'], SLACK_CHANNEL)
        # assert the token is not echoed into the redirect or the Slack alert
        self._assert_no_token_leaked(response)
        self.assertNotIn(self.token, mock_post.call_args.kwargs['json']['text'])

    @patch('frontend.requests.post')
    def test_payment_ledgerwriter_error_redirects_and_notifies_slack(self, mock_post):
        """test a ledgerwriter rejection is surfaced without leaking the token"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL

        backend_response = MagicMock()
        backend_response.text = 'account not found'
        backend_response.raise_for_status.side_effect = HTTPError('400 Client Error')

        def post_side_effect(**kwargs):
            if kwargs['url'] == TRANSACTIONS_URI:
                return backend_response
            return MagicMock()

        mock_post.side_effect = post_side_effect
        response = self.test_app.post('/payment', data=self._payment_form())
        # assert the backend failure reason is shown to the user
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed:+account+not+found',
                      response.headers['Location'])
        # assert the failure is reported to Slack
        slack_call = [call for call in mock_post.call_args_list
                      if call.kwargs['url'] == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_call), 1)
        self.assertIn('[frontend] /payment failed', slack_call[0].kwargs['json']['text'])
        # assert the token is not echoed into the redirect or the Slack alert
        self._assert_no_token_leaked(response)
        self.assertNotIn(self.token, slack_call[0].kwargs['json']['text'])


if __name__ == '__main__':
    unittest.main()
