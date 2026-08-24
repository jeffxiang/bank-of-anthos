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

"""Pytest configuration for the frontend service.

Makes the flat service modules (api_call, traced_thread_pool_executor)
importable when tests are run from this directory.
"""

import os
import sys

import markupsafe

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# On pre-release CPython builds the markupsafe C speedups can raise
# SystemError; fall back to the pure-Python implementation so template
# rendering works.
try:
    markupsafe.escape('probe')
except SystemError:
    from markupsafe import _native  # pylint: disable=protected-access
    markupsafe._escape_inner = _native._escape_inner  # pylint: disable=protected-access
