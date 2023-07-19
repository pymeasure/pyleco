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

import logging

from .director import Director


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


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

    :param str doc: Docstring for the method. {name} is replaced by the attribute name of the
        instance of RemoteCall, in the example by 'method'.
    """

    def __init__(self, doc: str = "Call '{name}' at the remote driver.", **kwargs) -> None:
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


class TransparentDirector(Director):
    """Director getting/setting all properties remotely.

    Whenever you try to get/set a property, which does not belong to the director itself,
    it tries to get/set it remotely from the actor.
    If you want to add method calls, you might use the :class:`RemoteCall` Descriptor to add methods
    to a subclass. For example :code:`method = RemoteCall()` in the class definition will make sure,
    that :code:`method(*args, **kwargs)` will be executed remotely.
    """

    def __getattr__(self, name):
        if name in dir(self):
            return super().__getattribute__(name)
        else:
            return self.get_parameters((name,)).get(name)

    def __setattr__(self, name, value) -> None:
        if name in dir(self) or name.startswith("_") or name in ("actor", "communicator",
                                                                 "generator"
                                                                 ):
            super().__setattr__(name, value)
        else:
            self.set_parameters({name: value})

    # TODO generate a list of capabilities of the actor and return these capabilites during a call
    # to __dir__. That enables autocompletion etc.
