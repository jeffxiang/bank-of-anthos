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
Tests for the frontend service: auth cookies, /payment error handling, and
guarantees that the session token never leaks into rendered output, redirect
Location headers, or outgoing Slack alerts.
"""

import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, mock_open, patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from requests.exceptions import HTTPError, RequestException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import create_app  # pylint: disable=wrong-import-position

LOCAL_ROUTING = '883745000'
SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/TEST/FAKE'
TRANSACTIONS_API_ADDR = 'ledgerwriter.test:8080'
USERSERVICE_API_ADDR = 'userservice.test:8080'
CONTACTS_API_ADDR = 'contacts.test:8080'
# Synthetic account fixtures only.
EXAMPLE_ACCOUNT = '1011226111'
RECIPIENT_ACCOUNT = '1033623433'
ATTACKER_ACCOUNT = '9999999999'


def generate_rsa_key():
    """Generate an ephemeral RSA keypair (PEM private, PEM public) for tests"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    return private_key, public_key


EXAMPLE_PRIVATE_KEY, EXAMPLE_PUBLIC_KEY = generate_rsa_key()


class TestFrontend(unittest.TestCase):
    """Test cases for the frontend service"""

    def setUp(self):
        """Create the Flask app with mocked key file, env vars and metadata server"""
        env = {
            'VERSION': '1',
            'ENABLE_TRACING': 'false',
            'PUB_KEY_PATH': '/dev/null',
            'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
            'TRANSACTIONS_API_ADDR': TRANSACTIONS_API_ADDR,
            'USERSERVICE_API_ADDR': USERSERVICE_API_ADDR,
            'CONTACTS_API_ADDR': CONTACTS_API_ADDR,
            'BALANCES_API_ADDR': 'balancereader.test:8080',
            'HISTORY_API_ADDR': 'transactionhistory.test:8080',
            'SLACK_WEBHOOK_URL': SLACK_WEBHOOK_URL,
        }
        with patch('frontend.open',
                   mock_open(read_data=EXAMPLE_PUBLIC_KEY.decode('utf-8'))):
            with patch('os.environ', env):
                # the metadata server is unreachable outside GCE
                with patch('frontend.requests.get',
                           side_effect=RequestException('no metadata server')):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()
        issued_at = int(time.time())
        self.token = jwt.encode(
            {
                'user': 'testuser',
                'acct': EXAMPLE_ACCOUNT,
                'name': 'Test User',
                'iat': issued_at,
                'exp': issued_at + 3600,
            },
            EXAMPLE_PRIVATE_KEY,
            algorithm='RS256')

    def _payment_form(self, amount='10.00', account_num=RECIPIENT_ACCOUNT):
        return {
            'account_num': account_num,
            'amount': amount,
            'uuid': '00000000-0000-0000-0000-000000000001',
        }

    def _assert_token_not_leaked(self, response, mock_post):
        """Assert the session token is absent from the response and any alert"""
        self.assertNotIn(self.token, response.headers.get('Location', ''))
        self.assertNotIn(self.token, response.data.decode('utf-8'))
        for call in mock_post.call_args_list:
            if call.kwargs.get('url') == SLACK_WEBHOOK_URL:
                self.assertNotIn(self.token, str(call.kwargs.get('json')))

    def test_payment_401_unauthenticated_sends_no_alert(self):
        """test /payment rejects a missing or wrongly signed token with 401"""
        rogue_private_key, _ = generate_rsa_key()
        rogue_token = jwt.encode({'user': 'testuser', 'acct': EXAMPLE_ACCOUNT},
                                 rogue_private_key,
                                 algorithm='RS256')
        for name, cookie in [('no token cookie', None),
                             ('token signed by unknown key', rogue_token)]:
            with self.subTest(name):
                self.test_app.delete_cookie('token', domain='localhost')
                if cookie is not None:
                    self.test_app.set_cookie('token', cookie, domain='localhost')
                with patch('frontend.requests.post') as mock_post:
                    response = self.test_app.post('/payment',
                                                  data=self._payment_form())
                self.assertEqual(response.status_code, 401)
                mock_post.assert_not_called()

    def test_payment_ledger_rejection_redirects_without_leaking_token(self):
        """test a 400 from ledgerwriter surfaces its message and hides the token"""
        ledger_response = MagicMock()
        ledger_response.text = 'insufficient balance'
        ledger_response.raise_for_status.side_effect = HTTPError('400 Client Error')
        self.test_app.set_cookie('token', self.token, domain='localhost')
        with patch('frontend.requests.post',
                   return_value=ledger_response) as mock_post:
            response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed:+insufficient+balance',
                      response.headers['Location'])
        self._assert_token_not_leaked(response, mock_post)
        slack_calls = [call for call in mock_post.call_args_list
                       if call.kwargs.get('url') == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_calls), 1)

    def test_payment_invalid_amount_redirects_without_leaking_token(self):
        """test a non-numeric amount fails the payment without leaking the token"""
        self.test_app.set_cookie('token', self.token, domain='localhost')
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post('/payment',
                                          data=self._payment_form(amount='abc'))
        self.assertEqual(response.status_code, 302)
        # the specific "not a valid number" message is dropped by the generic
        # fall-through redirect; only the generic failure reaches the user
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        self._assert_token_not_leaked(response, mock_post)
        slack_payloads = [str(call.kwargs.get('json'))
                         for call in mock_post.call_args_list
                         if call.kwargs.get('url') == SLACK_WEBHOOK_URL]
        self.assertEqual(len(slack_payloads), 1)
        self.assertIn('/payment failed', slack_payloads[0])

    def test_payment_sender_account_comes_from_token_not_form(self):
        """test the sender account is taken from the token, not from form input"""
        ledger_response = MagicMock()
        ledger_response.raise_for_status.return_value = None
        self.test_app.set_cookie('token', self.token, domain='localhost')
        form = self._payment_form()
        form['fromAccountNum'] = ATTACKER_ACCOUNT
        with patch('frontend.requests.post',
                   return_value=ledger_response) as mock_post:
            with patch('frontend.sleep'):
                response = self.test_app.post('/payment', data=form)
        self.assertEqual(response.status_code, 303)
        posted = json.loads(mock_post.call_args.kwargs['data'])
        self.assertEqual(posted['fromAccountNum'], EXAMPLE_ACCOUNT)
        self.assertEqual(posted['toAccountNum'], RECIPIENT_ACCOUNT)


if __name__ == '__main__':
    unittest.main()
