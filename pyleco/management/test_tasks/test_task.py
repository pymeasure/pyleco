"""
Example scheme for an Actor for pymeasure instruments. 'test_task'
"""

from threading import Event
from time import sleep

from pyleco.actors.actor import Actor


class FakeInstrument:  # pragma: no cover
    _prop1 = 5

    def __init__(self):
        pass

    def connect(self):
        pass

    @property
    def constant(self):
        return 7

    @property
    def prop1(self):
        return self._prop1

    @prop1.setter
    def prop1(self, value):
        self._prop1 = value

    def triple(self, factor: float = 1) -> float:
        return factor * 3


def task(stop_event: Event) -> None:
    """The task which is run by the starter."""
    # Initialize
    while stop_event.wait(.5):
        sleep(.1)
    return
    with Actor(name="pymeasure_actor", device_class=FakeInstrument,
               periodic_reading=-1) as actor:
        actor.connect()  # connect to the device

        # Continuous loop
        actor.listen(stop_event=stop_event)  # listen for commands and do the regular readouts

        # Finish
        # in listen and __exit__ included
