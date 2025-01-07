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

import pytest

from pyleco.test import FakeDirector
from pyleco.management.starter import Starter
from pyleco.directors.starter_director import StarterDirector


class FakeStarterDirector(FakeDirector, StarterDirector):
    """Replaces the ask_rpc method."""


@pytest.fixture
def starter_director() -> StarterDirector:
    data_logger_director = FakeStarterDirector(remote_class=Starter)
    return data_logger_director


@pytest.mark.parametrize("method", ("start_tasks", "restart_tasks", "stop_tasks", "install_tasks",
                                    "status_tasks", "list_tasks",
                                    ))
def test_method_call_existing_remote_methods(starter_director: FakeStarterDirector, method):
    starter_director.return_value = None
    getattr(starter_director, method)("task_name")
    # asserts that no error is raised in the "ask_rpc" method
