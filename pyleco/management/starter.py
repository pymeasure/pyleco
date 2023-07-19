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

"""
The starter starts scripts (containing devices) and runs them.

For command line arguments, execute the module with `--help` parameter.

Tasks have to be PyQtObjects with name "Task" in a file called with the taskname
in the folder "tasks" or any other folder given with `directory`.
E.g. in "tasks/test1.py" for task "test1".

Created on Thu Dec 15 09:31:04 2022by Benedikt Moneke
"""

from enum import IntFlag
from importlib import import_module, reload
import logging
import os
from os import path
import sys
import threading
from typing import Any, Optional, Union

try:
    from ..utils.message_handler import MessageHandler, Event, InfiniteEvent
    from ..utils.parser import parser
except ImportError:
    from pyleco.utils.message_handler import MessageHandler, Event, InfiniteEvent
    from pyleco.utils.parser import parser


log = logging.getLogger("starter")
StrFormatter = logging.Formatter("%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s")


modules: dict[str, Any] = {}  # A dictionary of the task modules


def sanitize_tasks(tasks: Optional[Union[list[str], tuple[str, ...], str]]
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
    STARTED = 2  # if not set
    INSTALLED = 4  # check regularly, whether it is running


class Starter(MessageHandler):
    """Listen to communication and start tasks as required.

    .. code::
        starter = Starter("starter")
        starter.listen()

    :param str directory: Absolute path to the directory with the tasks modules.
    :param tasks: List of task names to execute on startup.
    """

    def __init__(self, name: str = "starter", directory: Optional[str] = None,
                 tasks: Optional[list[str]] = None, **kwargs) -> None:
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
        if tasks is not None:
            for task in tasks:
                self.start_task(task)

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.rpc.method(self.start_tasks)
        self.rpc.method(self.stop_tasks)
        self.rpc.method(self.restart_tasks)
        self.rpc.method(self.install_tasks)
        self.rpc.method(self.list_tasks)
        self.rpc.method(self.status_tasks)

    def listen(self, stop_event: Event = InfiniteEvent(), waiting_time: int = 100) -> None:
        """Listen for zmq communication until `stop_event` is set.

        :param waiting_time: Time to wait for a readout signal in ms.
        """
        super().listen(stop_event=stop_event, waiting_time=waiting_time, **kwargs)
        keys = list(self.threads.keys())
        for name in keys:
            # set all stop signals
            self.events[name].set()
        for name in keys:
            # wait for threads to have stopped
            thread = self.threads[name]
            thread.join(2)
            if thread.is_alive():
                log.warning(f"Task '{name}' did not stop in time!")
                # TODO add possibility to stop thread otherwise.
            try:
                del self.threads[name]
            except Exception as exc:
                log.exception(f"Deleting task {name} failed", exc_info=exc)
        log.info("Starter stopped.")

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
                self.threads[name] = thread = threading.Thread(target=script.task,
                                                               args=(self.events[name],),
                                                               daemon=True)
            except Exception as exc:
                log.exception(f"Creation of task '{name}' failed.", exc_info=exc)
                return
            thread.start()

    def stop_tasks(self, names: Union[list[str], tuple[str, ...]]) -> None:
        for name in sanitize_tasks(names):
            self.stop_task(name)

    def stop_task(self, name: str) -> None:
        """Stop a task."""
        try:
            del self.started_tasks[name]
        except KeyError:
            pass  # Not present
        if name not in self.threads.keys():
            return
        log.info(f"Stopping task '{name}'.")
        self.events[name].set()
        thread = self.threads[name]
        thread.join(timeout=2)
        if thread.is_alive():
            log.warning(f"Task '{name}' did not stop in time!")
            # TODO add possibility to stop thread otherwise.
        try:
            del self.threads[name]
        except Exception as exc:
            log.exception(f"Deleting task {name} failed", exc_info=exc)

    def restart_tasks(self, names: Union[list[str], tuple[str, ...]]) -> None:
        for name in sanitize_tasks(names):
            self.stop_task(name)
            self.start_task(name)

    def install_tasks(self, names: Union[list[str], tuple[str, ...]]) -> None:
        for name in sanitize_tasks(names):
            self.install_task(name)

    def install_task(self, name: str) -> None:
        """Add tasks to the installed list."""
        self.started_tasks[name] = self.started_tasks.get(name, 0) | Status.INSTALLED

    def status_tasks(self, names: Optional[list[str]] = None) -> dict[str, Status]:
        """Enumerate the status of the started/running tasks and keep the records clean.

        :param list names: List of tasks to look for.
        """
        ret_data = {} if names is None else {key: Status.STOPPED for key in names}
        ret_data.update(self.started_tasks)  # type: ignore
        for key in list(self.threads.keys()):
            if self.threads[key].is_alive():
                ret_data[key] |= Status.RUNNING
            else:
                del self.threads[key]
        return ret_data

    def list_tasks(self) -> list[dict[str, str]]:
        """List all tasks (with name and tooltip) available in the folder."""
        try:
            filenames = os.listdir(self.directory)
        except FileNotFoundError:
            log.error("Task folder not found.")
            return []
        tasks = []
        for name in filenames:
            if name.endswith(".py") and not name == "__init__.py":
                with open(f"{self.directory}/{name}", "r") as file:
                    # Search for the first line with triple quotes
                    i = 0
                    while not file.readline().strip() == '\"\"\"' and i < 10:
                        i += 1
                    tooltip = file.readline()  # first line after line with triple quotes
                tasks.append({'name': name.replace(".py", ""), 'tooltip': tooltip})
        log.debug(f"Tasks found: {tasks}.")
        return tasks

    def check_installed_tasks(self) -> None:
        """Check whether installed tasks are running."""
        self.status_tasks()
        for task, s in self.started_tasks.items():
            if s & Status.INSTALLED and not s & Status.RUNNING:
                self.start_task(task)


if __name__ == "__main__":
    parser.description = "Start tasks as required."
    parser.add_argument("tasks", nargs="*",
                        help="Tasks to execute at startup.")
    parser.add_argument("-d", "--directory",
                        help="set the directory to search for tasks, do not add a trailing slash")
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

    starter = Starter(log=gLog, **kwargs)
    starter.listen()