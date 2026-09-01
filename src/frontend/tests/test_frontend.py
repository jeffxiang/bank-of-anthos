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
Tests for the frontend /payment error paths
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, mock_open, patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from requests.exceptions import HTTPError, RequestException

# frontend.py uses flat imports (`from api_call import ApiCall`), so the
# service directory has to be importable as a top-level path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import create_app  # pylint: disable=wrong-import-position


def generate_rsa_key():
    """Generate an ephemeral priv,pub key pair for test"""
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

LOCAL_ROUTING = '883745000'
SLACK_WEBHOOK_URL = 'https://hooks.slack.test/services/T000/B000/XXX'
SLACK_CHANNEL = '#alerts'
EXAMPLE_ACCOUNT_ID = '1011226111'
EXAMPLE_RECIPIENT = '1055757655'
SCREENING_DECLINE = 'bad request: recipient screening declined'
UPSTREAM_5XX = 'Internal Server Error'
INVALID_AMOUNTS = ['not-a-number', '', '12.3.4', '💸', '1,00']

EXAMPLE_ENV = {
    'VERSION': '1',
    'PUB_KEY_PATH': '1',
    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
    'ENABLE_TRACING': 'false',
    'SLACK_WEBHOOK_URL': SLACK_WEBHOOK_URL,
    'SLACK_CHANNEL': SLACK_CHANNEL,
}


