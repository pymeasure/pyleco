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

import json
from math import isnan
from pathlib import Path
import re
from unittest.mock import MagicMock

import pytest

from pyleco.core.data_message import DataMessage
from pyleco.test import FakeContext
from pyleco.management.data_logger import DataLogger, nan, ValuingModes, TriggerTypes


@pytest.fixture
def data_logger() -> DataLogger:
    dl = DataLogger(context=FakeContext())
    dl.subscriber.subscribe = MagicMock()  # type: ignore[method-assign]
    dl.subscriber.unsubscribe = MagicMock()  # type: ignore[method-assign]
    dl.start_collecting(
        variables=["time", "test", "2", "N1.sender.var"],
        trigger_type=TriggerTypes.VARIABLE,
        trigger_variable="test",
        trigger_timeout=10,
        valuing_mode=ValuingModes.AVERAGE,
        value_repeating=False,
        )
    dl.tmp["2"] = [1, 2]
    return dl


class Test_start_collecting:
    @pytest.fixture(params=[False, True])
    def data_logger_sc(self, data_logger: DataLogger, request):
        if request.param:
            # do it once without restarting and once with restarting
            data_logger.start_collecting()
        return data_logger

    def test_trigger_type(self, data_logger_sc: DataLogger):
        assert data_logger_sc.trigger_type == TriggerTypes.VARIABLE

    def test_trigger_variable(self, data_logger_sc: DataLogger):
        assert data_logger_sc.trigger_variable == "test"

    def test_trigger_timeout(self, data_logger_sc: DataLogger):
        assert data_logger_sc.trigger_timeout == 10

    def test_value_repeating(self, data_logger_sc: DataLogger):
        assert data_logger_sc.value_repeating is False

    def test_variables(self, data_logger_sc: DataLogger):
        for key in ["time", "test", "2", "N1.sender.var"]:
            assert key in data_logger_sc.lists.keys()

    def test_with_str_as_trigger_type(self, data_logger: DataLogger):
        data_logger.start_collecting(trigger_type=TriggerTypes.VARIABLE.value)  # type: ignore
        assert isinstance(data_logger.trigger_type, TriggerTypes)


def test_start_collecting_starts_timer(data_logger: DataLogger):
    # arrange
    data_logger.trigger_timeout = 1000
    # act
    data_logger.start_collecting(trigger_type=TriggerTypes.TIMER, trigger_timeout=500)
    # assert
    assert data_logger.timer.interval == 500
    # cleanup
    data_logger.timer.cancel()


def test_start_collecting_starts_timer_even_second_time(data_logger: DataLogger):
    """Even a second time, without explicit trigger type, the timer should be started."""
    # arrange
    data_logger.trigger_timeout = 500
    # first time, to set type
    data_logger.start_collecting(trigger_type=TriggerTypes.TIMER, trigger_timeout=1000)
    data_logger.stop_collecting()
    assert not hasattr(data_logger, "timer")  # no timer left
    # act
    data_logger.start_collecting()
    # assert
    assert data_logger.timer.interval == 1000
    # cleanup
    data_logger.timer.cancel()


def test_listen_close_stops_collecting(data_logger: DataLogger):
    data_logger.stop_collecting = MagicMock()  # type: ignore[method-assign]
    # act
    data_logger._listen_close()
    # assert
    data_logger.stop_collecting.assert_called_once()


def test_setup_listen_does_not_start_collecting_without_start_data(data_logger: DataLogger):
    data_logger.start_collecting = MagicMock()  # type: ignore[method-assign]
    data_logger._listen_setup()
    data_logger.start_collecting.assert_not_called()


def test_setup_listen_starts_collecting(data_logger: DataLogger):
    data_logger.start_collecting = MagicMock()  # type: ignore[method-assign]
    data_logger._listen_setup(start_data={"var": 7})
    data_logger.start_collecting.assert_called_once_with(var=7)


class Test_setup_variables:
    @pytest.fixture
    def data_logger_stv(self, data_logger: DataLogger):
        data_logger.namespace = "N1"
        data_logger.unsubscribe_all()
        data_logger.subscriber.subscribe = MagicMock()  # type: ignore[method-assign]
        data_logger.setup_variables([
            "var1",
            "N1.sender.var2", "N1.sender.var3", "sender.var4",
            "sender2.var5",
            ])
        return data_logger

    def test_just_once_subscribed_to_component(self, data_logger_stv: DataLogger):
        """Even though there are several variables from the same component
        (with or without namespace defined), only one subscriptions should be there"""
        data_logger_stv._subscriptions.remove(b"N1.sender")  # asserts that it is present
        assert b"N1.sender" not in data_logger_stv._subscriptions
        assert b"sender" not in data_logger_stv._subscriptions  # namespace is added

    def test_subscribe_to_complemented_namespace(self, data_logger_stv: DataLogger):
        """A variable name without namespace should be complemented with the namespace."""
        assert b"N1.sender2" in data_logger_stv._subscriptions

    def test_subscribe_to_simple_variable(self, data_logger_stv: DataLogger):
        assert b"var1" in data_logger_stv._subscriptions

    @pytest.mark.parametrize("var", ("N1.sender.var2", "N1.sender.var3"))
    def test_lists_for_component_variables(self, data_logger_stv: DataLogger, var):
        assert var in data_logger_stv.lists

    @pytest.mark.parametrize("var", ("N1.sender.var4", "N1.sender2.var5"))
    def test_lists_for_complemented_namespace(self, data_logger_stv: DataLogger, var):
        """If the namespace has been complemented, it should be in the lists."""
        assert var in data_logger_stv.lists


