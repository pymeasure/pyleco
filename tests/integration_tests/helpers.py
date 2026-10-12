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

"""Shared helpers for the live integration tests.

These are polling based readiness checks and port-selection utilities to avoid
sleep-based synchronization (which is the root cause of flaky smoke tests).
"""

from __future__ import annotations

import errno
import socket
from contextlib import closing
from time import sleep, time
from typing import Any, Callable, Iterable

from pyleco.directors.coordinator_director import CoordinatorDirector

READINESS_PROBE_TIMEOUT = 1.0  # s, per-attempt network timeout of a readiness probe.
READINESS_PROBE_NAME = "readiness_probe"  # communicator name of the temporary probe.
_BIND_PROHIBITED = (errno.EACCES, errno.EPERM)  # bind permission denied altogether.


def wait_for(condition: Callable[[], bool], timeout: float, interval: float = 0.05) -> bool:
    """Poll `condition` until it returns True or `timeout` seconds have passed.

    Returns whether the condition was fulfilled before the deadline. Small sleeps
    between the polls keep this from being a busy loop; the last sleep never
    overshoots the deadline.
    """
    deadline = time() + timeout
    while True:
        if condition():
            return True
        remaining = deadline - time()
        if remaining <= 0:
            return False
        sleep(min(interval, remaining))


def _probe_free_pulse(candidate: int) -> bool | None:
    """Whether TCP port `candidate` can be bound right now.

    Returns True when free, False when occupied, and None when binding is
    prohibited altogether (e.g. EACCES/EPERM in sandboxed environments).
    """
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as probe:
        try:
            probe.bind(("localhost", candidate))
        except OSError as err:
            if err.errno in _BIND_PROHIBITED:
                return None
            return False
    return True


def reserve_free_port(port: int, span: int = 32) -> int:
    """Return the first free TCP port in the range [`port`, `port + span`].

    The requested `port` is probed with a plain (SO_REUSEADDR-free) bind attempt;
    if it is blocked, e.g. by lingering sockets of a previous module, the next
    ports are tried in consecutive order so that a fixed relative layout of
    derived ports can be shifted as a whole. The probe socket is released again,
    the returned port must then be bound by the actual user (inherently racy but
    deterministic enough because ephemeral OS ports are far away).

    If binding is prohibited altogether (sandboxed runners raising EACCES/EPERM
    for every port), stepping up cannot help and the requested `port` is handed
    back best-effort, so collection/executing in such an environment still works.

    Raises OSError if all candidates in the range are blocked otherwise.
    """
    for candidate in range(port, port + span + 1):
        state = _probe_free_pulse(candidate)
        if state is None:
            return port
        if state:
            return candidate
    raise OSError(f"No free port found in the range {port}-{port + span}.")


def reserve_free_ports(port: int, offsets: Iterable[int], span: int = 32) -> int:
    """Return a base port such that *every* derived port `base + offset` is free.

    Works like :func:`reserve_free_port`, but validates the whole relative port
    layout instead of only one port: starting from `port`, each candidate base
    in [`port`, `port + span`] is accepted only if all ports `base + offset`
    (for `offset` in `offsets`) can be bound. Thereby all derived ports of a
    layout (e.g. neighboring xpub/xsub/gatherer servers of a coordinator) are
    guaranteed free, and a blocked member shifts the whole layout upwards.

    If binding is prohibited altogether (see :func:`reserve_free_port`), the
    requested `port` is handed back best-effort as well.

    Raises OSError if no candidate in the range provides a fully free layout.
    """
    # The base port itself is always part of the validated layout.
    probes = sorted({*offsets, 0})
    for candidate in range(port, port + span + 1):
        states = [_probe_free_pulse(candidate + o) for o in probes]
        if None in states:
            return port
        if all(states):
            return candidate
    raise OSError(f"No free port layout found in the range {port}-{port + span}.")


def coordinator_ready(port: int, **kwargs: Any) -> bool:
    """Check whether a Coordinator answers a management RPC on `port`.

    Opens a short-lived temporary `CoordinatorDirector` (i.e. signs in and out
    again, keeping the coordinator's component list clean between attempts).
    Further keyword arguments are forwarded to the underlying `Communicator`,
    e.g. a shared zmq `context`.
    """
    kwargs.setdefault("timeout", READINESS_PROBE_TIMEOUT)
    try:
        with CoordinatorDirector(port=port, name=READINESS_PROBE_NAME, **kwargs) as director:
            director.get_nodes()
    except Exception:
        return False
    return True


def component_ready(port: int, component: str, namespace: str | None = None, **kwargs: Any) -> bool:
    """Check whether `component` is registered at the Coordinator on `port`.

    If `namespace` is None, the local component list of that coordinator is
    queried, otherwise the global (namespace -> components) map is checked.
    See :func:`coordinator_ready` for the sign in/out behavior.
    """
    kwargs.setdefault("timeout", READINESS_PROBE_TIMEOUT)
    try:
        with CoordinatorDirector(port=port, name=READINESS_PROBE_NAME, **kwargs) as director:
            if namespace is None:
                return component in director.get_local_components()
            return component in director.get_global_components().get(namespace, [])
    except Exception:
        return False


def send_until_visible(
    send: Callable[[], None],
    visible: Callable[[], bool],
    timeout: float = 5.0,
    attempt_timeout: float = 0.25,
) -> bool:
    """Send until `visible` turns True, retrying if messages are dropped.

    A freshly connected PUB socket suffers from the zmq slow joiner problem: the
    first messages may be dropped by the peer. Therefore send again and again
    (each attempt followed by a short `attempt_timeout` waiting for the effect)
    until `visible` becomes True or `timeout` elapsed.
    """

    def attempt() -> bool:
        send()
        return wait_for(visible, timeout=attempt_timeout, interval=0.02)

    return wait_for(attempt, timeout=timeout, interval=0.0)
