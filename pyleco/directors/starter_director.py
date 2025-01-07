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
from typing import Optional, Union

from .director import Director


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class StarterDirector(Director):
    """Director for the Starter.

    :param actor: Name of the actor to direct.
    """

    def __init__(self, actor: str = "starter", **kwargs) -> None:
        super().__init__(actor=actor, **kwargs)

    def start_tasks(self, names: Union[list[str], str], actor: Optional[Union[bytes, str]] = None
                    ) -> None:
        """Start the task or tasks.

        :param names: Single task name or list of task names to start.
        :param name: Name of the starter to communicate with.
        """
        if isinstance(names, str):
            names = [names]
        self.ask_rpc(method="start_tasks", names=names, actor=actor)

    def restart_tasks(self, names: Union[list[str], str], actor: Optional[Union[bytes, str]] = None
                      ) -> None:
        """Restart the task or tasks.

        :param names: Single task name or list of task names to restart.
        :param name: Name of the starter to communicate with.
        """
        if isinstance(names, str):
            names = [names]
        self.ask_rpc(method="restart_tasks", names=names, actor=actor)

    def stop_tasks(self, names: Union[list[str], str], actor: Optional[Union[bytes, str]] = None
                   ) -> None:
        """Stop the task or tasks.

        :param names: Single task name or list of task names to stop.
        :param name: Name of the starter to communicate with.
        """
        if isinstance(names, str):
            names = [names]
        self.ask_rpc(method="stop_tasks", names=names, actor=actor)

    def install_tasks(self, names: Union[list[str], str], actor: Optional[Union[bytes, str]] = None
                      ) -> None:
        """Install the tasks.

        :param names: Single task name or list of task names to install.
        :param name: Name of the starter to communicate with.
        """
        if isinstance(names, str):
            names = [names]
        self.ask_rpc(method="install_tasks", names=names, actor=actor)

    def status_tasks(self, names: Optional[Union[list[str], str]] = None,
                     actor: Optional[Union[bytes, str]] = None) -> dict[str, int]:
        """Query the status of these tasks and all running ones.

        :param names: List of task names to ask for.
        :param name: Name of the starter to communicate with.
        """
        if isinstance(names, str):
            names = [names]
        return self.ask_rpc(method="status_tasks", names=names, actor=actor)

    def list_tasks(self, actor: Optional[Union[bytes, str]] = None) -> list[dict[str, str]]:
        """List all available tasks with name and tooltip."""
        return self.ask_rpc(method="list_tasks", actor=actor)
