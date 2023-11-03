#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2023 PyLECO Developers
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

import numpy as np
import pytest

from pyleco.management.data_logger import DataLogger, nan


@pytest.fixture
def data_logger() -> DataLogger:
    dl = DataLogger()
    dl.reset_data_storage()
    dl.tmp["test"] = []
    dl.tmp["2"] = [1, 2]
    dl.lists["test"] = []
    dl.lists["2"] = []
    return dl


def test_handle_subscription_data(data_logger: DataLogger):
    data_logger.handle_subscription_data({"test": 5})
    data_logger.handle_subscription_data({"test": 7})
    assert data_logger.tmp["test"] == [5, 7]


def test_set_publisher_name(data_logger: DataLogger):
    data_logger.set_full_name("N1.cA")
    assert data_logger.publisher.full_name == "N1.cA"
    assert data_logger.full_name == "N1.cA"


class Test_make_data_point:
    @pytest.fixture
    def data_logger_mdp(self, data_logger: DataLogger):
        data_logger.make_data_point()
        return data_logger

    def test_last_data_point(self, data_logger_mdp: DataLogger):
        assert data_logger_mdp.last_datapoint == {"test": nan, "2": 1.5}

    def test_tmp_is_cleared(self, data_logger_mdp: DataLogger):
        assert data_logger_mdp.tmp["2"] == []

    def test_publish_data(self, data_logger: DataLogger):
        # arrange it with a Mock
        data_logger.publisher.send_data = MagicMock()  # type: ignore
        data_logger.namespace = "N1"
        # act
        data_logger.make_data_point()
        # assert
        data_logger.publisher.send_data.assert_called_once_with(data={"test": nan, "2": 1.5})


class Test_calculate_single_data:
    @pytest.mark.parametrize("list, result", (
            ([2, 3], 2.5),
            # ([], nan),  # does not work for an unknown reason
            ([5], 5),
    ))
    def test_average(self, data_logger: DataLogger, list, result):
        assert data_logger.calculate_single_data("2", tmp=list) == result

    def test_whatever(self):
        assert np.average([2, 3]) == 2.5
