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

import logging

import pytest

from pyleco.utils.log_levels import get_leco_log_level, LogLevels, PythonLogLevels


@pytest.mark.parametrize("level, value", (
    (logging.DEBUG, LogLevels.DEBUG),
    (logging.INFO, LogLevels.INFO),
    (logging.WARNING, LogLevels.WARNING),
    (logging.ERROR, LogLevels.ERROR),
    (logging.CRITICAL, LogLevels.CRITICAL),
))
def test_get_leco_log_level(level, value):
    assert get_leco_log_level(level) == value


def test_failing_get_leco_log_level():
    with pytest.raises(ValueError):
        get_leco_log_level(5)


def test_PythonLogLevels():
    assert PythonLogLevels["DEBUG"] == logging.DEBUG
