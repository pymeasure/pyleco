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

import logging
from typing import Any

from .director import Director
from ..management.data_logger import ValuingModes


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class DataLoggerDirector(Director):
    """Director for the DataLogger.

    :param actor: Name of the actor to direct.
    """

    def __init__(self, actor: str = "dataLogger", **kwargs) -> None:
        super().__init__(actor=actor, **kwargs)

    def start_collecting(self, *,
                         subscriptions: list[str],
                         trigger: str | int = 1,
                         valuing_mode: ValuingModes = ValuingModes.LAST,
                         repeating: bool = False,
                         ) -> None:
        self.ask_rpc(method="start_collecting",
                     trigger=trigger,
                     subscriptions=subscriptions,
                     valuing_mode=valuing_mode,
                     repeating=repeating,
                     )

    def get_last_datapoint(self) -> dict[str, Any]:
        """Read the last datapoint."""
        return self.ask_rpc("get_last_datapoint")

    def saveData(self) -> str:
        """Save the data and return the name of the file."""
        try:
            tmo = self.communicator.timeout  # type:ignore[attr-defined]
            self.communicator.timeout = 1000  # type:ignore[attr-defined]
            name = self.ask_rpc("saveData")
            self.communicator.timeout = tmo  # type:ignore[attr-defined]
        except AttributeError:
            name = self.ask_rpc("saveData")
        return name

    def stop_collecting(self) -> None:
        """Stop the data acquisition."""
        self.ask_rpc(method="stop_collecting")
