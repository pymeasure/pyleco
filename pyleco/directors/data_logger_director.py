#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2026 PyLECO Developers
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
import logging
from typing import Any, cast, Dict

from .director import Director
from ..management.data_logger import ValuingModes, TriggerTypes


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class DataLoggerDirector(Director):
    """Director for the DataLogger.

    :param actor: Name of the actor to direct.
    """

    def __init__(self, actor: str = "dataLogger", **kwargs: Any) -> None:
        super().__init__(actor=actor, **kwargs)

    def start_collecting(
        self,
        *,
        variables: list[str] | None = None,
        units: dict[str, Any] | None = None,
        trigger_type: TriggerTypes | None = None,
        trigger_timeout: float | None = None,
        trigger_variable: str | None = None,
        valuing_mode: ValuingModes | None = None,
        value_repeating: bool | None = None,
    ) -> None:
        self.ask_rpc(method="start_collecting",
                     trigger_type=trigger_type,
                     trigger_timeout=trigger_timeout,
                     trigger_variable=trigger_variable,
                     variables=variables,
                     units=units,
                     valuing_mode=valuing_mode,
                     value_repeating=value_repeating,
                     )

    def get_last_datapoint(self) -> dict[str, Any]:
        """Read the last datapoint."""
        return cast(Dict[str, Any], self.ask_rpc("get_last_datapoint"))

    def save_data(self) -> str:
        """Save the data and return the name of the file."""
        # increase the timeout as saving might take longer than usual requests
        tmo = self.communicator.timeout
        self.communicator.timeout = 1000
        name = cast(str, self.ask_rpc("save_data"))
        self.communicator.timeout = tmo
        return name

    def save_data_async(self) -> bytes:
        """Save the data asynchronously."""
        return self.ask_rpc_async("save_data")

    def stop_collecting(self) -> None:
        """Stop the data acquisition."""
        return cast(None, self.ask_rpc(method="stop_collecting"))
