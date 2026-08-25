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
Tests for the frontend service, focused on auth-cookie handling and the
/payment error branches.
"""

import datetime
import os
import sys
import unittest
import uuid
from unittest.mock import MagicMock, mock_open, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import markupsafe
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# MarkupSafe's optional C extension is incompatible with the Python 3.14
# prerelease used by the test environment.
from markupsafe import _native
markupsafe._escape_inner = _native._escape_inner

# pylint: disable=wrong-import-position
from frontend import create_app  # noqa: E402

LOCAL_ROUTING = '883745000'
TRANSACTIONS_URI = 'http://ledgerwriter:8080/transactions'
SLACK_WEBHOOK_URL = 'http://slack.example.com/webhook'
# Synthetic account data only.
SENDER_ACCT = '1011226111'
RECIPIENT_ACCT = '1033623433'


def _generate_keypair():
    """Generate an ephemeral RSA keypair as PEM strings"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private_pem, public_pem


class TestFrontend(unittest.TestCase):
    """
    Test cases for the frontend service
    """

    def setUp(self):
        """Setup Flask TestClient with a mocked public key and env vars"""
        self.private_key, self.public_key = _generate_keypair()
        _, other_public_key = _generate_keypair()
        self.other_public_key = other_public_key

        # mock reading the userservice public key from disk
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            # mock env vars
            with patch(
                'os.environ',
                {
                    'VERSION': '1',
                    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
                    'USERSERVICE_API_ADDR': 'userservice:8080',
                    'BALANCES_API_ADDR': 'balancereader:8080',
                    'HISTORY_API_ADDR': 'transactionhistory:8080',
                    'CONTACTS_API_ADDR': 'contacts:8080',
                    'PUB_KEY_PATH': '1',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
                    'ENABLE_TRACING': 'false',
                },
            ):
                # the metadata server is unreachable outside GCP
                with patch('frontend.requests.get',
                           side_effect=requests.exceptions.RequestException()):
                    self.flask_app = create_app()

        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        self.token = self._make_token(self.private_key)

    def _make_token(self, key):
        """Sign a synthetic session token with the given private key"""
        expiry = datetime.datetime.now(
            tz=datetime.timezone.utc) + datetime.timedelta(hours=1)
        return jwt.encode({'user': 'testuser',
                           'acct': SENDER_ACCT,
                           'name': 'Test User',
                           'iat': datetime.datetime.now(
                               tz=datetime.timezone.utc),
                           'exp': expiry},
                          key,
                          algorithm='RS256')

    def _payment_form(self, amount='10.00'):
        return {'account_num': RECIPIENT_ACCT,
                'amount': amount,
                'uuid': str(uuid.uuid4())}

    def test_payment_401_when_token_cookie_missing(self):
        """test that an unauthenticated payment is rejected before any
        backend call"""
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment',
                                          data=self._payment_form())
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    def test_payment_401_when_token_cookie_signed_by_unknown_key(self):
        """test that a well-formed token signed by an unknown key is
        rejected"""
        forged_key, _ = _generate_keypair()
        self.test_app.set_cookie('token', self._make_token(forged_key))
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment',
                                          data=self._payment_form())
        self.assertEqual(response.status_code, 401)
        mock_post.assert_not_called()

    def test_payment_ledgerwriter_400_redirects_without_leaking_token(self):
        """test that a ledgerwriter 400 is surfaced as a failure message and
        alerted on, without leaking the session token"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.test_app.set_cookie('token', self.token)

        ledger_response = MagicMock()
        ledger_response.text = 'transaction declined: SCREEN-403'
        ledger_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError())

        def post_side_effect(*_args, **kwargs):
            if kwargs.get('url') == SLACK_WEBHOOK_URL:
                return MagicMock()
            return ledger_response

        with patch('frontend.requests.post',
                   side_effect=post_side_effect) as mock_post:
            response = self.test_app.post('/payment',
                                          data=self._payment_form())

        self.assertEqual(response.status_code, 302)
        self.assertIn('SCREEN-403', response.headers['Location'])
        # the token must not be echoed back to the user or to Slack
        self.assertNotIn(self.token, response.headers['Location'])
        self.assertNotIn(self.token, response.get_data(as_text=True))
        slack_calls = [call for call in mock_post.call_args_list
                       if call.kwargs.get('url') == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_calls), 1)
        slack_text = slack_calls[0].kwargs['json']['text']
        self.assertIn('/payment failed', slack_text)
        self.assertNotIn(self.token, slack_text)

    def test_payment_invalid_amount_redirects_without_submitting(self):
        """test that a non-numeric amount fails validation before the
        transaction is submitted"""
        self.test_app.set_cookie('token', self.token)

        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment',
                                          data=self._payment_form(
                                              amount='not-a-number'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        transaction_calls = [call for call in mock_post.call_args_list
                            if call.kwargs.get('url') == TRANSACTIONS_URI]
        self.assertEqual(transaction_calls, [])


if __name__ == '__main__':
    unittest.main()
