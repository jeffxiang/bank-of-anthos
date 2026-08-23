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
Tests for the backend API call helpers used by frontend
"""

import logging
import unittest
from unittest.mock import MagicMock, patch

from requests.exceptions import RequestException

from api_call import ApiCall, ApiRequest
from traced_thread_pool_executor import TracedThreadPoolExecutor

EXAMPLE_URL = 'http://balancereader:8080/balances/1011226111'
EXAMPLE_HEADERS = {'Authorization': 'Bearer synthetic-token'}
EXAMPLE_TIMEOUT = 4


class TestApiCall(unittest.TestCase):
    """
    Test cases for ApiCall
    """

    def setUp(self):
        """Setup an ApiCall against a fake backend"""
        self.api_call = ApiCall(display_name='balance',
                                api_request=ApiRequest(url=EXAMPLE_URL,
                                                       headers=EXAMPLE_HEADERS,
                                                       timeout=EXAMPLE_TIMEOUT),
                                logger=MagicMock())

    @patch('api_call.get')
    def test_make_call_returns_backend_response(self, mock_get):
        """test a successful call returns the backend response"""
        response = self.api_call.make_call()
        self.assertEqual(response, mock_get.return_value)
        self.assertEqual(mock_get.call_args.kwargs['url'], EXAMPLE_URL)
        self.assertEqual(mock_get.call_args.kwargs['headers'], EXAMPLE_HEADERS)
        self.assertEqual(mock_get.call_args.kwargs['timeout'], EXAMPLE_TIMEOUT)

    @patch('api_call.get', side_effect=RequestException('backend down'))
    def test_make_call_returns_none_when_backend_unreachable(self, _mock_get):
        """test an unreachable backend yields no response and is logged"""
        self.assertIsNone(self.api_call.make_call())
        self.assertIn('Error getting %s: %s',
                      self.api_call.logger.error.call_args[0])

    @patch('api_call.get', side_effect=ValueError('bad json'))
    def test_make_call_returns_none_on_invalid_response(self, _mock_get):
        """test an invalid backend response yields no response"""
        self.assertIsNone(self.api_call.make_call())
        self.api_call.logger.error.assert_called_once()


class TestTracedThreadPoolExecutor(unittest.TestCase):
    """
    Test cases for TracedThreadPoolExecutor
    """

    def test_submit_runs_task_with_current_context(self):
        """test a submitted task runs and returns its result"""
        with TracedThreadPoolExecutor(logging.getLogger(), max_workers=1) as executor:
            future = executor.submit(lambda value: value * 2, 21)
            self.assertEqual(future.result(), 42)

    @patch('traced_thread_pool_executor.otel_context')
    def test_submit_propagates_context_to_worker(self, mock_context):
        """test the current context is attached inside the worker task"""
        mock_context.get_current.return_value = {'trace': 'context'}
        with TracedThreadPoolExecutor(logging.getLogger(), max_workers=1) as executor:
            future = executor.submit(lambda value: value * 2, 21)
            self.assertEqual(future.result(), 42)
        mock_context.attach.assert_called_once_with({'trace': 'context'})

    @patch('traced_thread_pool_executor.otel_context')
    def test_with_otel_context_attaches_context_and_runs_function(self, mock_context):
        """test with_otel_context attaches the context before running the task"""
        executor = TracedThreadPoolExecutor(logging.getLogger(), max_workers=1)
        result = executor.with_otel_context({'trace': 'context'}, lambda: 42)
        executor.shutdown()
        self.assertEqual(result, 42)
        mock_context.attach.assert_called_once_with({'trace': 'context'})

    @patch('traced_thread_pool_executor.otel_context')
    def test_submit_runs_task_without_context(self, mock_context):
        """test a submitted task runs when there is no context to propagate"""
        mock_context.get_current.return_value = None
        with TracedThreadPoolExecutor(logging.getLogger(), max_workers=1) as executor:
            future = executor.submit(lambda value: value + 1, 41)
            self.assertEqual(future.result(), 42)
        mock_context.attach.assert_not_called()
