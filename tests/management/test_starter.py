#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2024 PyLECO Developers
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

from unittest.mock import MagicMock

import pytest

from pyleco.test import FakeContext
from pyleco.management.starter import Starter, Status


@pytest.fixture
def starter() -> Starter:
    starter = Starter(context=FakeContext())
    return starter


class FakeThread:
    def __init__(self, target=None, alive=False, *args, **kwargs) -> None:
        self._target = target
        self._args = args
        self._kwargs = kwargs
        self._alive = alive

    def start(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout=None) -> None:
        return


def test_init(starter: Starter):
    assert starter.started_tasks == {}
    assert starter.threads == {}


@pytest.mark.parametrize("pre, post", (
        (Status.STARTED | Status.INSTALLED, Status.STARTED | Status.INSTALLED),
        (None, Status.INSTALLED),  # not yet in the dict
        (Status.STARTED, Status.STARTED | Status.INSTALLED),
        (Status.STARTED | Status.RUNNING, Status.STARTED | Status.RUNNING | Status.INSTALLED),
        (Status.STOPPED, Status.INSTALLED),
))
def test_install_task(starter: Starter, pre: Status, post: Status):
    if pre is not None:
        starter.started_tasks["test"] = pre
    starter.install_task("test")
    assert starter.started_tasks["test"] == post


@pytest.mark.parametrize("pre, post", (
        (Status.RUNNING | Status.INSTALLED, Status.RUNNING),
        (None, Status.STOPPED),  # not yet in the dict
        (Status.RUNNING, Status.RUNNING),
        (Status.STOPPED, Status.STOPPED),
))
def test_uninstall_task(starter: Starter, pre: Status, post: Status):
    if pre is not None:
        starter.started_tasks["test"] = pre
    starter.uninstall_task("test")
    assert starter.started_tasks.get("test") == post


class Test_status_tasks:
    @pytest.fixture
    def status(self, starter: Starter) -> dict[str, Status]:
        starter.threads["SR"] = FakeThread(alive=True)  # type: ignore
        starter.threads["S"] = FakeThread()  # type: ignore
        starter.threads["NS"] = FakeThread(alive=True)  # type: ignore
        starter.started_tasks = {
            "SR": Status.STARTED | Status.RUNNING,
            "S": Status.STARTED | Status.RUNNING,
            "NS": Status.STARTED,
        }
        self.starter = starter
        return starter.status_tasks(names=["unknown"])

    def test_started_running(self, status):
        """Test that a running task remains running."""
        assert status["SR"] == Status.STARTED | Status.RUNNING

    def test_started_not_running(self, status):
        """Test that a stopped thread is not running anymore."""
        assert status["S"] == Status.STARTED

    def test_newly_started_is_also_running(self, status):
        """Test that a newly started (last time not running) is now running."""
        assert status["NS"] == Status.STARTED | Status.RUNNING

    def test_unknown_is_marked_stopped(self, status):
        assert status["unknown"] == Status.STOPPED

    def test_stopped_running_thread_is_removed(self, status):
        assert "S" not in self.starter.threads.keys()

    def test_stopped_causes_log_entry(self, status, caplog: pytest.LogCaptureFixture):
        assert caplog.get_records(when="setup")[-1].message == "Thread 'S' stopped unexpectedly."


class Test_check_installed_tasks:
    @pytest.fixture
    def starter_cit(self, starter: Starter) -> Starter:
        starter.start_task = MagicMock()  # type: ignore[method-assign]
        starter.started_tasks = {
            "IR": Status.INSTALLED | Status.RUNNING,
            "INR": Status.INSTALLED,
            "SR": Status.STARTED | Status.RUNNING,
            "SNR": Status.STARTED,  # not running, should not be started as it is not installed.
        }
        starter.check_installed_tasks()
        return starter

    def test_start_installed_but_not_running_task(self, starter_cit: Starter):
        """Test, that only the installed (and not running) task is started."""
        starter_cit.start_task.assert_called_once_with("INR")  # type: ignore[attr-defined]
