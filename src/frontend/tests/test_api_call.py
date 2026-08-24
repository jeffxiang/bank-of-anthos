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
Tests for api_call and traced_thread_pool_executor helpers
"""

import unittest
from unittest.mock import MagicMock, patch

from opentelemetry import context as otel_context
from opentelemetry import trace
from requests.exceptions import RequestException

from api_call import ApiCall, ApiRequest
from traced_thread_pool_executor import TracedThreadPoolExecutor


class TestApiCall(unittest.TestCase):
    """Tests cases for ApiCall"""

    def setUp(self):
        self.logger = MagicMock()
        self.api_request = ApiRequest(url='http://backend.test/endpoint',
                                      headers={'Authorization': 'Bearer token'},
                                      timeout=4)
        self.api_call = ApiCall(display_name='balance',
                                api_request=self.api_request,
                                logger=self.logger)

    @patch('api_call.get')
    def test_make_call_returns_response(self, mock_get):
        """test a successful call returns the backend response"""
        expected = MagicMock()
        mock_get.return_value = expected
        response = self.api_call.make_call()
        self.assertIs(response, expected)
        mock_get.assert_called_once_with(url=self.api_request.url,
                                         headers=self.api_request.headers,
                                         timeout=self.api_request.timeout)
        self.logger.error.assert_not_called()

    @patch('api_call.get')
    def test_make_call_error_returns_none_and_logs(self, mock_get):
        """test an unreachable backend returns None and logs the error"""
        mock_get.side_effect = RequestException('backend down')
        response = self.api_call.make_call()
        self.assertIsNone(response)
        self.logger.error.assert_called_once()


class TestTracedThreadPoolExecutor(unittest.TestCase):
    """Tests cases for TracedThreadPoolExecutor"""

    def test_submit_without_otel_context_runs_function(self):
        """test tasks run when no otel context is active"""
        tracer = trace.get_tracer(__name__)
        with patch.object(otel_context, 'get_current', return_value=None):
            with TracedThreadPoolExecutor(tracer, max_workers=1) as executor:
                future = executor.submit(lambda x: x + 1, 1)
                self.assertEqual(future.result(), 2)

    def test_submit_with_otel_context_propagates_context(self):
        """test tasks run with the caller's otel context attached"""
        tracer = trace.get_tracer(__name__)
        context = otel_context.set_value('test-key', 'test-value')
        token = otel_context.attach(context)
        try:
            with TracedThreadPoolExecutor(tracer, max_workers=1) as executor:
                future = executor.submit(
                    lambda: otel_context.get_value('test-key'))
                self.assertEqual(future.result(), 'test-value')
        finally:
            otel_context.detach(token)
