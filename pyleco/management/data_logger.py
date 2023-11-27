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

import datetime
try:
    from enum import StrEnum  # type: ignore
except ImportError:  # pragma: no cover
    # For python<3.11
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore
        pass
import json
import logging
from typing import Any, Callable, Optional, Iterable

try:
    import numpy as np  # type: ignore[import-not-found]
except ModuleNotFoundError:
    def average(values: list[float | int] | tuple[float | int, ...]):
        return sum(values) / len(values)
else:
    average = np.average  # type: ignore

if __name__ == "__main__":  # pragma: no cover
    from pyleco.utils.timers import RepeatingTimer
    from pyleco.utils.extended_message_handler import ExtendedMessageHandler, DataMessage
    from pyleco.utils.parser import parser, parse_command_line_parameters
    from pyleco.utils.data_publisher import DataPublisher
else:
    from ..utils.timers import RepeatingTimer
    from ..utils.extended_message_handler import ExtendedMessageHandler, DataMessage
    from ..utils.parser import parser, parse_command_line_parameters
    from ..utils.data_publisher import DataPublisher


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())
StrFormatter = logging.Formatter("%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s")

nan = float("nan")


class TriggerTypes(StrEnum):
    TIMER = "timer"
    VARIABLE = "variable"
    NONE = "none"


class ValuingModes(StrEnum):
    LAST = "last"
    AVERAGE = "average"


