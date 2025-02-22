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

from __future__ import annotations
from typing import Union, Sequence

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
from threading import Lock
from typing import Any, Callable, Optional, Iterable

try:
    import numpy as np  # type: ignore[import-not-found]
except ModuleNotFoundError:
    def average(values: Sequence[Union[float, int]]) -> float:
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
    units: dict[str, Any]  # contains the units of the variables  TODO TBD what the value is.
    last_datapoint: dict[str, Any]
    last_save_name: str = ""

    # configuration variables
    trigger_type: TriggerTypes = TriggerTypes.NONE
    _last_trigger_type: TriggerTypes = TriggerTypes.NONE
    trigger_timeout: float = 1
    trigger_variable: str = ""
    value_repeating: bool = False
    valuing: Callable[[list], Any]

    def __init__(self, name: str = "DataLoggerN", directory: str = ".", **kwargs) -> None:
        super().__init__(name=name, **kwargs)
        self.directory = directory
        self.publisher = DataPublisher(full_name=name)
        self.valuing = average
        # Initialize values
        self.list_lock = Lock()
        self.reset_data_storage()
        self.units = {}
        # TODO add auto_save functionality?

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.register_rpc_method(self.set_valuing_mode)  # TODO offer during a measurement?
        self.register_rpc_method(self.start_collecting)
        self.register_rpc_method(self.save_data)
        self.register_rpc_method(self.stop_collecting)
        self.register_rpc_method(self.get_last_datapoint)
        self.register_rpc_method(self.get_list_length)
        self.register_rpc_method(self.get_last_save_name)
        self.register_rpc_method(self.get_configuration)

    def __del__(self) -> None:
        self.stop_collecting()

    def _listen_setup(self, start_data: Optional[dict[str, Any]] = None,  # type: ignore[override]
                      **kwargs):
        poller = super()._listen_setup(**kwargs)
        if start_data is not None:
            self.start_collecting(**start_data)
        return poller

    def _listen_close(self, waiting_time: Optional[int] = None) -> None:
        self.stop_collecting()
        super()._listen_close(waiting_time=waiting_time)

    def set_full_name(self, full_name: str) -> None:
        super().set_full_name(full_name=full_name)
        self.publisher.full_name = full_name

    # Data management
    def handle_subscription_message(self, message: DataMessage) -> None:
        sender = message.topic.decode()
        try:
            content: dict[str, Any] = message.data  # type: ignore
            modified_dict = {".".join((sender, k)): v for k, v in content.items()}
        except Exception:
            log.exception(f"Could not decode message {message}.")
        else:
            self.handle_subscription_data(modified_dict)

    def handle_subscription_data(self, data: dict[str, Any]) -> None:
        """Store `data` dict in `tmp`"""
        with self.list_lock:
            for key, value in data.items():
                try:
                    self.tmp[key].append(value)
                except KeyError:
                    log.debug("Got value for '%s', but no list present.", key)
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
        with self.list_lock:
            if 'time' in self.lists.keys():
                now = datetime.datetime.now(datetime.timezone.utc)
                today = datetime.datetime.combine(
                    self.today, datetime.time(), datetime.timezone.utc
                )
                time = (now - today).total_seconds()
                self.tmp['time'].append(time)
            for variable, datalist in self.lists.items():
                value = datapoint[variable] = self.calculate_single_data(
                    variable, self.tmp[variable]
                )
                datalist.append(value)
            for key in self.tmp.keys():
                self.tmp[key].clear()
            return datapoint

    def calculate_single_data(self, variable: str, tmp: list):
        if tmp:
            value = self.valuing(tmp)
        elif self.value_repeating:
            try:
                # no lock, as this method is called in in a locked environment!
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
                         variables: Optional[list[str]] = None,
                         units: Optional[dict[str, Any]] = None,
                         trigger_type: Optional[TriggerTypes] = None,  # TODO also str, but openrpc
                         trigger_timeout: Optional[float] = None,
                         trigger_variable: Optional[str] = None,
                         valuing_mode: Optional[ValuingModes] = None,  # TODO also str, but openrpc
                         value_repeating: Optional[bool] = None,
                         ) -> None:
        """Start collecting data.

        If you do not give a specific parameter, the value of the last measurement is used again.
        """
        self.stop_collecting()
        log.info(f"Start collecting data. Trigger: {trigger_type}, {trigger_timeout}, "
                 f"{trigger_variable}; subscriptions: {variables}")
        self.today = datetime.datetime.now(datetime.timezone.utc).date()
        self.trigger_type = TriggerTypes(trigger_type) if trigger_type else self._last_trigger_type
        self._last_trigger_type = self.trigger_type
        if trigger_timeout is not None:
            self.trigger_timeout = trigger_timeout
        if trigger_variable is not None:
            self.trigger_variable = trigger_variable
        if value_repeating is not None:
            self.value_repeating = value_repeating
        if self.trigger_type == TriggerTypes.TIMER:
            self.start_timer_trigger(timeout=self.trigger_timeout)
        self.set_valuing_mode(valuing_mode=valuing_mode)
        self.setup_variables(self.lists.keys() if variables is None else variables)
        self.units = units if units else {}

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
                    if self.namespace is None:
                        log.error(f"Cannot subscribe to '{variable}' as the namespace is not known.")  # noqa
                        continue
                    parts.insert(0, self.namespace)
                    variable = ".".join(parts)
                subscriptions.add(".".join(parts[:2]))
            else:
                # old style: topic is variable name
                subscriptions.add(variable)
            with self.list_lock:
                self.lists[variable] = []
                self.tmp[variable] = []
        self.subscribe(topics=subscriptions)

    def reset_data_storage(self) -> None:
        """Reset the data storage."""
        with self.list_lock:
            self.tmp = {}
            self.lists = {}
        self.last_datapoint = {}

    def start_timer_trigger(self, timeout: float) -> None:
        self.timer = RepeatingTimer(timeout, self.make_datapoint)
        self.timer.start()

    def set_valuing_mode(self, valuing_mode: Optional[ValuingModes]) -> None:  # also str
        if valuing_mode == ValuingModes.LAST:
            self.valuing = self.last
        elif valuing_mode == ValuingModes.AVERAGE:
            self.valuing = average
        elif valuing_mode is None:
            pass  # already setup

    def save_data(self, meta: Optional[dict] = None, suffix: str = "", header: str = "") -> str:
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
            with self.list_lock:
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
        config['trigger_type'] = self.trigger_type.value
        config['trigger_timeout'] = self.trigger_timeout
        config['trigger_variable'] = self.trigger_variable
        # Value
        vm = ValuingModes.LAST if self.valuing == self.last else ValuingModes.AVERAGE
        config['valuing_mode'] = vm.value
        config['value_repeating'] = self.value_repeating
        # Header and Variables.
        with self.list_lock:
            config['variables'] = list(self.lists.keys())
        config['units'] = self.units
        # config['autoSave'] = self.actionAutoSave.isChecked()
        return config

    def get_last_datapoint(self) -> dict[str, Any]:
        """Read the last datapoint."""
        return self.last_datapoint

    def get_last_save_name(self) -> Union[str, None]:
        """Return the name of the last save."""
        return self.last_save_name

    def get_list_length(self) -> int:
        """Return the length of the lists."""
        with self.list_lock:
            length = len(self.lists[list(self.lists.keys())[0]]) if self.lists else 0
            return length


def main() -> None:
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
