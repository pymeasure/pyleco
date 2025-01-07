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
from typing import Generic, Optional, TypeVar, Union
from warnings import warn

from .director import Director


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


Device = TypeVar("Device")


class RemoteCall:
    """Descriptor for remotely calling methods.

    You can add methods by simpling adding this Descriptor.
    Whenever this instance is called, it executes :code:`call_method`
    with the attribute name as `method` parameter. For example:

    .. code::

        class XYZ(BaseDirector):
            method = RemoteCall("Docstring for that method.")  # add a RemoteCall instance as attr.
        director = XYZ()
        director.method(*some_args, **kwargs)  # execute this instance.
        # equivalent to:
        director.call_method("method", *some_args, **kwargs)

    :param str name: Name of the method, only necessary if the RemoteCall is added after class
        creation.
    :param str doc: Docstring for the method. {name} is replaced by the attribute name of the
        instance of RemoteCall, in the example by 'method'.
    """

    def __init__(self, name: str = "", doc: Optional[str] = None, **kwargs) -> None:
        self._name = name
        if doc is None:
            doc = "Call '{name}' at the remote driver."
        self._doc = doc
        super().__init__(**kwargs)

    def __set_name__(self, owner, name) -> None:
        self._name = name
        self._doc = self._doc.format(name=self._name)

    def __get__(self, obj: Director, objtype=None):
        if obj is None:
            return self

        def remote_call(*args, **kwargs):
            obj.call_action(self._name, *args, **kwargs)

        remote_call.__doc__ = self._doc
        return remote_call


class TransparentDevice:
    """For all property access, the remote device is called.

    If you want to call methods, you can add them. with :class:`RemoteCall` to a subclass of this
    instrument.
    """

    director: Director

    def __init__(self, director: Director):
        self.director = director

    def call_action(self, action: str, *args, **kwargs):
        self.director.call_action(action, *args, **kwargs)

    def __getattr__(self, name):
        if name in dir(self):
            return super().__getattribute__(name)
        else:
            return self.director.get_parameters(parameters=(name,)).get(name)

    def __setattr__(self, name, value) -> None:
        if name in dir(self) or name.startswith("_") or name in ("director"):
            super().__setattr__(name, value)
        else:
            self.director.set_parameters(parameters={name: value})

    # TODO generate a list of capabilities of the actor and return these capabilities during a call
    # to __dir__. That enables autocompletion etc.


class TransparentDirector(Director, Generic[Device]):
    """Director getting/setting all properties remotely.

    It has a :attr:`device` attribute. Whenever you get/set an attribute of `device`, the Director
    will call the Actor and try to get/set the corresponding attribute of the Actor's device.
    If you want to add method calls, you might use the :class:`RemoteCall` Descriptor to add methods
    to a subclass of :class:`TransparentDevice` and give that class to the `device_class` parameter.
    For example :code:`method = RemoteCall()` in the class definition will make sure,
    that :code:`device.method(*args, **kwargs)` will be executed remotely.

    :param actor: Name of the actor to direct.
    :param device_class: Subclass of :class:`TransparentDevice` to use as a device dummy.
    :param cls: see :code:`device_class`.

        .. deprecated:: 0.3
            Use :code:`device_class` instead.
    """

    def __init__(
        self,
        actor: Optional[Union[bytes, str]] = None,
        device_class: type[Device] = TransparentDevice,  # type: ignore[assignment]
        cls: Optional[type[Device]] = None,
        **kwargs,
    ):
        super().__init__(actor=actor, **kwargs)
        if cls is not None:
            warn("Parameter `cls` is deprecated, use `device_class` instead.", FutureWarning)
            device_class = cls
        self.device = device_class(director=self)  # type: ignore[call-arg]
