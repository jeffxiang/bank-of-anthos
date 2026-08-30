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
Tests for the frontend /payment endpoint and auth cookie handling
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch, mock_open

import jwt
import markupsafe
from markupsafe import _native as markupsafe_native
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from requests.exceptions import HTTPError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from frontend import create_app  # noqa: E402


def _use_pure_python_escape():
    """Fall back to markupsafe's Python escape when its C extension is broken.

    The compiled speedups return NULL without setting an exception on some
    CPython 3.14 alphas, which breaks every HTML escape (and therefore every
    redirect) in this interpreter.
    """
    try:
        markupsafe.escape('<')
    except SystemError:
        markupsafe._escape_inner = markupsafe_native._escape_inner  # pylint: disable=protected-access


_use_pure_python_escape()

LOCAL_ROUTING = '883745000'
EXAMPLE_ACCOUNT = '1011226111'
EXAMPLE_RECIPIENT = '1033623433'


def _generate_key_pair():
    """Generate an RSA key pair for signing test tokens"""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private_pem, public_pem


class TestFrontendPayment(unittest.TestCase):
    """Test cases for /payment error paths and auth cookie handling"""

    @classmethod
    def setUpClass(cls):
        cls.private_key, cls.public_key = _generate_key_pair()

    def setUp(self):
        """Setup Flask TestClient with a mocked public key and backend URIs"""
        # mock reading the userservice public key from disk
        with patch('frontend.open', mock_open(read_data=self.public_key)):
            with patch('os.environ', {
                    'VERSION': '1',
                    'PUB_KEY_PATH': '1',
                    'ENABLE_TRACING': 'false',
                    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
                    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
                    'CONTACTS_API_ADDR': 'contacts:8080',
            }):
                # the metadata server is unreachable outside GCP
                with patch('frontend.requests.get',
                           side_effect=HTTPError('no metadata server')):
                    self.flask_app = create_app()
        self.flask_app.config['TESTING'] = True
        self.test_app = self.flask_app.test_client()

    def _token(self, **overrides):
        """Sign a valid frontend session token"""
        issued = int(time.time())
        claims = {'user': 'testuser',
                  'acct': EXAMPLE_ACCOUNT,
                  'name': 'Test User',
                  'iat': issued,
                  'exp': issued + 3600}
        claims.update(overrides)
        return jwt.encode(claims, self.private_key, algorithm='RS256')

    def _payment_form(self, amount='10.00'):
        return {'account_num': EXAMPLE_RECIPIENT,
                'amount': amount,
                'uuid': '1cf5c4b1-4d4b-4f4b-9f4b-1cf5c4b14d4b'}

    def test_payment_401_when_token_cookie_is_not_valid(self):
        """/payment rejects missing, malformed and forged tokens"""
        other_private_key, _ = _generate_key_pair()
        forged = jwt.encode({'user': 'testuser',
                             'acct': EXAMPLE_ACCOUNT,
                             'name': 'Test User'},
                            other_private_key,
                            algorithm='RS256')
        expired = self._token(iat=0, exp=1)
        for name, cookie in [('missing', None),
                             ('malformed', 'not-a-jwt'),
                             ('forged', forged),
                             ('expired', expired)]:
            with self.subTest(token=name):
                if cookie is None:
                    self.test_app.delete_cookie('token')
                else:
                    self.test_app.set_cookie('token', cookie)
                with patch('frontend.requests.post') as mock_post:
                    response = self.test_app.post('/payment',
                                                  data=self._payment_form())
                self.assertEqual(response.status_code, 401)
                mock_post.assert_not_called()

    def test_payment_surfaces_ledgerwriter_400_to_user(self):
        """A 400 from ledgerwriter is surfaced in the redirect message"""
        self.test_app.set_cookie('token', self._token())
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = 'insufficient balance'
        mock_response.raise_for_status.side_effect = HTTPError('400 Client Error')
        with patch('frontend.requests.post', return_value=mock_response):
            response = self.test_app.post('/payment', data=self._payment_form())
        self.assertEqual(response.status_code, 302)
        self.assertIn('msg=Payment+failed:+insufficient+balance',
                      response.headers['Location'])

    def test_payment_invalid_amount_does_not_reach_ledgerwriter(self):
        """A non-numeric amount fails before any transaction is submitted"""
        self.test_app.set_cookie('token', self._token())
        with patch('frontend.requests.post') as mock_post:
            response = self.test_app.post(
                '/payment', data=self._payment_form(amount='not-a-number'))
        mock_post.assert_not_called()
        self.assertEqual(response.status_code, 302)
        # NOTE: the ValueError/DecimalException handler builds a
        # "<input> is not a valid number" message that is never used -- the
        # handler falls through to the generic message below.
        self.assertIn('msg=Payment+failed', response.headers['Location'])

    def test_payment_failure_does_not_leak_token(self):
        """The session token never reaches the response or the logs"""
        token = self._token()
        self.test_app.set_cookie('token', token)
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = 'invalid transaction'
        mock_response.raise_for_status.side_effect = HTTPError('400 Client Error')
        with patch('frontend.requests.post', return_value=mock_response):
            with self.assertLogs(self.flask_app.logger, level='DEBUG') as logs:
                response = self.test_app.post('/payment',
                                              data=self._payment_form())
        self.assertNotIn(token, response.get_data(as_text=True))
        self.assertNotIn(token, str(response.headers))
        for message in logs.output:
            self.assertNotIn(token, message)


if __name__ == '__main__':
    unittest.main()
