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
from sqlalchemy.exc import OperationalError, SQLAlchemyError
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

    def _assert_no_pii_or_token(self, body, extra=()):
        """assert a response body leaks no PII, credentials or token material"""
        haystack = body.decode(errors='ignore').lower()
        secrets = [
            EXAMPLE_USER_REQUEST['ssn'],
            EXAMPLE_USER_REQUEST['password'],
            EXAMPLE_USER_REQUEST['birthday'],
            EXAMPLE_USER_REQUEST['address'],
            EXAMPLE_PRIVATE_KEY.decode(),
            'token',
        ]
        secrets.extend(extra)
        for secret in secrets:
            self.assertNotIn(secret.lower(), haystack)

    @unittest.expectedFailure
    def test_create_user_whitespace_only_pii_400_status_code_error_message(self):
        """whitespace-only PII values should be rejected as missing values

        Marked as an expected failure: the validator's
        `not bool(req[f] or req[f].strip())` check treats a whitespace-only
        value as present, so fields such as ssn are stored verbatim.
        """
        self.mocked_db.return_value.get_user.return_value = None
        self.mocked_db.return_value.generate_accountid.return_value = '123'
        for field in ('ssn', 'firstname', 'lastname', 'address', 'state', 'zip'):
            example_user = EXAMPLE_USER_REQUEST.copy()
            example_user[field] = '   '
            response = self.test_app.post('/users', data=example_user)
            self.assertEqual(response.status_code, 400,
                             'whitespace-only {} was accepted'.format(field))
            self.assertEqual(response.data, b'missing value for input field(s)')

    def test_create_user_db_lookup_error_500_status_code_no_pii_leak(self):
        """test the user-exists lookup failing returns a generic 500"""
        self.mocked_db.return_value.get_user.side_effect = SQLAlchemyError(
            'connection to accounts-db failed for user jdoe ssn 123'
        )
        with self.assertLogs(self.flask_app.logger, level='ERROR') as logs:
            response = self.test_app.post('/users', data=EXAMPLE_USER_REQUEST.copy())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, b'failed to create user')
        self._assert_no_pii_or_token(response.data)
        self.assertNotIn(EXAMPLE_USER_REQUEST['password'], '\n'.join(logs.output))

    def test_login_db_error_500_status_code_no_pii_leak(self):
        """test a DB failure during login returns a generic 500"""
        self.mocked_db.return_value.get_user.side_effect = SQLAlchemyError()
        self.flask_app.config['PRIVATE_KEY'] = EXAMPLE_PRIVATE_KEY
        response = self.test_app.get('/login', query_string=EXAMPLE_USER_REQUEST.copy())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, b'failed to retrieve user information')
        self._assert_no_pii_or_token(response.data)

    def test_login_missing_parameter_no_token_returned(self):
        """test login without a username or password parameter fails closed"""
        self.mocked_db.return_value.get_user.return_value = EXAMPLE_USER.copy()
        self.flask_app.config['PRIVATE_KEY'] = EXAMPLE_PRIVATE_KEY
        for query_string in ({'password': 'pwd'}, {'username': 'jdoe'}, {}):
            # the missing parameter is never sanitized into a lookup or a token
            with self.assertRaises(TypeError):
                self.test_app.get('/login', query_string=query_string)
            self.mocked_db.return_value.get_user.assert_not_called()

    @patch('bcrypt.checkpw', return_value=True)
    def test_login_jwt_signing_key_invalid_no_token_returned(self, _mock_checkpw):
        """test an unusable signing key aborts login instead of issuing a token"""
        self.mocked_db.return_value.get_user.return_value = EXAMPLE_USER.copy()
        self.flask_app.config['PRIVATE_KEY'] = 'not-a-private-key'
        with self.assertRaises(jwt.exceptions.InvalidKeyError) as err_ctx:
            self.test_app.get('/login', query_string=EXAMPLE_USER_REQUEST.copy())
        # the failure must not echo the key material back out
        self.assertNotIn('not-a-private-key', str(err_ctx.exception))

    @patch('userservice.userservice.jwt.encode',
           side_effect=jwt.exceptions.PyJWTError('signing backend unavailable'))
    @patch('bcrypt.checkpw', return_value=True)
    def test_login_jwt_encode_error_no_token_returned(self, _mock_checkpw, mock_encode):
        """test a signing failure is not swallowed into a 200 with an empty token"""
        self.mocked_db.return_value.get_user.return_value = EXAMPLE_USER.copy()
        self.flask_app.config['PRIVATE_KEY'] = EXAMPLE_PRIVATE_KEY
        with self.assertRaises(jwt.exceptions.PyJWTError):
            self.test_app.get('/login', query_string=EXAMPLE_USER_REQUEST.copy())
        # the signed payload never carries the password or ssn
        payload = mock_encode.call_args[0][0]
        self.assertEqual(
            sorted(payload.keys()), ['acct', 'exp', 'iat', 'name', 'user']
        )

    def test_create_app_db_connection_failure_exits(self):
        """test a failed database connection aborts startup"""
        with patch('userservice.userservice.open', mock_open(read_data='foo')):
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
                with patch('userservice.userservice.UserDb',
                           side_effect=OperationalError('stmt', {}, Exception())):
                    with self.assertRaises(SystemExit) as exit_ctx:
                        create_app()
        self.assertEqual(exit_ctx.exception.code, 1)

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
