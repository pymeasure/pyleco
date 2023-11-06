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

from pyleco.management.data_logger import DataLogger, nan, ValuingModes


@pytest.fixture
def data_logger() -> DataLogger:
    dl = DataLogger()
    dl.subscribe = MagicMock()
    dl.unsubscribe_all = MagicMock()
    dl.start_collecting(
        subscriptions=["time", "test", "2"],
        trigger="test",
        valuing_mode=ValuingModes.AVERAGE,
        value_repeating=False,
        )
    dl.tmp["2"] = [1, 2]
    return dl


def _setup_listen_does_not_start_collecting_without_start_data(data_logger: DataLogger):
    data_logger.start_collecting = MagicMock()
    data_logger._listen_setup()
    data_logger.start_collecting.assert_not_called()


def _setup_listen_starts_collecting(data_logger: DataLogger):
    data_logger.start_collecting = MagicMock()
    data_logger._listen_setup(start_data={"2": 7})
    data_logger.start_collecting.assert_called_once_with(start_data={"2": 7})


def test_handle_subscription_data_without_trigger(data_logger: DataLogger):
    data_logger.trigger_variable = "not present"
    data_logger.handle_subscription_data({"test": 5})
    data_logger.handle_subscription_data({"test": 7})
    assert data_logger.tmp["test"] == [5, 7]


def test_handle_subscription_data_triggers(data_logger: DataLogger):
    data_logger.make_data_point = MagicMock()
    data_logger.handle_subscription_data({"test": 5})
    data_logger.make_data_point.assert_called_once()


def test_set_publisher_name(data_logger: DataLogger):
    data_logger.set_full_name("N1.cA")
    assert data_logger.publisher.full_name == "N1.cA"
    assert data_logger.full_name == "N1.cA"


class Test_make_data_point:
    @pytest.fixture
    def data_logger_mdp(self, data_logger: DataLogger):
        del data_logger.lists['time']  # for better comparison
        data_logger.make_data_point()
        return data_logger

    def test_last_data_point(self, data_logger_mdp: DataLogger):
        assert data_logger_mdp.last_datapoint == {"test": nan, "2": 1.5}

    def test_tmp_is_cleared(self, data_logger_mdp: DataLogger):
        assert data_logger_mdp.tmp["2"] == []

    def test_publish_data(self, data_logger: DataLogger):
        # arrange it with a Mock
        data_logger.publisher.send_data = MagicMock()  # type: ignore[method-assign]
        del data_logger.lists["time"]

        data_logger.namespace = "N1"
        # act
        data_logger.make_data_point()
        # assert
        data_logger.publisher.send_data.assert_called_once_with(data={"test": nan, "2": 1.5})


def calculate_data_adds_time(data_logger: DataLogger):
    datapoint = data_logger.calculate_data()
    assert datapoint["time"][0] > 0


class Test_calculate_single_data:
    @pytest.mark.parametrize("list, result", (
            ([2, 3], 2.5),
            ([5], 5),
    ))
    def test_average(self, data_logger: DataLogger, list, result):
        assert data_logger.calculate_single_data("2", tmp=list) == result

    def test_average_results_in_nan(self, data_logger: DataLogger):
        assert np.isnan(data_logger.calculate_single_data("2", tmp=[]))

    @pytest.mark.parametrize("list, result", (
            ([2, 3], 3),
            ([5], 5),
    ))
    def test_last(self, data_logger: DataLogger, list, result):
        data_logger.valuing = data_logger.last
        assert data_logger.calculate_single_data("2", tmp=list) == result

    def test_last_results_in_nan(self, data_logger: DataLogger):
        data_logger.valuing = data_logger.last
        assert np.isnan(data_logger.calculate_single_data("2", tmp=[]))

    @pytest.mark.parametrize("list, result", (
            ([2, 3], 2.5),
            ([], 55),
            ([5], 5),
    ))
    def test_repeating_with_last_value(self, data_logger: DataLogger, list, result):
        data_logger.value_repeating = True
        data_logger.lists["2"] = [55]
        assert data_logger.calculate_single_data("2", tmp=list) == result

    @pytest.mark.parametrize("list, result", (
            ([2, 3], 2.5),
            ([5], 5),
    ))
    def test_repeating_without_last_value(self, data_logger: DataLogger, list, result):
        data_logger.value_repeating = True
        data_logger.lists["2"] = []
        assert data_logger.calculate_single_data("2", tmp=list) == result

    def test_reapeating_without_last_value_results_in_nan(self, data_logger: DataLogger):
        data_logger.value_repeating = True
        data_logger.lists["2"] = []
        assert np.isnan(data_logger.calculate_single_data("2", tmp=[]))


class Test_last:
    def test_last_returns_last_value(self, data_logger: DataLogger):
        assert data_logger.last([1, 2, 3, 4, 5]) == 5

    def test_empty_list_returns_nan(self, data_logger: DataLogger):
        assert np.isnan(data_logger.last([]))
