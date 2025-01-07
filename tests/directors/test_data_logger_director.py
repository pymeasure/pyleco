#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2025 PyLECO Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

from inspect import getfullargspec

import pytest

from pyleco.test import FakeDirector
from pyleco.management.data_logger import DataLogger
from pyleco.directors.data_logger_director import DataLoggerDirector


class FakeDataLoggerDirector(FakeDirector, DataLoggerDirector):
    """Replaces the ask_rpc method."""


@pytest.fixture
def data_logger_director():
    data_logger_director = FakeDataLoggerDirector(remote_class=DataLogger)
    return data_logger_director


def test_start_collecting_signature():
    orig_spec = getfullargspec(DataLogger.start_collecting)
    dir_spec = getfullargspec(DataLoggerDirector.start_collecting)
    assert orig_spec == dir_spec


@pytest.mark.parametrize("method", ("save_data", "start_collecting", "stop_collecting",
                                    "save_data_async", "get_last_datapoint"
                                    ))
def test_method_call_existing_remote_methods(data_logger_director: FakeDataLoggerDirector, method):
    data_logger_director.return_value = None
    getattr(data_logger_director, method)()
    # asserts that no error is raised in the "ask_rpc" method