def test_subscribe_without_having_logged_in(data_logger: DataLogger,
                                            caplog: pytest.LogCaptureFixture):
    """Test that proper logging happens if the data_logger did not sign in (yet) but should
    subscribe to some remote object."""
    data_logger.namespace = None
    data_logger.setup_variables(["Component.Variable"])
    assert caplog.messages == ["Cannot subscribe to 'Component.Variable' as the namespace is not known."]  # noqa


def test_set_valuing_mode_last(data_logger: DataLogger):
    data_logger.set_valuing_mode(ValuingModes.LAST)
    assert data_logger.last == data_logger.valuing


def test_handle_subscription_message_calls_handle_data(data_logger: DataLogger):
    data_logger.handle_subscription_data = MagicMock()  # type: ignore[method-assign]
    message = DataMessage(topic="N1.sender", data={'var': 5, 'test': 7.3})
    data_logger.handle_subscription_message(message)
    data_logger.handle_subscription_data.assert_called_once_with({"N1.sender.var": 5,
                                                                  "N1.sender.test": 7.3})


def test_handle_subscription_message_adds_data_to_lists(data_logger: DataLogger):
    message = DataMessage(topic="N1.sender", data={"var": 5.6})
    data_logger.handle_subscription_message(message)
    assert data_logger.tmp["N1.sender.var"] == [5.6]


def test_handle_subscription_message_handles_broken_message(data_logger: DataLogger,
                                                            caplog: pytest.LogCaptureFixture):
    message = DataMessage(topic="N1.sender", data="not a dict")
    data_logger.handle_subscription_message(message)
    assert len(caplog.messages) == 1
    assert caplog.messages[0].startswith("Could not decode message")


def test_handle_subscription_data_without_trigger(data_logger: DataLogger):
    data_logger.trigger_variable = "not present"
    data_logger.handle_subscription_data({"test": 5})
    data_logger.handle_subscription_data({"test": 7})
    assert data_logger.tmp["test"] == [5, 7]


def test_handle_subscription_data_triggers(data_logger: DataLogger):
    data_logger.make_datapoint = MagicMock()  # type: ignore[method-assign]
    data_logger.handle_subscription_data({"test": 5})
    data_logger.make_datapoint.assert_called_once()


def test_handle_subscription_data_without_list(data_logger: DataLogger,
                                               caplog: pytest.LogCaptureFixture):
    caplog.set_level(0)
    data_logger.handle_subscription_data({'not_present': 42})
    assert caplog.messages == ["Got value for 'not_present', but no list present."]


def test_set_publisher_name(data_logger: DataLogger):
    data_logger.set_full_name("N1.cA")
    assert data_logger.publisher.full_name == "N1.cA"
    assert data_logger.full_name == "N1.cA"


class Test_start_timer_trigger:
    @pytest.fixture
    def data_logger_stt(self, data_logger: DataLogger):
        data_logger.start_timer_trigger(1000)
        yield data_logger
        data_logger.timer.cancel()

    def test_timer_interval(self, data_logger_stt: DataLogger):
        assert data_logger_stt.timer.interval == 1000

    def test_timer_started(self, data_logger_stt: DataLogger):
        with pytest.raises(RuntimeError):  # can start a timer at most once
            data_logger_stt.timer.start()


class Test_make_data_point:
    @pytest.fixture
    def data_logger_mdp(self, data_logger: DataLogger):
        del data_logger.lists['time']  # for better comparison
        data_logger.make_datapoint()
        return data_logger

    def test_last_data_point(self, data_logger_mdp: DataLogger):
        assert data_logger_mdp.last_datapoint == {"test": nan, "2": 1.5, "N1.sender.var": nan}

    def test_tmp_is_cleared(self, data_logger_mdp: DataLogger):
        assert data_logger_mdp.tmp["2"] == []

    def test_publish_data(self, data_logger: DataLogger):
        # arrange it with a Mock
        data_logger.publisher.send_data = MagicMock()  # type: ignore[method-assign]
        del data_logger.lists["time"]

        data_logger.namespace = "N1"
        # act
        data_logger.make_datapoint()
        # assert
        data_logger.publisher.send_data.assert_called_once_with(data={"test": nan, "2": 1.5,
                                                                      "N1.sender.var": nan})


