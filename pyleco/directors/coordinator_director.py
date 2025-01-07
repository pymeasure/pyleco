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
import logging

from .director import Director


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class CoordinatorDirector(Director):
    """Direct a Coordinator."""

    def __init__(self, actor="COORDINATOR", **kwargs) -> None:
        super().__init__(actor=actor, **kwargs)

    def get_local_components(self) -> list[str]:
        """Get the directory."""
        return self.ask_rpc(method="send_local_components")

    def get_global_components(self) -> dict[str, list[str]]:
        """Get the directory."""
        return self.ask_rpc(method="send_global_components")

    def get_nodes(self) -> dict[str, str]:
        """Get all known nodes."""
        return self.ask_rpc(method="send_nodes")

    def add_nodes(self, coordinators: dict[str, str]) -> None:
        """Tell the Coordinator about other coordinators (dict)."""
        return self.ask_rpc(method="add_nodes", nodes=coordinators)
