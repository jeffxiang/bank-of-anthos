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
    """Generate priv,pub key pair for test"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption())
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    return private_key, public_key


EXAMPLE_PRIVATE_KEY, EXAMPLE_PUBLIC_KEY = generate_rsa_key()
# a second, unrelated keypair used to forge tokens with the wrong key
OTHER_PRIVATE_KEY, OTHER_PUBLIC_KEY = generate_rsa_key()

EXAMPLE_USERNAME = 'jdoe'
EXAMPLE_DISPLAY_NAME = 'John Doe'
EXAMPLE_ACCOUNT_ID = '1234567890'
EXAMPLE_CONTACT_ACCOUNT_ID = '9876543210'
LOCAL_ROUTING = '883745000'
EXTERNAL_ROUTING = '123456789'
TOKEN_EXPIRY_SECONDS = 3600
EXAMPLE_UUID = '00000000-0000-0000-0000-000000000000'


def make_token(private_key=EXAMPLE_PRIVATE_KEY,
               username=EXAMPLE_USERNAME,
               account_id=EXAMPLE_ACCOUNT_ID,
               expired=False):
    """Sign an example JWT with the given private key"""
    now = int(time.time())
    if expired:
        iat = now - 2 * TOKEN_EXPIRY_SECONDS
        exp = now - TOKEN_EXPIRY_SECONDS
    else:
        iat = now
        exp = now + TOKEN_EXPIRY_SECONDS
    payload = {
        'user': username,
        'acct': account_id,
        'name': EXAMPLE_DISPLAY_NAME,
        'iat': iat,
        'exp': exp,
    }
    return jwt.encode(payload, private_key, algorithm='RS256')


# environment the frontend app is created with in tests
EXAMPLE_ENVIRON = {
    'TRANSACTIONS_API_ADDR': 'ledgerwriter:8080',
    'USERSERVICE_API_ADDR': 'userservice:8080',
    'BALANCES_API_ADDR': 'balancereader:8080',
    'HISTORY_API_ADDR': 'transactionhistory:8080',
    'CONTACTS_API_ADDR': 'contacts:8080',
    'PUB_KEY_PATH': '1',
    'LOCAL_ROUTING_NUM': LOCAL_ROUTING,
    'ENABLE_TRACING': 'false',
    'VERSION': 'v0.1.0',
}

EXAMPLE_PAYMENT_FORM = {
    'account_num': EXAMPLE_CONTACT_ACCOUNT_ID,
    'amount': '25.50',
    'uuid': EXAMPLE_UUID,
}

EXAMPLE_DEPOSIT_FORM = {
    'account': '{{"account_num": "{}", "routing_num": "{}"}}'.format(
        EXAMPLE_CONTACT_ACCOUNT_ID, EXTERNAL_ROUTING),
    'amount': '100.00',
    'uuid': EXAMPLE_UUID,
}

EXAMPLE_LOGIN_FORM = {
    'username': EXAMPLE_USERNAME,
    'password': 'pwd',
}

EXAMPLE_SIGNUP_FORM = {
    'username': EXAMPLE_USERNAME,
    'password': 'pwd',
    'password-repeat': 'pwd',
    'firstname': 'John',
    'lastname': 'Doe',
    'birthday': '2000-01-01',
    'timezone': 'GMT+1',
    'address': '1600 Amphitheatre Parkway',
    'state': 'CA',
    'zip': '94043',
    'ssn': '123',
}

TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'
EXAMPLE_TRANSACTIONS = [
    # money received by the example user
    {
        'fromAccountNum': EXAMPLE_CONTACT_ACCOUNT_ID,
        'toAccountNum': EXAMPLE_ACCOUNT_ID,
        'amount': 5000,
        'timestamp': '2026-01-01T12:00:00.000000+00:00',
    },
    # money sent by the example user
    {
        'fromAccountNum': EXAMPLE_ACCOUNT_ID,
        'toAccountNum': EXAMPLE_CONTACT_ACCOUNT_ID,
        'amount': 2500,
        'timestamp': '2026-01-02T12:00:00.000000+00:00',
    },
    # transaction with an account not in the user's contacts
    {
        'fromAccountNum': '5555555555',
        'toAccountNum': EXAMPLE_ACCOUNT_ID,
        'amount': 100,
        'timestamp': '2026-01-03T12:00:00.000000+00:00',
    },
    # transaction not involving the user's account at all
    {
        'fromAccountNum': '5555555555',
        'toAccountNum': '6666666666',
        'amount': 200,
        'timestamp': '2026-01-04T12:00:00.000000+00:00',
    },
]

EXAMPLE_CONTACTS = [
    {
        'label': 'Friend',
        'account_num': EXAMPLE_CONTACT_ACCOUNT_ID,
        'routing_num': LOCAL_ROUTING,
        'is_external': False,
    },
]

# Slack incoming webhook used to verify error notifications
SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/test'
SLACK_CHANNEL = '#alerts'
