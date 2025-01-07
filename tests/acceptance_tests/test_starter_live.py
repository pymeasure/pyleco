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

import logging
import os
import threading
from time import sleep

import pytest

from pyleco.coordinators.coordinator import Coordinator
from pyleco.management.starter import Starter, Status
from pyleco.directors.starter_director import StarterDirector
from pyleco.directors.coordinator_director import CoordinatorDirector

from pyleco.management.test_tasks import test_task

# Constants
PORT = 60005


def start_coordinator(namespace: str, port: int, coordinators=None, **kwargs):
    with Coordinator(namespace=namespace, port=port, **kwargs) as coordinator:
        coordinator.routing(coordinators=coordinators)


def start_starter(event: threading.Event):
    path = os.path.dirname(test_task.__file__)
    starter = Starter(directory=path, port=PORT)
    starter.listen(event)


@pytest.fixture(scope="module")
def director():
    """A leco setup."""
    glog = logging.getLogger()
    glog.setLevel(logging.DEBUG)
    # glog.addHandler(logging.StreamHandler())
    log = logging.getLogger("test")
    stop_event = threading.Event()
    threads = []
    threads.append(threading.Thread(target=start_coordinator,
                                    kwargs=dict(namespace="N1", port=PORT)))
    threads.append(threading.Thread(target=start_starter, kwargs=dict(event=stop_event)))
    for thread in threads:
        thread.daemon = True
        thread.start()
    sleep(1)
    director = StarterDirector(actor="starter", port=PORT, timeout=5)
    yield director
    log.info("Tearing down")
    stop_event.set()
    director.shut_down_actor(actor="COORDINATOR")
    for thread in threads:
        thread.join(0.5)


def test_sign_in(director: StarterDirector):
    d2 = CoordinatorDirector(communicator=director.communicator)
    assert "starter" in d2.get_local_components()  # type: ignore


def test_tasks_listing(director: StarterDirector):
    tasks = director.list_tasks()
    expected_tasks = [
        {"name": "failing_task", "tooltip": ""},
        {
            "name": "no_task",
            "tooltip": "Task which can be imported, but not started as method `task` is missing.\n",
        },
        {
            "name": "test_task",
            "tooltip": "Example scheme for an Actor for pymeasure instruments. 'test_task'\n",
        },
    ]
    for t in expected_tasks:
        assert t in tasks
    assert len(tasks) == len(expected_tasks), "More tasks present than expected."


def test_start_task(director: StarterDirector):
    director.start_tasks("test_task")
    status = Status(director.status_tasks("test_task")["test_task"])
    assert Status.STARTED in status
    assert Status.RUNNING in status


def test_stop_task(director: StarterDirector):
    director.stop_tasks("test_task")
    status = Status(director.status_tasks("test_task").get("test_task", 0))
    assert Status.STARTED not in status
    assert Status.RUNNING not in status


def test_start_task_again(director: StarterDirector):
    director.start_tasks(["test_task", "failing_task", "no_task"])
    status = Status(director.status_tasks("test_task")["test_task"])
    assert Status.STARTED in status
    assert Status.RUNNING in status
    director.stop_tasks(["test_task", "no_task"])
