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

"""Unit tests for the shared integration test helpers."""

from __future__ import annotations

import socket
from time import perf_counter

import pytest

import helpers
from helpers import reserve_free_port, reserve_free_ports, wait_for


def test_wait_for_returns_true_when_flag_flips() -> None:
    flag = {"value": False}

    def flip_after_two_polls() -> bool:
        result = flag["value"]
        flag["value"] = not flag["value"]
        return result

    start = perf_counter()
    assert wait_for(flip_after_two_polls, timeout=2.0, interval=0.01)
    assert perf_counter() - start < 1.0


def test_wait_for_returns_false_at_timeout() -> None:
    start = perf_counter()
    assert not wait_for(lambda: False, timeout=0.2, interval=0.01)
    assert perf_counter() - start >= 0.2


def test_wait_for_does_not_oversleep_past_deadline() -> None:
    start = perf_counter()
    assert not wait_for(lambda: False, timeout=0.15, interval=10.0)
    assert perf_counter() - start < 1.0


def test_reserve_free_port_skips_occupied_base() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        occupied.bind(("localhost", 0))
    except PermissionError:
        # Sandbox environments without TCP bind permission (e.g. restricted CI runners).
        occupied.close()
        pytest.skip("TCP binds are not permitted in this environment.")
    with occupied:
        base = occupied.getsockname()[1]
        occupied.listen(1)
        free = reserve_free_port(base)
    # The base port is occupied, so the returned port must be shifted upwards.
    assert base < free <= base + 32


def test_reserve_free_ports_returns_free_layout() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        occupied.bind(("localhost", 0))
    except PermissionError:
        # Sandbox environments without TCP bind permission (e.g. restricted CI runners).
        occupied.close()
        pytest.skip("TCP binds are not permitted in this environment.")
    with occupied:
        blocked_port = occupied.getsockname()[1]
        occupied.listen(1)
        # A layout whose middle member is occupied must shift as a whole.
        layout = reserve_free_ports(blocked_port - 1, (0, 1, 2))
    assert layout > blocked_port - 1
    assert blocked_port != layout + 1


def test_reserve_free_ports_base_counts_as_offset() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        occupied.bind(("localhost", 0))
    except PermissionError:
        # Sandbox environments without TCP bind permission (e.g. restricted CI runners).
        occupied.close()
        pytest.skip("TCP binds are not permitted in this environment.")
    with occupied:
        base = occupied.getsockname()[1]
        occupied.listen(1)
        layout = reserve_free_ports(base, (5,))
    assert layout > base


def test_reserve_free_ports_raises_when_no_layout_fits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers, "_probe_free_pulse", lambda candidate: False)
    with pytest.raises(OSError):
        reserve_free_ports(60100, (0, 1), span=0)


def test_reserve_free_ports_falls_back_when_bind_prohibited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helpers, "_probe_free_pulse", lambda candidate: None)
    assert reserve_free_ports(60100, (0, 1, 2)) == 60100
