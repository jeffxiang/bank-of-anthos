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
Example constants used in tests
"""

import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_key():
    """Generate an ephemeral priv,pub key pair for test"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_key, public_key


EXAMPLE_PRIVATE_KEY, EXAMPLE_PUBLIC_KEY = generate_rsa_key()
# a second, unrelated key pair: tokens signed with it must not verify
OTHER_PRIVATE_KEY, OTHER_PUBLIC_KEY = generate_rsa_key()

EXAMPLE_ACCOUNT_ID = '1011226111'
EXAMPLE_USERNAME = 'jdoe'
EXAMPLE_DISPLAY_NAME = 'John Doe'
EXAMPLE_RECIPIENT_ACCOUNT_ID = '9099791699'
LOCAL_ROUTING_NUM = '883745000'
EXTERNAL_ROUTING_NUM = '123456789'
TOKEN_EXPIRY_SECONDS = 3600


def generate_token(private_key=None,
                   account_id=EXAMPLE_ACCOUNT_ID,
                   username=EXAMPLE_USERNAME,
                   name=EXAMPLE_DISPLAY_NAME,
                   expiry_seconds=TOKEN_EXPIRY_SECONDS):
    """Generate a signed JWT mirroring the one issued by userservice"""
    issued_at = int(time.time())
    payload = {
        'user': username,
        'acct': account_id,
        'name': name,
        'iat': issued_at,
        'exp': issued_at + expiry_seconds,
    }
    return jwt.encode(payload,
                      private_key or EXAMPLE_PRIVATE_KEY,
                      algorithm='RS256')


EXAMPLE_TOKEN = generate_token()
# valid RS256 token signed by a key the frontend does not trust
FOREIGN_TOKEN = generate_token(private_key=OTHER_PRIVATE_KEY)
# correctly signed but already expired
EXPIRED_TOKEN = generate_token(expiry_seconds=-1)

EXAMPLE_BALANCE = 12345
EXAMPLE_CONTACTS = [
    {
        'label': 'Friend',
        'account_num': EXAMPLE_RECIPIENT_ACCOUNT_ID,
        'routing_num': LOCAL_ROUTING_NUM,
        'is_external': False,
    },
]
EXAMPLE_TRANSACTIONS = [
    {
        'amount': 5000,
        'fromAccountNum': EXAMPLE_ACCOUNT_ID,
        'fromRoutingNum': LOCAL_ROUTING_NUM,
        'toAccountNum': EXAMPLE_RECIPIENT_ACCOUNT_ID,
        'toRoutingNum': LOCAL_ROUTING_NUM,
        'timestamp': '2026-01-01T00:00:00.000+00:00',
    },
    {
        'amount': 2500,
        'fromAccountNum': EXAMPLE_RECIPIENT_ACCOUNT_ID,
        'fromRoutingNum': LOCAL_ROUTING_NUM,
        'toAccountNum': EXAMPLE_ACCOUNT_ID,
        'toRoutingNum': LOCAL_ROUTING_NUM,
        'timestamp': '2026-01-02T00:00:00.000+00:00',
    },
    {
        'amount': 100,
        'fromAccountNum': '0000000000',
        'fromRoutingNum': EXTERNAL_ROUTING_NUM,
        'toAccountNum': '1111111111',
        'toRoutingNum': LOCAL_ROUTING_NUM,
        'timestamp': '2026-01-03T00:00:00.000+00:00',
    },
]

EXAMPLE_PAYMENT_REQUEST = {
    'account_num': EXAMPLE_RECIPIENT_ACCOUNT_ID,
    'amount': '12.34',
    'uuid': 'f0a12dbe-4a4e-4a09-b5f4-1cb2e5e6e0a1',
}
EXAMPLE_DEPOSIT_REQUEST = {
    'account': '{{"account_num": "0000000000", "routing_num": "{}"}}'.format(
        EXTERNAL_ROUTING_NUM),
    'amount': '100.00',
    'uuid': '2d4b3d95-5d2d-4f7a-9a3b-2d3ad7c9e2b7',
}
EXAMPLE_LOGIN_REQUEST = {
    'username': EXAMPLE_USERNAME,
    'password': 'synthetic-password',
}
EXAMPLE_SIGNUP_REQUEST = {
    'username': EXAMPLE_USERNAME,
    'password': 'synthetic-password',
    'password-repeat': 'synthetic-password',
    'firstname': 'John',
    'lastname': 'Doe',
    'birthday': '2000-01-01',
    'timezone': 'GMT+1',
    'address': '1600 Amphitheatre Parkway',
    'state': 'CA',
    'zip': '94043',
    'ssn': '000-00-0000',
}

# amounts that must be rejected as non-numeric by /payment and /deposit
INVALID_AMOUNTS = [
    '',
    ' ',
    'abc',
    '1.2.3',
    '12,34',
    '1e',
    '💸',
    '1️⃣0',
    '--5',
]

# Slack incoming webhook used to verify error notifications
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/test"
SLACK_CHANNEL = "#alerts"
