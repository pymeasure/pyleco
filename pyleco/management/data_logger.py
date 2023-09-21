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
from enum import StrEnum, auto
import json
import logging
from typing import Any, Callable

import numpy as np

if __name__ == "__main__":
    from pyleco.utils.timers import RepeatingTimer
    from pyleco.utils.extended_message_handler import ExtendedMessageHandler
    from pyleco.utils.parser import parser
else:
    from ..utils.timers import RepeatingTimer
    from ..utils.extended_message_handler import ExtendedMessageHandler
    from ..utils.parser import parser


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())
StrFormatter = logging.Formatter("%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s")


class TriggerTypes(StrEnum):
    TIMER = auto()
    VARIABLE = auto()
    NONE = auto()


class ValuingModes(StrEnum):
    LAST = auto()
    AVERAGE = auto()


class DataLogger(ExtendedMessageHandler):
    """Collect data and save it to the disk, if required.

    The data logger listens to commands via the control protocol and to data via the data protocol.
    Whenever triggered, either by a timer or by receiving certain data, it generates a data point.
    The data point contains values for each variable. The value is either the last one received
    since the last data point, or the average of all values received sind the last data point.

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

    trigger_type: TriggerTypes = TriggerTypes.NONE
    trigger_value: None | str | int = None
    repeating: bool = False
    valuing: Callable[[list], Any] = np.average

    next_config: dict[str, Any]  # configuration for the next start

    def __init__(self, name: str = "DataLoggerN", directory: str = ".", **kwargs) -> None:
        super().__init__(name=name, **kwargs)
        self.directory = directory
        self.units: dict = {}  # TODO later
        self.last_datapoint = {}
        self.next_config = {}
        self.lists = {}

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.rpc.method()(self.start_collecting)
        self.rpc.method()(self.set_trigger)  # offer during a measurement?
        self.rpc.method()(self.set_valuing_mode)
        self.rpc.method()(self.get_last_datapoint)
        self.rpc.method()(self.saveData)
        self.rpc.method()(self.getConfiguration)
        self.rpc.method()(self.setConfiguration)
        self.rpc.method()(self.get_list_length)

    def shut_down(self) -> None:
        self.stop()
        super().shut_down()

    def __del__(self) -> None:
        self.stop()

    # Data management
    def handle_subscription_data(self, data: dict) -> None:
        """Store `data` dict in `tmp`"""
        for key, value in data.items():
            try:
                self.tmp[key].append(value)
            except KeyError:
                log.error(f"Got value for {key}, but no list present.")
        if self.trigger_type == TriggerTypes.VARIABLE and self.trigger_value in data.keys():
            self.make_data_point()

    def make_data_point(self) -> None:
        """Store a datapoint."""
        datapoint = self.calculateData()
        self.last_datapoint = datapoint
        # TODO send datapoint to subscribers

    def get_last_datapoint(self) -> dict[str, Any]:
        """Read the last datapoint."""
        return self.last_datapoint

    def calculateData(self) -> dict[str, Any]:
        """Calculate data for a data point and return the data point."""
        datapoint = {}
        if 'time' in self.lists.keys():
            now = datetime.datetime.now(datetime.timezone.utc)
            today = datetime.datetime.combine(self.today, datetime.time(),
                                              datetime.timezone.utc)
            time = (now - today).total_seconds()
            self.tmp['time'].append(time)
        if self.repeating:
            for variable, datalist in self.lists.items():
                if self.tmp[variable]:
                    value = self.valuing(self.tmp[variable])
                else:
                    try:
                        value = self.lists[variable][-1]
                    except IndexError:  # No last value present.
                        value = np.nan
                datalist.append(value)
                datapoint[variable] = value
        else:
            for variable, datalist in self.lists.items():
                if self.tmp[variable]:
                    value = self.valuing(self.tmp[variable])
                else:
                    value = np.nan
                datalist.append(value)
                datapoint[variable] = value
        for key in self.tmp.keys():
            self.tmp[key].clear()
        return datapoint

    @staticmethod
    def last(data: list[Any]) -> Any:
        """Return the last value of an iterable with error handling."""
        try:
            return data[-1]
        except TypeError:
            return data
        except IndexError:
            return np.nan

    # Control
    def start_collecting(self, *,
                         trigger_type: TriggerTypes = TriggerTypes.TIMER,
                         trigger_value: str | int = 1000,
                         subscriptions: list[str] = [],
                         valuing_mode: ValuingModes = ValuingModes.LAST,
                         repeating: bool = False,
                         ) -> None:
        """Start collecting data."""
        log.info(f"Start collecting data. Trigger: {trigger_type}, {trigger_value}; "
                 f"subscriptions: {subscriptions}")
        self.unsubscribe_all()
        self.set_trigger(trigger_type=trigger_type, trigger_value=trigger_value)

        self.repeating = repeating
        self.today = datetime.datetime.now(datetime.timezone.utc).date()
        self.set_valuing_mode(valuing_mode=valuing_mode)

        self.reset_data_storage()
        for variable in subscriptions:
            self.lists[variable] = []
            self.tmp[variable] = []

        self.subscribe(topics=subscriptions)

    def reset_data_storage(self) -> None:
        """Reset the data storage."""
        self.tmp = {}
        self.lists = {}
        self.last_datapoint = {}

    def set_trigger(self, trigger_type: TriggerTypes, trigger_value: None | str | int) -> None:
        self.trigger_type = trigger_type
        self.trigger_value = trigger_value
        if trigger_type == TriggerTypes.TIMER:
            self.timer = RepeatingTimer(trigger_value / 1000, self.make_data_point)
            self.timer.start()
        pass  # TODO modify triggering (timer or such), if allowed during a measurement

    def set_valuing_mode(self, valuing_mode: ValuingModes) -> None:
        if valuing_mode == ValuingModes.LAST:
            self.valuing = self.last
        elif valuing_mode == ValuingModes.AVERAGE:
            self.valuing = np.average

    def saveData(self, meta: None | dict = None, suffix: str = "", header: str = "") -> str:
        """Save the data.

        :param addr: Reply address for the filename.
        :param dict meta: The meta data to save. Use e.g. in subclass
            Protected keys: units, today, name, configuration, user.
        :param str suffix: Suffix to append to the filename.
        """
        # Preparation.
        if meta is None:
            meta = {}
        folder = self.directory
        # Pickle the header and lists.
        name = datetime.datetime.now().strftime("%Y_%m_%dT%H_%M_%S") + suffix
        meta.update({
            'units': {parameter: f"{units:~P}" for parameter, units in self.units.items()},
            'today': self.today.isoformat(),
            'name': name,
            'configuration': self.getConfiguration(),
            # 'user': self.user_data,  # user stored meta data
        })
        try:
            with open(f"{folder}/{name}.json", 'w') as file:
                json.dump(obj=(header, self.lists, meta), fp=file)
        except TypeError as exc:
            log.exception("Some type error during saving occurred.", exc_info=exc)
            raise
        except PermissionError as exc:
            log.exception(f"Writing permission denied for '{folder}'.", exc_info=exc)
            raise
        else:
            # Indicate the name.
            log.info(f"Saved data to '{folder}/{name}'.")
            return name

    def stop(self) -> None:
        """Stop the data acquisition."""
        log.info("Stopping to collect data.")
        self.trigger_type = TriggerTypes.NONE
        try:
            self.timer.cancel()
            del self.timer
        except AttributeError:
            pass

    def getConfiguration(self) -> dict[str, Any]:
        """Get the currently used configuration as a dictionary."""
        config = {}
        # Trigger
        config['trigger'] = self.trigger_type.value
        config['triggerValue'] = self.trigger_value
        # Value
        config['value'] = "last" if self.valuing == self.last else "mean"
        config['valueRepeat'] = self.repeating
        # Header and Variables.
        config['variables'] = " ".join(self.lists.keys())
        # config['unitsText'] = self.leUnits.text()
        # config['autoSave'] = self.actionAutoSave.isChecked()
        return config

    def setConfiguration(self, configuration: dict[str, Any]) -> None:
        """Set logging configuration according to the dict `configuration`."""
        translated_dict = self.next_config
        for key, value in configuration.items():
            match key, value:  # noqa
                # case 'trigger', "none":
                #     self.actionPause.setChecked(True)
                case 'trigger', "timer":
                    translated_dict["trigger_type"] = TriggerTypes.TIMER
                case 'trigger', "variable":
                    translated_dict["trigger_type"] = TriggerTypes.VARIABLE
                case 'triggerTimer', value:
                    translated_dict["trigger_value"] = value
                case 'triggerVariable', value:
                    translated_dict["trigger_value"] = value
                case 'value', 'last':
                    translated_dict["valuing_mode"] = ValuingModes.LAST
                case 'value', "mean":
                    translated_dict["valuing_mode"] = ValuingModes.AVERAGE
                case 'valueRepeat', checked:
                    translated_dict["repeating"] = checked
                # case 'header', value:
                #     self.leHeader.setPlainText(value)
                case 'variables', value:
                    translated_dict["subscriptions"] = value.split()
                # case 'unitsText', text:
                #     self.leUnits.setText(text)
                # case 'meta', content:
                #     self.user_data = content
                # case 'autoSaveInterval', content:
                #     self.auto_save_timer.setInterval(content * 60 * 1000)  # min to ms
                #     settings.setValue('autoSaveInterval', content)
                # case 'autoSave', content:
                #     self.actionAutoSave.setChecked(content)
                # case 'pause', checked:
                #     self.actionPause.setChecked(checked)
                case _:
                    pass
        # Start the logging.
        if configuration.get('start', False):
            translated_dict.setdefault("trigger_type", TriggerTypes.TIMER)
            translated_dict.setdefault("trigger_value", 1000)
            translated_dict.setdefault("subscriptions", ["time"])
            translated_dict.setdefault("valuing_mode", ValuingModes.LAST)
            translated_dict.setdefault("repeating", False)
            self.start_collecting(**translated_dict)

    def get_list_length(self) -> int:
        """Return the length of the lists."""
        length = len(self.lists[list(self.lists.keys())[0]]) if self.lists else 0
        return length


if __name__ == "__main__":
    parser.description = "Log data."
    parser.add_argument("-d", "--directory",
                        help="set the directory to save the data to")
    kwargs = vars(parser.parse_args())
    verbosity = logging.INFO + (kwargs.pop("quiet") - kwargs.pop("verbose")) * 10

    gLog = logging.getLogger()  # print all log entries!
    if not gLog.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StrFormatter)
        gLog.addHandler(handler)
    gLog.setLevel(verbosity)

    for key, value in list(kwargs.items()):
        if value is None:
            del kwargs[key]

    datalogger = DataLogger(log=gLog, **kwargs)
    datalogger.listen()