def test_calculate_data_adds_time(data_logger: DataLogger):
    datapoint = data_logger.calculate_data()
    assert datapoint["time"] > 0


class Test_calculate_single_data:
    @pytest.mark.parametrize("list, result", (
            ([2, 3], 2.5),
            ([5], 5),
    ))
    def test_average(self, data_logger: DataLogger, list, result):
        assert data_logger.calculate_single_data("2", tmp=list) == result

    def test_average_results_in_nan(self, data_logger: DataLogger):
        assert isnan(data_logger.calculate_single_data("2", tmp=[]))

    @pytest.mark.parametrize("list, result", (
            ([2, 3], 3),
            ([5], 5),
    ))
    def test_last(self, data_logger: DataLogger, list, result):
        data_logger.valuing = data_logger.last
        assert data_logger.calculate_single_data("2", tmp=list) == result

    def test_last_results_in_nan(self, data_logger: DataLogger):
        data_logger.valuing = data_logger.last
        assert isnan(data_logger.calculate_single_data("2", tmp=[]))

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

    def test_repeating_without_last_value_results_in_nan(self, data_logger: DataLogger):
        data_logger.value_repeating = True
        data_logger.lists["2"] = []
        assert isnan(data_logger.calculate_single_data("2", tmp=[]))


class Test_last:
    def test_last_returns_last_value(self, data_logger: DataLogger):
        assert data_logger.last([1, 2, 3, 4, 5]) == 5

    def test_return_single_value(self, data_logger: DataLogger):
        assert data_logger.last(5) == 5  # type: ignore

    def test_empty_list_returns_nan(self, data_logger: DataLogger):
        assert isnan(data_logger.last([]))


class Test_save_data:
    @pytest.fixture
    def data_logger_sd(self, data_logger: DataLogger, tmp_path_factory: pytest.TempPathFactory):
        path = tmp_path_factory.mktemp("save")
        data_logger.directory = str(path)
        self.file_name = data_logger.save_data()
        self.today = data_logger.today
        return data_logger

    def test_filename(self, data_logger_sd: DataLogger):
        result = re.match(r"20\d\d_\d\d_\d\dT\d\d_\d\d_\d\d", data_logger_sd.last_save_name)
        assert result is not None

    @pytest.fixture
    def saved_file(self, data_logger_sd: DataLogger):
        path = Path(data_logger_sd.directory) / data_logger_sd.last_save_name
        return path.with_suffix(".json").read_text()

    def test_output(self, saved_file: str):
        today_string = self.today.isoformat()
        assert saved_file == "".join(
            (
                """["", {"time": [], "test": [], "2": [], "N1.sender.var": []}, """,
                '''{"units": {}, "today": "''',
                today_string,
                '''", "file_name": "''',
                self.file_name,
                """", "logger_name": "DataLoggerN", """,
                """"configuration": {"trigger_type": "variable", "trigger_timeout": 10, """,
                """"trigger_variable": "test", "valuing_mode": "average", """,
                """"value_repeating": false, """,
                """"variables": ["time", "test", "2", "N1.sender.var"], """,
                """"units": {}}}]""",
            )
        )

    def test_json_content(self, saved_file: str):
        today_string = self.today.isoformat()
        assert json.loads(saved_file) == [
            "",
            {"time": [], "test": [], "2": [], "N1.sender.var": []},
            {"units": {}, "today": today_string, "file_name": self.file_name,
             "logger_name": "DataLoggerN",
             "configuration": {"trigger_type": "variable", "trigger_timeout": 10,
                               "trigger_variable": "test", "valuing_mode": "average",
                               "value_repeating": False,
                               "variables": ["time", "test", "2", "N1.sender.var"],
                               "units": {},
                               },
             },
            ]


def test_get_configuration(data_logger: DataLogger):
    config = data_logger.get_configuration()
    assert config == {
        "trigger_type": TriggerTypes.VARIABLE,
        "trigger_variable": "test",
        "trigger_timeout": 10,
        "valuing_mode": "average",
        "value_repeating": False,
        "variables": ["time", "test", "2", "N1.sender.var"],
        "units": {},
        }


def test_get_last_datapoint(data_logger: DataLogger):
    data_logger.last_datapoint = {"key": "value"}
    assert data_logger.get_last_datapoint() == data_logger.last_datapoint


def test_get_last_save_name(data_logger: DataLogger):
    data_logger.last_save_name = "abcef"
    assert data_logger.get_last_save_name() == data_logger.last_save_name


def test_get_list_length(data_logger: DataLogger):
    data_logger.lists = {"abc": [0, 1, 2, 3, 4]}
    assert data_logger.get_list_length() == 5
