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

from time import sleep

from pyleco.directors.transparent_director import TransparentDevice, TransparentDirector, RemoteCall


class YARTransparentDevice(TransparentDevice):
    """Transparent device with method calls of the ipg photonics YAR from pymeasure."""

    clear = RemoteCall()


def setup_director(actor: str) -> TransparentDirector:
    return TransparentDirector(actor=actor, cls=YARTransparentDevice)


def start_laser(director: TransparentDirector, target: float) -> None:
    director.device.clear()  # allowed due to the `RemoteCall` above
    if not director.device.emission_enabled:
        director.device.emission_enabled = True
        sleep(5)
    current = director.device.power_setpoint
    while current != target:
        difference = target - current
        director.device.power_setpoint = current + max(difference, 1)
        sleep(5)
        current = director.device.power_setpoint


def stop_laser(director: TransparentDirector) -> None:
    director.device.power_setpoint = 0
    sleep(5)
    director.device.emission_enabled = False


def main() -> None:
    """Do some experiment."""
    director = setup_director(actor="Namespace.YAR_actor")
    start_laser(director=director, target=10)
    for _ in range(10):
        print(director.device.power)
        sleep(5)
    stop_laser(director)


if __name__ == "__main__":
    main()
