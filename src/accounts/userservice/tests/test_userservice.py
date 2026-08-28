# Copyright 2019 Google LLC
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
Tests for userservice
"""

import random
import unittest
from unittest.mock import patch, mock_open

from requests.exceptions import RequestException
from sqlalchemy.exc import SQLAlchemyError
import jwt

from userservice.userservice import create_app
from userservice.tests.constants import (
    TIMESTAMP_FORMAT,
    EXAMPLE_USER_REQUEST,
    EXAMPLE_USER,
    EXPECTED_FIELDS,
    EXAMPLE_PRIVATE_KEY,
    EXAMPLE_PUBLIC_KEY,
    INVALID_USERNAMES,
    SLACK_CHANNEL,
    SLACK_WEBHOOK_URL,
)

# PII edge cases, kept here because this slice may only touch this test file
WHITESPACE_ONLY_PII_FIELDS = ['firstname', 'lastname', 'address', 'state', 'zip', 'ssn']
UNICODE_NAME = 'Jo\u00e3o \u5c71\u7530 \U0001f3e6'
SCRIPT_INJECTION_NAME = '<script>alert("xss")</script>Doe'
OVERLONG_ADDRESS = 'A' * 5000


class TestUserservice(unittest.TestCase):
    """
    Tests cases for userservice
    """

    def setUp(self):
        """Setup Flask TestClient and mock userdatabase"""
        # mock opening files
        with patch('userservice.userservice.open', mock_open(read_data='foo')):
            # mock env vars
            with patch(
                'os.environ',
                {
                    'VERSION': '1',
                    'TOKEN_EXPIRY_SECONDS': '3600',
                    'PRIV_KEY_PATH': '1',
                    'PUB_KEY_PATH': '1',
                    'ENABLE_TRACING': 'false',
                },
            ):
                # mock db module as MagicMock, context manager handles cleanup
                with patch('userservice.userservice.UserDb') as mock_db:
                    self.mocked_db = mock_db
                    # get create flask app
                    self.flask_app = create_app()
                    # set testing config
                    self.flask_app.config['TESTING'] = True
                    # create test client
                    self.test_app = self.flask_app.test_client()

    def test_version_endpoint_returns_200_status_code_correct_version(self):
        """test if correct version is returned"""
        # generate a version
        version = str(random.randint(1, 9))
        # set version in Flask config
        self.flask_app.config['VERSION'] = version
        # send get request to test client
        response = self.test_app.get('/version')
        # assert 200 response code
        self.assertEqual(response.status_code, 200)
        # assert both versions are equal
        self.assertEqual(response.data, version.encode())

    def test_ready_endpoint_200_status_code_ok_string(self):
        """test if correct response is returned from readiness probe"""
        response = self.test_app.get('/ready')
        # assert 200 response code
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'ok')

    def test_create_user_201_status_code_correct_db_user_object(self):
        """test creating a new user who does not exist in the DB"""
        # mock return value of get_user which checks if user exists as None
        self.mocked_db.return_value.get_user.return_value = None
        # mock return value for generate_id from user_db
        self.mocked_db.return_value.generate_accountid.return_value = '123'
        # create example user request
        example_user_request = EXAMPLE_USER_REQUEST.copy()
        # send request to test client
        response = self.test_app.post('/users', data=example_user_request)
        # assert 201 response code
        self.assertEqual(response.status_code, 201)
        # assert user object added to database had the required fields
        # get the arg that user_db.add_user was called with
        user_object = self.mocked_db.return_value.add_user.call_args[0][0]
        # not comparing passhash due to differences in salt
        user_object.pop('passhash')
        # assert user_object is equal to expected object
        expected_user_object = EXAMPLE_USER.copy()
        # convert time to string from datetime
        expected_user_object['birthday'] = expected_user_object['birthday'].strftime(
            TIMESTAMP_FORMAT
        )
        # not comparing passhash due to differences in salt
        expected_user_object.pop('passhash')
        # assert all keys are equal except for hashed pwd
        self.assertEqual(user_object, expected_user_object)

    def test_create_user_existing_409_status_code_error_message(self):
        """test creating a new user who already exists in the DB"""
        # mock return value of get_user which checks if user exists
        self.mocked_db.return_value.get_user.return_value = {}
        example_user_request = EXAMPLE_USER_REQUEST.copy()
        # create example user request
        example_user_request['username'] = 'foo'
        # send request to test client
        response = self.test_app.post('/users', data=example_user_request)
        # assert 409 response code
        self.assertEqual(response.status_code, 409)
        # assert we get correct error message
        self.assertEqual(
            response.data,
            'user {} already exists'.format(example_user_request['username']).encode()
        )

    def test_create_user_sql_error_500_status_code_error_message(self):
        """test creating a new user but throws SQL error when trying to add"""
        # mock return value of get_user which checks if user exists as None
        self.mocked_db.return_value.get_user.return_value = None
        # mock return value of add_user to throw SQLAlchemyError
        self.mocked_db.return_value.add_user.side_effect = SQLAlchemyError()
        # create example user request
        example_user = EXAMPLE_USER_REQUEST.copy()
        example_user['username'] = 'foo'
        # send request to test client
        response = self.test_app.post('/users', data=example_user)
        # assert 500 response code
        self.assertEqual(response.status_code, 500)
        # assert we get correct error message
        self.assertEqual(response.data, b'failed to create user')

    def test_create_user_malformed_400_status_code_error_message(self):
        """test creating a new user without required keys"""
        # test each expected field missing from user request
        for expected_field in EXPECTED_FIELDS:
            # create example user request
            example_user = EXAMPLE_USER_REQUEST.copy()
            # remove a required field
            example_user.pop(expected_field)
            # send request to test client
            response = self.test_app.post('/users', data=example_user)
            # assert 400 response code
            self.assertEqual(response.status_code, 400)
            # assert we get correct error message
            self.assertEqual(response.data, b'missing required field(s)')

    def test_create_user_malformed_empty_400_status_code_error_message(self):
        """test creating a new user with empty value for required key"""
        # create example user request
        example_user = EXAMPLE_USER_REQUEST.copy()
        # set empty value for required key
        example_user['username'] = ''
        # send request to test client
        response = self.test_app.post('/users', data=example_user)
        # assert 400 response code
        self.assertEqual(response.status_code, 400)
        # assert we get correct error message
        self.assertEqual(response.data, b'missing value for input field(s)')

    def test_create_user_mismatch_password_400_status_code_error_message(self):
        """test creating a new user with mismatched password values"""
        # create example user request
        example_user = EXAMPLE_USER_REQUEST.copy()
        # set mismatch values for password and password-repeat
        example_user['password'] = 'foo'
        example_user['password-repeat'] = 'bar'
        # send request to test client
        response = self.test_app.post('/users', data=example_user)
        # assert 400 response code
        self.assertEqual(response.status_code, 400)
        # assert we get correct error message
        self.assertEqual(response.data, b'passwords do not match')

    # mock check pw to return true to simulate correct password
    @patch('bcrypt.checkpw', return_value=True)
    def test_login_200_status_code_jwt_decoding_payload_passes(self, _mock_checkpw):
        """test logging in with existing user"""
        # create example user request
        example_user = EXAMPLE_USER.copy()
        example_user_request = EXAMPLE_USER_REQUEST.copy()
        self.mocked_db.return_value.get_user.return_value = example_user
        # set private key
        self.flask_app.config['PRIVATE_KEY'] = EXAMPLE_PRIVATE_KEY
        # send request to test client
        response = self.test_app.get('/login', query_string=example_user_request)
        # assert 200 response
        self.assertEqual(response.status_code, 200)
        # assert we get a json response with just token key
        self.assertEqual(list(response.json.keys()), ['token'])
        # decode payload using public key
        decoded_value = jwt.decode(algorithms='RS256',
                                   jwt=response.json['token'],
                                   key=EXAMPLE_PUBLIC_KEY,)
        # assert fields match user request
        self.assertEqual(decoded_value['user'], EXAMPLE_USER['username'])
        self.assertEqual(
            decoded_value['name'],
            "{} {}".format(EXAMPLE_USER['firstname'], EXAMPLE_USER['lastname']),
        )

    # mock check pw to return false
    @patch('bcrypt.checkpw', return_value=False)
    def test_login_invalid_password_401_status_code_error_message(self, _mock_checkpw):
        """test logging in with existing user and wrong password"""
        # create example user request
        example_user = EXAMPLE_USER.copy()
        example_user_request = EXAMPLE_USER_REQUEST.copy()
        self.mocked_db.return_value.get_user.return_value = example_user
        response = self.test_app.get('/login', query_string=example_user_request)
        # assert 401 response
        self.assertEqual(response.status_code, 401)
        # assert we get correct error message
        self.assertEqual(response.data, b'invalid login')

    def test_login_non_existent_user_404_status_code_error_message(self):
        """test logging in with a user that does not exist"""
        # mock return value of get_user which checks if user exists as None
        self.mocked_db.return_value.get_user.return_value = None
        # example user request
        example_user_request = EXAMPLE_USER_REQUEST.copy()
        example_user_request['username'] = 'foo'
        # send request to test client
        response = self.test_app.get('/login', query_string=example_user_request)
        # assert 404 response
        self.assertEqual(response.status_code, 404)
        # assert we get correct error message
        self.assertEqual(
            response.data,
            'user {} does not exist'.format(example_user_request['username']).encode()
        )

    @patch('userservice.userservice.requests.post')
    def test_slack_notification_sent_on_error(self, mock_post):
        """test a Slack notification is posted when a request fails"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.flask_app.config['SLACK_CHANNEL'] = SLACK_CHANNEL
        # mock return value of get_user which checks if user exists as None
        self.mocked_db.return_value.get_user.return_value = None
        # mock return value of add_user to throw SQLAlchemyError
        self.mocked_db.return_value.add_user.side_effect = SQLAlchemyError()
        response = self.test_app.post('/users', data=EXAMPLE_USER_REQUEST.copy())
        # assert behavior on failure is unchanged
        self.assertEqual(response.status_code, 500)
        # assert the webhook was called with the endpoint and channel
        self.assertEqual(mock_post.call_args.kwargs['url'], SLACK_WEBHOOK_URL)
        payload = mock_post.call_args.kwargs['json']
        self.assertEqual(payload['channel'], SLACK_CHANNEL)
        self.assertIn('[userservice] /users failed', payload['text'])

    @patch('userservice.userservice.requests.post')
    def test_no_slack_notification_when_webhook_unset(self, mock_post):
        """test no Slack notification is sent when no webhook is configured"""
        self.mocked_db.return_value.get_user.return_value = None
        self.mocked_db.return_value.add_user.side_effect = SQLAlchemyError()
        response = self.test_app.post('/users', data=EXAMPLE_USER_REQUEST.copy())
        self.assertEqual(response.status_code, 500)
        mock_post.assert_not_called()

    @patch('userservice.userservice.requests.post',
           side_effect=RequestException('slack down'))
    def test_slack_failure_does_not_affect_response(self, _mock_post):
        """test a failing Slack webhook does not change the error response"""
        self.flask_app.config['SLACK_WEBHOOK_URL'] = SLACK_WEBHOOK_URL
        self.mocked_db.return_value.get_user.return_value = None
        self.mocked_db.return_value.add_user.side_effect = SQLAlchemyError()
        response = self.test_app.post('/users', data=EXAMPLE_USER_REQUEST.copy())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, b'failed to create user')

    def test_create_user_whitespace_only_pii_currently_accepted(self):
        """characterize whitespace-only PII values, which validation lets through

        KNOWN BUG: __validate_new_user checks
        `not bool(req[f] or req[f].strip())`, which short-circuits on the truthy
        raw value, so '   ' never reaches the strip() check. This test pins the
        current behaviour; flip it to expect 400 once validation is fixed.
        """
        self.mocked_db.return_value.get_user.return_value = None
        self.mocked_db.return_value.generate_accountid.return_value = '123'
        for pii_field in WHITESPACE_ONLY_PII_FIELDS:
            example_user = EXAMPLE_USER_REQUEST.copy()
            example_user[pii_field] = '   '
            response = self.test_app.post('/users', data=example_user)
            self.assertEqual(response.status_code, 201,
                             '{} behaviour changed'.format(pii_field))
            user_object = self.mocked_db.return_value.add_user.call_args[0][0]
            self.assertEqual(user_object[pii_field], '   ')

    def test_create_user_201_status_code_unicode_and_overlong_pii_stored_sanitized(self):
        """test creating a new user with unicode and over-length PII values"""
        self.mocked_db.return_value.get_user.return_value = None
        self.mocked_db.return_value.generate_accountid.return_value = '123'
        example_user = EXAMPLE_USER_REQUEST.copy()
        example_user['firstname'] = UNICODE_NAME
        example_user['lastname'] = SCRIPT_INJECTION_NAME
        example_user['address'] = OVERLONG_ADDRESS
        response = self.test_app.post('/users', data=example_user)
        self.assertEqual(response.status_code, 201)
        user_object = self.mocked_db.return_value.add_user.call_args[0][0]
        # unicode is preserved verbatim, markup is escaped by bleach
        self.assertEqual(user_object['firstname'], UNICODE_NAME)
        self.assertNotIn('<script>', user_object['lastname'])
        # NOTE: no upper length bound is enforced on free-text PII fields
        self.assertEqual(user_object['address'], OVERLONG_ADDRESS)

    def test_login_sql_error_500_status_code_no_credentials_echoed(self):
        """test logging in when the user lookup raises a DB error"""
        self.mocked_db.return_value.get_user.side_effect = SQLAlchemyError(
            'connection to accounts-db failed'
        )
        example_user_request = EXAMPLE_USER_REQUEST.copy()
        response = self.test_app.get('/login', query_string=example_user_request)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, b'failed to retrieve user information')
        # the submitted password must never be echoed back to the caller
        self.assertNotIn(example_user_request['password'].encode(), response.data)

    @patch('bcrypt.checkpw', return_value=True)
    def test_login_200_status_code_token_payload_excludes_sensitive_fields(self,
                                                                           _mock_checkpw):
        """test the issued JWT carries no password hash or PII beyond the user's name"""
        self.mocked_db.return_value.get_user.return_value = EXAMPLE_USER.copy()
        self.flask_app.config['PRIVATE_KEY'] = EXAMPLE_PRIVATE_KEY
        response = self.test_app.get('/login',
                                     query_string=EXAMPLE_USER_REQUEST.copy())
        self.assertEqual(response.status_code, 200)
        decoded_value = jwt.decode(algorithms='RS256',
                                   jwt=response.json['token'],
                                   key=EXAMPLE_PUBLIC_KEY)
        self.assertEqual(sorted(decoded_value.keys()),
                         ['acct', 'exp', 'iat', 'name', 'user'])
        raw_token = response.json['token']
        for secret in (EXAMPLE_USER['address'],
                       EXAMPLE_USER['passhash'].decode()):
            self.assertNotIn(secret, str(decoded_value))
            self.assertNotIn(secret, raw_token)

    def test_create_user_400_status_code_invalid_username(self,):
        """test adding a contact with invalid labels """
        # mock return value of get_user which checks if user exists as None
        self.mocked_db.return_value.get_user.return_value = None
        # mock return value for generate_id from user_db
        self.mocked_db.return_value.generate_accountid.return_value = '123'
        # test for each invalid label in INVALID_USERNAMES
        for invalid_username in INVALID_USERNAMES:
            example_user_request = EXAMPLE_USER_REQUEST.copy()
            # create example user request
            example_user_request['username'] = invalid_username
            # send request to test client
            response = self.test_app.post('/users', data=example_user_request)
            self.assertEqual(response.status_code, 400,
                             'username {} returned incorrect status code'.format(invalid_username))
            if invalid_username:
                # assert we get correct error message
                self.assertEqual(
                    response.data,
                    'username must contain 2-15 alphanumeric characters or underscores'.encode(),
                    'username {} returned unexpected error message'.format(invalid_username)
                )
