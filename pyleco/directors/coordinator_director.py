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
from typing import Dict

from .director import Director


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class CoordinatorDirector(Director):
    """Direct a Coordinator."""

    def __init__(self, actor="COORDINATOR", **kwargs) -> None:
        super().__init__(actor=actor, **kwargs)

    def get_directory(self) -> dict:
        """Get the directory."""
        return self.call_method_rpc(method="compose_local_directory")

    def get_global_directory(self) -> dict:
        """Get the directory."""
        return self.call_method_rpc(method="compose_global_directory")

    def set_directory(self, coordinators: Dict[str, str]) -> None:
        """Tell the Coordinator about other coordinators (dict)."""
        return self.call_method_rpc(method="set_nodes", nodes=coordinators)
