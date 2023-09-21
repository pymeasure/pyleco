# -*- coding: utf-8 -*-
"""
Example scheme for an Actor for pymeasure instruments. 'pymeasure_actor'
"""
# This first docstring is shown in the GUI corresponding to the starter, such that it may be
# identified more easily.


import logging

from pyleco.actors.actor import Actor
from pyleco.utils.publisher import Publisher
from pymeasure.instruments.ipgphotonics import YAR

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


# Parameters
interval = 0.05  # Readout interval in s
adapter = "COM15"  # pymeasure adapter string


def readout(device, publisher: Publisher) -> None:
    """This method is executed every `interval`.

    :param device: The device driver managed by the Actor.
    :param publisher: The :class:`pyleco.utils.Publisher` instance of the Actor to publish data.
    """
    publisher.send({'some_value': device.power})


def task(stop_event) -> None:
    """The task which is run by the starter."""
    # Initialize
    with Actor(name="pymeasure_actor", cls=YAR, periodic_reading=interval) as actor:
        actor.read_publish = readout  # define the regular readout function
        actor.connect(adapter)  # connect to the device

        # Continuos loop
        actor.listen(stop_event=stop_event)  # listen for commands and do the regular readouts

        # Finish
        # in listen and __exit__ included


if __name__ == "__main__":
    """Run the task if the module is executed."""
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)

    class Signal:
        def is_set(self):
            return False
    try:
        task(Signal())
    except KeyboardInterrupt:
        pass
