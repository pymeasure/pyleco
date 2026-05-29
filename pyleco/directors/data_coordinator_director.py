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
from typing import Any, cast, Dict, List

from .director import Director


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class DataCoordinatorDirector(Director):
    """Direct a DataCoordinator."""

    def __init__(self, actor: bytes | str | None = "DATA_COORDINATOR", **kwargs: Any) -> None:
        super().__init__(actor=actor, **kwargs)

    def connect_to_gatherer(self, address: str) -> None:
        """Connect to a remote Gatherer."""
        return cast(None, self.ask_rpc(method="connect_to_gatherer", address=address))

    def disconnect_from_gatherer(self, address: str) -> None:
        """Disconnect from a remote Gatherer."""
        return cast(None, self.ask_rpc(method="disconnect_from_gatherer", address=address))

    def list_gatherers(self) -> list[str]:
        """List connected Gatherers."""
        return cast(List[str], self.ask_rpc(method="list_gatherers"))

    def send_data_addresses(self) -> dict[str, str]:
        """Get data addresses."""
        return cast(Dict[str, str], self.ask_rpc(method="send_data_addresses"))