class DataLogger(ExtendedMessageHandler):
    """Collect data and save it to the disk, if required.

    The data logger listens to commands via the control protocol and to data via the data protocol.
    Whenever triggered, either by a timer or by receiving certain data via data protocol, it
    generates a data point.
    Each new datapoint is published via the data protocol, such that a user might follow the data
    acquisition.
    The data point contains values for each variable. The value is either the last one received
    since the last data point, or the average of all values received sind the last data point, or
    `float("nan")`.

    If desired, the datalogger may save all datapoints to disk.

    .. code::

        datalogger = DataLogger()
        datalogger.listen()  # listen until a shutdown signal is received.
        # Now you may send a "start_collecting" message to start a measurement.
    """

    # TODO names
    tmp: dict[str, list[Any]]  # contains all values since last datapoint
    lists: dict[str, list[Any]]  # contains datapoints.
    # units: dict[str, Quantity]
    last_datapoint: dict[str, Any]
    last_save_name: Optional[str]

    trigger_type: TriggerTypes = TriggerTypes.NONE
    trigger_timeout: float
    trigger_variable: str
    value_repeating: bool = False
    valuing: Callable[[list], Any]

    last_config: dict[str, Any]  # configuration for the next start

    def __init__(self, name: str = "DataLoggerN", directory: str = ".", **kwargs) -> None:
        super().__init__(name=name, **kwargs)
        self.directory = directory
        self.units: dict = {}  # TODO later
        self.last_datapoint = {}
        self.last_config = {}
        self.lists = {}
        self.publisher = DataPublisher(full_name=name)
        self.last_save_name = None
        self.valuing = average
        # TODO add auto_save functionality?

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.register_rpc_method(self.set_valuing_mode)  # offer during a measurement?
        self.register_rpc_method(self.start_collecting)
        self.register_rpc_method(self.save_data)
        self.register_rpc_method(self.stop_collecting)
        self.register_rpc_method(self.get_last_datapoint)
        self.register_rpc_method(self.get_list_length)
        self.register_rpc_method(self.get_last_save_name)
        self.register_rpc_method(self.get_configuration)
        self.register_rpc_method(self.set_configuration)  # keep that style of setting values?
        # deprecated, for backwards compatibility
        self.register_rpc_method(method=self.save_data, name="saveData")
        self.register_rpc_method(self.get_configuration, name="getConfiguration")
        self.register_rpc_method(self.set_configuration, name="setConfiguration")

    def shut_down(self) -> None:
        self.stop_collecting()
        super().shut_down()

    def __del__(self) -> None:
        self.stop_collecting()

    def _listen_setup(self, start_data: Optional[dict[str, Any]] = None,  # type: ignore[override]
                      **kwargs):
        poller = super()._listen_setup(**kwargs)
        if start_data is not None:
            self.start_collecting(**start_data)
        return poller

    def set_full_name(self, full_name: str) -> None:
        super().set_full_name(full_name=full_name)
        self.publisher.full_name = full_name

    # Data management
    def handle_subscription_message(self, data_message: DataMessage) -> None:
        sender = data_message.topic.decode()
        try:
            content: dict[str, Any] = data_message.data  # type: ignore
            modified_dict = {".".join((sender, k)): v for k, v in content.items()}
        except Exception:
            log.exception("Could not decode message {data_message}.")
        else:
            self.handle_subscription_data(modified_dict)

    def handle_subscription_data(self, data: dict[str, Any]) -> None:
        """Store `data` dict in `tmp`"""
        for key, value in data.items():
            try:
                self.tmp[key].append(value)
            except KeyError:
                log.error(f"Got value for {key}, but no list present.")
        if self.trigger_type == TriggerTypes.VARIABLE and self.trigger_variable in data.keys():
            self.make_datapoint()

    def make_datapoint(self) -> dict[str, Any]:
        """Store a datapoint."""
        datapoint = self.calculate_data()
        self.last_datapoint = datapoint
        if self.namespace is not None:
            self.publisher.send_data(data=self.last_datapoint)
        return datapoint

    def calculate_data(self) -> dict[str, Any]:
        """Calculate data for a data point and return the data point."""
        datapoint = {}
        if 'time' in self.lists.keys():
            now = datetime.datetime.now(datetime.timezone.utc)
            today = datetime.datetime.combine(self.today, datetime.time(),
                                              datetime.timezone.utc)
            time = (now - today).total_seconds()
            self.tmp['time'].append(time)
        for variable, datalist in self.lists.items():
            value = datapoint[variable] = self.calculate_single_data(variable, self.tmp[variable])
            datalist.append(value)
        for key in self.tmp.keys():
            self.tmp[key].clear()
        return datapoint

    def calculate_single_data(self, variable: str, tmp: list):
        if tmp:
            value = self.valuing(tmp)
        elif self.value_repeating:
            try:
                value = self.lists[variable][-1]
            except (KeyError, IndexError):  # No last value present.
                value = nan
        else:
            value = nan
        return value

    @staticmethod
    def last(data: list[Any]) -> Any:
        """Return the last value of an iterable with error handling."""
        try:
            return data[-1]
        except TypeError:
            return data
        except IndexError:
            # empty list
            return nan

    # Control
    def start_collecting(self, *,
                         variables: Optional[Iterable[str]] = None,
                         trigger: Optional[str | float] = None,
                         valuing_mode: Optional[ValuingModes] = None,
                         value_repeating: Optional[bool] = None,
                         ) -> None:
        """Start collecting data."""
        for key, value in zip(
            ("variables", "trigger", "valuing_mode", "value_repeating"),
            (variables, trigger, valuing_mode, value_repeating)
        ):
            if value is not None:
                self.last_config[key] = value
        self._start(**self.last_config)

    def _start(self, *,
               variables: Iterable[str],
               trigger: str | float = 1,
               valuing_mode: ValuingModes = ValuingModes.LAST,
               value_repeating: bool = False,
               ) -> None:
        self.stop_collecting()
        log.info(f"Start collecting data. Trigger: {trigger}; "
                 f"subscriptions: {variables}")
        self._set_trigger(trigger=trigger)
        self.value_repeating = value_repeating
        self.today = datetime.datetime.now(datetime.timezone.utc).date()
        self.set_valuing_mode(valuing_mode=valuing_mode)
        self.setup_variables(variables)

    def setup_variables(self, variables: Iterable[str]) -> None:
        """Subscribe to the variables."""
        self.reset_data_storage()
        subscriptions: set[str] = set()
        for variable in variables:
            if "." in variable:
                # this is the new style: topic is sender name, data is in content
                parts = variable.split(".")
                if len(parts) == 2:
                    # assume to be in the same namespace
                    parts.insert(0, self.namespace)  # type: ignore
                    variable = ".".join(parts)
                try:
                    subscriptions.add(".".join(parts[:2]))
                except TypeError:
                    # if self.namespace is None
                    log.error(f"Cannot subscribe to '{variable}' as the namespace is not known.")
            else:
                # old style: topic is variable name
                subscriptions.add(variable)
            self.lists[variable] = []
            self.tmp[variable] = []
        self.subscribe(topics=subscriptions)

    def _set_trigger(self, trigger: str | float):
        if isinstance(trigger, (float, int)):
            self.set_timeout_trigger(timeout=trigger)
        elif isinstance(trigger, str):
            self.set_variable_trigger(variable=trigger)
        else:
            self.trigger_type = TriggerTypes.NONE

    def reset_data_storage(self) -> None:
        """Reset the data storage."""
        self.tmp = {}
        self.lists = {}
        self.last_datapoint = {}

    def set_timeout_trigger(self, timeout: float) -> None:
        self.trigger_type = TriggerTypes.TIMER
        self.trigger_timeout = timeout
        self.timer = RepeatingTimer(timeout, self.make_datapoint)
        self.timer.start()

    def set_variable_trigger(self, variable: str) -> None:
        self.trigger_type = TriggerTypes.VARIABLE
        self.trigger_variable = variable

    def set_valuing_mode(self, valuing_mode: ValuingModes) -> None:
        if valuing_mode == ValuingModes.LAST:
            self.valuing = self.last
        elif valuing_mode == ValuingModes.AVERAGE:
            self.valuing = average

    def save_data(self, meta: None | dict = None, suffix: str = "", header: str = "") -> str:
        """Save the data.

        :param addr: Reply address for the filename.
        :param dict meta: The meta data to save. Use e.g. in subclass
            Protected keys: units, today, name, configuration, user.
        :param str suffix: Suffix to append to the filename.
        :return str: Name of the saved file.
        """
        # Preparation.
        if meta is None:
            meta = {}
        folder = self.directory
        # Pickle the header and lists.
        file_name = datetime.datetime.now().strftime("%Y_%m_%dT%H_%M_%S") + suffix
        meta.update({
            'units': self.units,
            'today': self.today.isoformat(),
            'file_name': file_name,
            'logger_name': self.full_name,
            'configuration': self.get_configuration(),
            # 'user': self.user_data,  # user stored meta data
        })
        try:
            with open(f"{folder}/{file_name}.json", 'w') as file:
                json.dump(obj=(header, self.lists, meta), fp=file)
        except TypeError as exc:
            log.exception("Some type error during saving occurred.", exc_info=exc)
            raise
        except PermissionError as exc:
            log.exception(f"Writing permission denied for '{folder}'.", exc_info=exc)
            raise
        else:
            # Indicate the name.
            log.info(f"Saved data to '{folder}/{file_name}'.")
            self.last_save_name = file_name
            return file_name

    def stop_collecting(self) -> None:
        """Stop the data acquisition."""
        log.info("Stopping to collect data.")
        self.trigger_type = TriggerTypes.NONE
        self.unsubscribe_all()
        try:
            self.timer.cancel()
            del self.timer
        except AttributeError:
            pass

    def get_configuration(self) -> dict[str, Any]:
        """Get the currently used configuration as a dictionary."""
        config: dict[str, Any] = {}
        # Trigger
        config['trigger'] = self.trigger_type.value
        if self.trigger_type == TriggerTypes.TIMER:
            config['triggerTimer'] = int(self.trigger_timeout * 1000)  # deprecated
            config['trigger_timeout'] = self.trigger_timeout
        elif self.trigger_type == TriggerTypes.VARIABLE:
            config['triggerVariable'] = self.trigger_variable  # deprecated
            config['trigger_variable'] = self.trigger_variable
        # Value
        config['valuing_mode'] = "last" if self.valuing == self.last else "mean"
        config['valueRepeat'] = self.value_repeating  # deprecated
        config['value_repeating'] = self.value_repeating
        # Header and Variables.
        config['variables'] = " ".join(self.lists.keys())
        # config['unitsText'] = self.leUnits.text()
        # config['autoSave'] = self.actionAutoSave.isChecked()
        return config

    def set_configuration(self, configuration: dict[str, Any]) -> None:
        """Set logging configuration according to the dict `configuration`."""
        if configuration.get('start', False) is False:
            return  # set properties only at start of new measurement.
        translated_dict = self.last_config
        if configuration.get("trigger") == "timer":
            translated_dict["trigger"] = configuration.get(
                "trigger_timeout") or configuration.get("triggerTimer")
        elif configuration.get("trigger") == "variable":
            translated_dict["trigger"] = configuration.get(
                "trigger_variable") or configuration.get("triggerVariable")
        for key, value in configuration.items():
            match key, value:  # noqa
                case 'value', 'last':
                    translated_dict["valuing_mode"] = ValuingModes.LAST
                case 'value', "mean":
                    translated_dict["valuing_mode"] = ValuingModes.AVERAGE
                case 'valueRepeat', checked:
                    translated_dict["value_repeating"] = checked
                case 'variables', value:
                    translated_dict["variables"] = value.split()
                case _:
                    pass
        # Start the logging.
        translated_dict.setdefault("trigger", 1)
        translated_dict.setdefault("variables", ["time"])
        translated_dict.setdefault("valuing_mode", ValuingModes.LAST)
        translated_dict.setdefault("value_repeating", False)
        self.start_collecting(**translated_dict)

    def get_last_datapoint(self) -> dict[str, Any]:
        """Read the last datapoint."""
        return self.last_datapoint

    def get_last_save_name(self) -> str | None:
        """Return the name of the last save."""
        return self.last_save_name

    def get_list_length(self) -> int:
        """Return the length of the lists."""
        length = len(self.lists[list(self.lists.keys())[0]]) if self.lists else 0
        return length


def main():
    """Start a datalogger at script execution."""
    parser.description = "Log data."
    parser.add_argument("-d", "--directory",
                        help="set the directory to save the data to")

    gLog = logging.getLogger()  # print all log entries!
    kwargs = parse_command_line_parameters(parser=parser, parser_description="Log data.",
                                           logger=gLog)
    if not gLog.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StrFormatter)
        gLog.addHandler(handler)

    datalogger = DataLogger(log=gLog, **kwargs)
    datalogger.listen()


if __name__ == "__main__":  # pragma: no cover
    main()
