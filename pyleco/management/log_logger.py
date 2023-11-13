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
import json
import logging
from logging.handlers import QueueHandler
from typing import Any, Optional


if __name__ == "__main__":
    from pyleco.utils.extended_message_handler import ExtendedMessageHandler, DataMessage
    from pyleco.utils.parser import parser
    from pyleco.core import LOG_SENDING_PORT
    from pyleco.utils.zmq_log_handler import ZmqLogHandler
else:
    from ..utils.extended_message_handler import ExtendedMessageHandler, DataMessage
    from ..utils.parser import parser
    from ..core import LOG_SENDING_PORT
    from ..utils.zmq_log_handler import ZmqLogHandler


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())
StrFormatter = logging.Formatter("%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s")
glog = logging.getLogger()


class ListHandler(QueueHandler):
    """Handle logs emitting a Qt signal."""

    def __init__(self, log_list, **kwargs) -> None:
        super().__init__(log_list, **kwargs)  # type: ignore

    def enqueue(self, record: Any) -> None:
        """Enqueue a message, if the fullname is given."""
        self.queue.append(record)  # type: ignore

    prepare = ZmqLogHandler.prepare  # type: ignore


class LogLogger(ExtendedMessageHandler):
    """Collect published log entries

    .. code::

        log_logger = LogLogger()
        log_logger.listen()  # listen until a shutdown signal is received.
    """

    log_entries: dict[str, list[list[str]]]

    def __init__(self, name: str = "LogLoggerN", directory: str = ".",
                 data_port: int = LOG_SENDING_PORT,
                 **kwargs) -> None:
        super().__init__(name=name, data_port=data_port, **kwargs)
        self.directory = directory
        self.reset_data_storage()

        lhandler = ListHandler(self.log_entries['self'])
        glog.addHandler(lhandler)

        self.last_save_name = None
        # TODO add auto_save functionality?

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.rpc.method()(self.start_collecting)
        self.rpc.method()(self.save_data)
        self.rpc.method()(self.stop_collecting)
        self.rpc.method()(self.get_last_save_name)

    def shut_down(self) -> None:
        self.stop_collecting()
        super().shut_down()

    def __del__(self) -> None:
        self.stop_collecting()

    def _listen_setup(self, subscriptions: Optional[list[str] | tuple[str, ...]] = None,  # type: ignore  # noqa
                      **kwargs):
        poller = super()._listen_setup(**kwargs)
        self.start_collecting(subscriptions=subscriptions)
        return poller

    # Data management
    def handle_subscription_message(self, message: DataMessage) -> None:
        """Handle a message read from the data protocol and handle it."""
        emitter = message.topic.decode()
        log_entry = message.data
        self.add_log_entry(emitter=emitter,
                           log_entry=log_entry)  # type: ignore

    def handle_subscription_data(self, data: dict) -> None:
        """Store `data` dict in `tmp`"""
        # legacy!
        for key, value in data.items():
            self.add_log_entry(emitter=key, log_entry=value)

    def add_log_entry(self, emitter: str, log_entry: list[str]) -> None:
        li = self.log_entries.get(emitter)
        if li is None:
            li = self.log_entries[emitter] = []
        li.append(log_entry)

    # Control
    def start_collecting(self, subscriptions: Optional[list[str] | tuple[str, ...]] = None) -> None:
        """Start collecting data."""
        if subscriptions is not None:
            self.subscribe(topics=subscriptions)

    def reset_data_storage(self) -> None:
        """Reset the data storage."""
        ll = self.log_entries.get('self')
        if ll is not None:
            ll.clear()
        else:
            ll = []
        self.log_entries = {'self': ll}

    def save_data(self, meta: None | dict = None, suffix: str = "", header: str = "") -> str:
        """Save the data.

        :param addr: Reply address for the filename.
        :param dict meta: The meta data to save. Use e.g. in subclass
            Protected keys: units, today, name, configuration, user.
        :param str suffix: Suffix to append to the filename.
        :return str: Name of the saved file.
        """
        raise NotImplementedError("Not yet implemented")
        # Below is code for comparison from the datalogger
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
            'configuration': self.get_configuration(),
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
            self.last_save_name = name
            return name

    def stop_collecting(self) -> None:
        """Stop the data acquisition."""
        log.info("Stopping to collect data.")
        self.unsubscribe_all()

    def get_last_save_name(self) -> str | None:
        """Return the name of the last save."""
        return self.last_save_name

    def get_log_entries(self, emitters: list[str] | tuple[str, ...]
                        ) -> dict[str, list[list[str]] | None]:
        return_dict = {}
        for emitter in emitters:
            return_dict[emitter] = self.log_entries.get(emitter)
        if self.full_name in emitters:
            return_dict[self.full_name] = self.log_entries.get('self')
        return return_dict


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

    datalogger = LogLogger(log=gLog, **kwargs)
    datalogger.listen()
