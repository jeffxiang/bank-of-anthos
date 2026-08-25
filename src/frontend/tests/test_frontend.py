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

"""Tests for frontend payment authentication and error handling."""

import sys
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, mock_open, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from frontend import api_call, traced_thread_pool_executor
from markupsafe import _native
import jwt
import markupsafe
import requests

sys.modules["api_call"] = api_call
sys.modules["traced_thread_pool_executor"] = traced_thread_pool_executor
import frontend.frontend as frontend

try:
    markupsafe._escape_inner("x")
except SystemError:
    # The MarkupSafe C speedup is broken on this CPython build.
    markupsafe._escape_inner = _native._escape_inner


def generate_rsa_key_pair():
    """Generate an ephemeral RSA private/public key pair for tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


PRIVATE_KEY, PUBLIC_KEY = generate_rsa_key_pair()
DIFFERENT_PRIVATE_KEY, _ = generate_rsa_key_pair()
TOKEN_PAYLOAD = {
    "user": "jdoe",
    "acct": "1234567890",
    "name": "J Doe",
}
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/test"
TRANSACTION_FORM = {
    "account_num": "0987654321",
    "amount": "12.34",
    "uuid": "test-payment-uuid",
}


class TestFrontend(unittest.TestCase):
    """Test cases for the frontend Flask app."""

    def setUp(self):
        """Set up a Flask test client with external calls mocked."""
        environment = {
            "VERSION": "1",
            "PUB_KEY_PATH": "/tmp/frontend-test-public-key.pem",
            "ENABLE_TRACING": "false",
            "LOCAL_ROUTING_NUM": "123456789",
            "TRANSACTIONS_API_ADDR": "transactions",
            "CONTACTS_API_ADDR": "contacts",
            "BALANCES_API_ADDR": "balances",
            "HISTORY_API_ADDR": "history",
            "USERSERVICE_API_ADDR": "userservice",
            "SLACK_WEBHOOK_URL": SLACK_WEBHOOK_URL,
            "SLACK_CHANNEL": "#alerts",
        }
        with patch(
            "frontend.frontend.open",
            mock_open(read_data=PUBLIC_KEY),
        ), patch("os.environ", environment), patch(
            "frontend.frontend.requests.get",
            return_value=MagicMock(ok=False),
        ):
            self.flask_app = frontend.create_app()
        self.flask_app.config["TESTING"] = True
        self.flask_app.config["PUBLIC_KEY"] = PUBLIC_KEY
        self.test_app = self.flask_app.test_client()

    def _set_token_cookie(self, private_key=PRIVATE_KEY):
        token = jwt.encode(TOKEN_PAYLOAD, private_key, algorithm="RS256")
        self.test_app.set_cookie("token", token)
        return token

    def test_payment_401_when_token_cookie_missing(self):
        """Rejects payment requests without an authentication cookie."""
        with patch("frontend.frontend.requests.post") as mocked_post:
            response = self.test_app.post("/payment", data=TRANSACTION_FORM)

        self.assertEqual(response.status_code, 401)
        mocked_post.assert_not_called()

    def test_payment_401_when_token_signature_invalid(self):
        """Rejects payment requests with an invalid token signature."""
        token = self._set_token_cookie(DIFFERENT_PRIVATE_KEY)

        response = self.test_app.post("/payment", data=TRANSACTION_FORM)

        self.assertEqual(response.status_code, 401)
        self.assertNotIn(token, response.get_data(as_text=True))

    def test_payment_redirects_home_when_ledgerwriter_returns_400(self):
        """Redirects with the backend error and alerts Slack on payment failure."""
        token = self._set_token_cookie()
        backend_error = "transaction recipient is screened"

        def post_side_effect(*args, **kwargs):
            if kwargs.get("url") == self.flask_app.config["TRANSACTIONS_URI"]:
                response = MagicMock()
                response.raise_for_status.side_effect = requests.exceptions.HTTPError()
                response.text = backend_error
                return response
            if kwargs.get("url") == SLACK_WEBHOOK_URL:
                return MagicMock(status_code=200)
            raise AssertionError("unexpected outbound POST URL")

        with patch("frontend.frontend.requests.post", side_effect=post_side_effect) as mocked_post:
            response = self.test_app.post("/payment", data=TRANSACTION_FORM)

        location = response.headers["Location"]
        location_message = parse_qs(urlparse(location).query)["msg"][0]
        self.assertEqual(response.status_code, 302)
        self.assertIn("/home", location)
        self.assertEqual(location_message, "Payment failed: transaction recipient is screened")
        self.assertIn(SLACK_WEBHOOK_URL, [call.kwargs["url"] for call in mocked_post.call_args_list])
        self.assertNotIn(token, location)
        self.assertNotIn(token, response.get_data(as_text=True))

    def test_payment_redirects_home_when_amount_not_a_number(self):
        """Redirects with a generic validation error and alerts Slack for invalid amounts."""
        token = self._set_token_cookie()
        form_data = {**TRANSACTION_FORM, "amount": "abc"}

        with patch(
            "frontend.frontend.requests.post",
            return_value=MagicMock(status_code=200),
        ) as mocked_post:
            response = self.test_app.post("/payment", data=form_data)

        location = response.headers["Location"]
        location_message = parse_qs(urlparse(location).query)["msg"][0]
        post_urls = [call.kwargs["url"] for call in mocked_post.call_args_list]
        self.assertEqual(response.status_code, 302)
        self.assertIn("/home", location)
        self.assertEqual(location_message, "Payment failed")
        self.assertIn(SLACK_WEBHOOK_URL, post_urls)
        self.assertNotIn(self.flask_app.config["TRANSACTIONS_URI"], post_urls)
        self.assertNotIn(token, location)
        self.assertNotIn(token, response.get_data(as_text=True))
