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
from enum import IntFlag
from importlib import import_module, reload
import logging
import os
from os import path
import sys
import threading
from typing import Any, Optional, Union

if __name__ != "__main__":
    from ..utils.message_handler import MessageHandler
    from ..utils.parser import parser, parse_command_line_parameters
else:  # pragma: no cover
    from pyleco.utils.message_handler import MessageHandler
    from pyleco.utils.parser import parser, parse_command_line_parameters


log = logging.getLogger("starter")
StrFormatter = logging.Formatter("%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s")


modules: dict[str, Any] = {}  # A dictionary of the task modules


def sanitize_tasks(
    tasks: Optional[Union[list[str], tuple[str, ...], str]],
) -> Union[tuple[str, ...], list[str]]:
    """Ensure that the tasks are a list of tasks."""
    if tasks is None:
        return ()
    if not isinstance(tasks, (list, tuple)):
        tasks = (tasks,)
    for task in tasks:
        if not isinstance(task, str):
            log.error(f"Invalid task name '{task}' received.")
            return ()
    return tasks


class Status(IntFlag):
    STOPPED = 0
    RUNNING = 1  # currently running
    STARTED = 2  # has been started and should be running
    INSTALLED = 4  # check regularly, whether it is running, restart if not running anymore


class Starter(MessageHandler):
    """Listen to communication and start tasks as required.

    The Starter can start functions called `task` with the following signature
    ``task(stop_event: threading.Event) -> None: ...``.
    Whenever a task should be started, the Starter looks in :attr:`directory` for a module with that
    name and loads it.
    If the module has been loaded already, it is reloaded to get the newest version.
    Attention: dependencies are not reloaded!
    Then it starts the method `task` of that module in a separate thread.

    When the Starter stops a task, it sets the corresponding `threading.Event`.

    The first str line of a module is the modules description, available from :meth:`list_tasks`.

    If you write your own task modules, make sure, that you react in a reasonable time to a stop
    event.
    You can use `while stop_event.wait(timeout)` to execute something regularly.
    Pyleco Actors should be able to consume a `threading.Event` in order to be compatible.

    .. code::
        starter = Starter("starter")
        starter.listen()

    :param str directory: Absolute path to the directory with the tasks modules.
    :param tasks: List of task names to execute on startup.
    """

    def __init__(
        self,
        name: str = "starter",
        directory: Optional[str] = None,
        tasks: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(name=name, **kwargs)
        self.threads: dict[str, threading.Thread] = {}  # List of threads
        self.events: dict[str, threading.Event] = {}  # Events to stop the threads.
        self.started_tasks: dict[str, int | Status] = {}  # A list of all tasks started
        if directory is not None:
            self.directory = path.normpath(directory)
            head, tail = path.split(self.directory)
            sys.path.append(head)
            self.folder_name = tail
        else:
            # TODO remove?
            self.directory = "test_tasks"
            self.folder_name = "test_tasks"

        log.info(f"Starter started with tasks in folder '{self.directory}'.")
        self.start_tasks(tasks or ())

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.register_rpc_method(self.start_tasks)
        self.register_rpc_method(self.stop_tasks)
        self.register_rpc_method(self.restart_tasks)
        self.register_rpc_method(self.install_tasks)
        self.register_rpc_method(self.list_tasks)
        self.register_rpc_method(self.status_tasks)
        self.register_rpc_method(self.uninstall_tasks)

    def _listen_close(self, waiting_time: Optional[int] = None) -> None:
        """Close the listening loop."""
        super()._listen_close(waiting_time=waiting_time)
        self.stop_all_tasks()
        log.info("Starter stopped.")

    def stop_all_tasks(self) -> None:
        self.started_tasks = {}
        keys = list(self.threads.keys())
        for name in keys:
            # set all stop signals
            self.events[name].set()
        for name in keys:
            self.wait_for_stopped_thread(name)

    def heartbeat(self) -> None:
        """Check installed tasks at heartbeating."""
        super().heartbeat()
        self.check_installed_tasks()

    def start_tasks(self, names: Union[list[str], tuple[str, ...]]) -> None:
        for name in sanitize_tasks(names):
            self.start_task(name)

    def start_task(self, name: str) -> None:
        """Start the `Task` object in a script with `name` in a separate thread."""
        if name in self.threads.keys() and self.threads[name].is_alive():
            log.error(f"Task '{name}' is already running.")
            self.started_tasks[name] |= Status.RUNNING
        else:
            log.info(f"Starting task '{name}'.")
            self.started_tasks[name] = self.started_tasks.get(name, 0) | Status.STARTED
            try:
                if name in modules.keys():
                    modules[name] = script = reload(modules[name])
                else:
                    modules[name] = script = import_module(f"{self.folder_name}.{name}")
            except Exception as exc:
                log.exception(f"Loading task '{name}' failed.", exc_info=exc)
                return
            self.events[name] = threading.Event()
            try:
                self.threads[name] = thread = threading.Thread(
                    target=script.task, args=(self.events[name],), daemon=True
                )
            except Exception as exc:
                log.exception(f"Creation of task '{name}' failed.", exc_info=exc)
                return
            thread.start()

    def stop_tasks(self, names: Union[list[str], tuple[str, ...]]) -> None:
        for name in sanitize_tasks(names):
            self.stop_task(name)

    def stop_task(self, name: str) -> None:
        """Stop a task and don't restart it, if it was installed."""
        try:
            del self.started_tasks[name]
        except KeyError:
            pass  # Not present
        if name not in self.threads.keys():
            return
        log.info(f"Stopping task '{name}'.")
        self.events[name].set()
        self.wait_for_stopped_thread(name)

    def wait_for_stopped_thread(self, name: str) -> None:
        thread = self.threads[name]
        thread.join(timeout=2)
        if thread.is_alive():
            log.warning(f"Task '{name}' did not stop in time!")
            # TODO add possibility to stop thread otherwise.
        try:
            del self.threads[name]
        except Exception as exc:
            log.exception(f"Deleting task '{name}' failed", exc_info=exc)

    def restart_tasks(self, names: Union[list[str], tuple[str, ...]]) -> None:
        for name in sanitize_tasks(names):
            self.stop_task(name)
            self.start_task(name)

    def install_tasks(self, names: Union[list[str], tuple[str, ...]]) -> None:
        for name in sanitize_tasks(names):
            self.install_task(name)

    def install_task(self, name: str) -> None:
        """Add tasks to the installed list."""
        log.info(f"Install task '{name}'.")
        self.started_tasks[name] = self.started_tasks.get(name, 0) | Status.INSTALLED

    def uninstall_tasks(self, names: Union[list[str], tuple[str, ...]]) -> None:
        for name in sanitize_tasks(names):
            self.uninstall_task(name)

    def uninstall_task(self, name: str) -> None:
        """Uninstalls a task without stopping it, if it is already running."""
        self.started_tasks[name] = self.started_tasks.get(name, 0) & ~Status.INSTALLED

    def status_tasks(self, names: Optional[list[str]] = None) -> dict[str, Status]:
        """Enumerate the status of the started/running tasks and keep the records clean.

        :param list names: List of tasks to look for.
        """
        ret_data = {} if names is None else {key: Status.STOPPED for key in names}
        for key in list(self.threads.keys()):
            if self.threads[key].is_alive():
                self.started_tasks[key] |= Status.RUNNING
            else:
                self.started_tasks[key] = self.started_tasks.get(key, 0) & ~Status.RUNNING
                del self.threads[key]
                log.warning(f"Thread '{key}' stopped unexpectedly.")
        ret_data.update(self.started_tasks)  # type: ignore
        return ret_data

    def list_tasks(self) -> list[dict[str, str]]:
        """List all tasks (with name and tooltip) available in the folder."""
        try:
            filenames = os.listdir(self.directory)
        except FileNotFoundError:
            log.error(f"Task folder '{self.directory}' not found.")
            return []
        tasks = []
        for name in filenames:
            if name.endswith(".py") and not name == "__init__.py":
                with open(f"{self.directory}/{name}", "r") as file:
                    # Search for the first line with triple quotes
                    for i in range(10):
                        if file.readline().strip() == '"""':
                            break
                    tooltip = file.readline()  # first line after line with triple quotes
                tasks.append({"name": name.replace(".py", ""), "tooltip": tooltip})
        log.debug(f"Tasks found: {tasks}.")
        return tasks

    def check_installed_tasks(self) -> None:
        """Check whether installed tasks are running."""
        self.status_tasks()
        for task, s in self.started_tasks.items():
            if s & Status.INSTALLED and not s & Status.RUNNING:
                log.info(f"Starting installed task '{task}' with status {s}.")
                self.start_task(task)


def main() -> None:
    parser.add_argument("tasks", nargs="*", help="Tasks to execute at startup.")
    parser.add_argument(
        "-d",
        "--directory",
        help="set the directory to search for tasks, do not add a trailing slash",
    )

    gLog = logging.getLogger()  # print all log entries!
    if not gLog.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StrFormatter)
        gLog.addHandler(handler)
    kwargs = parse_command_line_parameters(
        parser=parser, parser_description="Start tasks as required.", logger=gLog
    )

    starter = Starter(log=gLog, **kwargs)
    starter.listen()


if __name__ == "__main__":  # pragma: no cover
    main()
