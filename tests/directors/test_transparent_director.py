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

from unittest.mock import MagicMock

import pytest

from pyleco.test import FakeCommunicator
from pyleco.directors.transparent_director import TransparentDevice, TransparentDirector, RemoteCall


def get_parameters_fake(parameters):
    pars = {}
    for i, par in enumerate(parameters):
        pars[par] = i
    return pars


class FakeDirector(TransparentDirector):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.call_action = MagicMock()
        self.get_parameters = MagicMock()
        self.get_parameters.side_effect = get_parameters_fake
        self.set_parameters = MagicMock()


class FantasyDevice(TransparentDevice):
    method = RemoteCall()


@pytest.fixture
def director() -> TransparentDirector:
    director = FakeDirector(device_class=FantasyDevice,
                            communicator=FakeCommunicator(name="Communicator"))  # type: ignore
    return director


def test_get_parameters(director: TransparentDirector):
    assert director.device.getter == 0
    director.get_parameters.assert_called_once_with(parameters=("getter",))  # type: ignore


def test_set_parameters(director: TransparentDirector):
    director.device.setter = 5
    director.set_parameters.assert_called_once_with(parameters={"setter": 5})  # type: ignore


def test_method(director: TransparentDirector):
    director.device.method(5, kwarg=7)
    director.call_action.assert_called_once_with("method", 5, kwarg=7)  # type: ignore