class TestFrontendPayment(unittest.TestCase):
    """
    Test cases for the /payment endpoint of the frontend service
    """

    def setUp(self):
        """Setup Flask TestClient with a mocked public key and no metadata server"""
        # mock opening the public key file
        with patch('frontend.open', mock_open(read_data=EXAMPLE_PUBLIC_KEY.decode())):
            # mock env vars
            with patch('os.environ', EXAMPLE_ENV):
                # the GCE metadata server is unreachable in tests
                with patch('frontend.requests.get',
                           side_effect=RequestException('no metadata server')):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.flask_app.config['PUBLIC_KEY'] = EXAMPLE_PUBLIC_KEY
        self.test_app = self.flask_app.test_client()
        self.token = self._make_token()
        self.payment_form = {
            'account_num': EXAMPLE_RECIPIENT,
            'amount': '25.00',
            'uuid': 'e0a8b1d0-0000-4000-8000-000000000001',
        }

    @staticmethod
    def _make_token(expired=False):
        """Sign an ephemeral JWT for the example account"""
        now = datetime.now(tz=timezone.utc)
        issued_at = now - timedelta(hours=2) if expired else now
        expires_at = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
        return jwt.encode({'user': 'testuser',
                           'acct': EXAMPLE_ACCOUNT_ID,
                           'name': 'Test User',
                           'iat': issued_at,
                           'exp': expires_at},
                          EXAMPLE_PRIVATE_KEY,
                          algorithm='RS256')

    @staticmethod
    def _upstream_error_response(status_code, text):
        """Build a mocked ledgerwriter response that fails raise_for_status"""
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        response.raise_for_status.side_effect = HTTPError(
            '{} Error'.format(status_code), response=response)
        return response

    def _post_payment(self, form=None, token=None):
        """POST /payment with the given form and auth cookie"""
        if token is not None:
            self.test_app.set_cookie('token', token)
        return self.test_app.post('/payment',
                                  data=form if form is not None else self.payment_form,
                                  follow_redirects=False)

    def _slack_payloads(self, mocked_post):
        """Return the payloads posted to the Slack webhook"""
        return [call.kwargs['json'] for call in mocked_post.call_args_list
                if call.kwargs.get('url') == SLACK_WEBHOOK_URL]

    def test_payment_upstream_400_screening_decline_redirects_with_reason(self):
        """test that a ledgerwriter 400 decline is surfaced to the user and to Slack"""
        with patch('frontend.requests.post') as mocked_post:
            mocked_post.return_value = self._upstream_error_response(400, SCREENING_DECLINE)
            response = self._post_payment(token=self.token)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        self.assertIn('screening+declined', response.headers['Location'])
        slack_payloads = self._slack_payloads(mocked_post)
        self.assertEqual(len(slack_payloads), 1)
        self.assertIn(SCREENING_DECLINE, slack_payloads[0]['text'])

    def test_payment_upstream_500_redirects_with_reason(self):
        """test that a ledgerwriter 5xx is reported as a failed payment"""
        with patch('frontend.requests.post') as mocked_post:
            mocked_post.return_value = self._upstream_error_response(500, UPSTREAM_5XX)
            response = self._post_payment(token=self.token)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Payment+failed', response.headers['Location'])
        slack_payloads = self._slack_payloads(mocked_post)
        self.assertEqual(len(slack_payloads), 1)
        self.assertIn(UPSTREAM_5XX, slack_payloads[0]['text'])

    def test_payment_unreachable_ledgerwriter_redirects_without_reason(self):
        """test that a transport error redirects to the generic failure message"""
        with patch('frontend.requests.post') as mocked_post:
            mocked_post.side_effect = [RequestException('connection refused'), MagicMock()]
            response = self._post_payment(token=self.token)
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed', response.headers['Location'])
        self.assertEqual(mocked_post.call_args_list[-1].kwargs['url'], SLACK_WEBHOOK_URL)

    def test_payment_invalid_amounts_redirect_and_never_reach_ledgerwriter(self):
        """test that unparseable amounts fail before any transaction is submitted"""
        for amount in INVALID_AMOUNTS:
            with self.subTest(amount=amount):
                form = dict(self.payment_form, amount=amount)
                with patch('frontend.requests.post') as mocked_post:
                    response = self._post_payment(form=form, token=self.token)
                self.assertEqual(response.status_code, 302)
                self.assertIn('msg=Payment+failed', response.headers['Location'])
                ledger_calls = [call for call in mocked_post.call_args_list
                                if call.kwargs.get('url') != SLACK_WEBHOOK_URL]
                self.assertEqual(ledger_calls, [])

    def test_payment_without_token_returns_401(self):
        """test that a missing auth cookie is rejected"""
        with patch('frontend.requests.post') as mocked_post:
            response = self._post_payment()
        self.assertEqual(response.status_code, 401)
        mocked_post.assert_not_called()

    def test_payment_with_expired_token_returns_401(self):
        """test that an expired auth cookie is rejected"""
        with patch('frontend.requests.post') as mocked_post:
            response = self._post_payment(token=self._make_token(expired=True))
        self.assertEqual(response.status_code, 401)
        mocked_post.assert_not_called()

    def test_payment_with_foreign_token_returns_401(self):
        """test that a token signed by another key is rejected"""
        foreign_private_key, _ = generate_rsa_key()
        foreign_token = jwt.encode({'user': 'testuser',
                                    'acct': EXAMPLE_ACCOUNT_ID,
                                    'name': 'Test User'},
                                   foreign_private_key,
                                   algorithm='RS256')
        with patch('frontend.requests.post') as mocked_post:
            response = self._post_payment(token=foreign_token)
        self.assertEqual(response.status_code, 401)
        mocked_post.assert_not_called()

    def test_payment_failure_never_leaks_token_in_output_or_logs(self):
        """test that the auth token is absent from the response, redirect and logs"""
        with self.assertLogs(self.flask_app.logger, level='DEBUG') as logs:
            with patch('frontend.requests.post') as mocked_post:
                mocked_post.return_value = self._upstream_error_response(400,
                                                                        SCREENING_DECLINE)
                response = self._post_payment(token=self.token)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(self.token, response.get_data(as_text=True))
        self.assertNotIn(self.token, response.headers['Location'])
        self.assertNotIn(self.token, ' '.join(logs.output))
        self.assertNotIn(self.token, str(self._slack_payloads(mocked_post)))
