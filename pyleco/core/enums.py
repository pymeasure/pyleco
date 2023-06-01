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

try:
    from enum import StrEnum  # type: ignore
except ImportError:
    # for versions <3.11
    from enum import Enum

    class StrEnum(str, Enum):
        pass  # just inherit


class Commands(StrEnum):
    """Valid commands for the control protocol."""

    # Coordinator communication requests
    SIGNIN = "SI"
    SIGNOUT = "D"
    CO_SIGNIN = "COS"  # Sign in as a Coordinator
    CO_SIGNOUT = "COD"
    PING = "P"  # Ping: Check, whether the other side is alive.
    # Component communication requests
    GET = "G"
    SET = "S"
    CALL = "C"
    OFF = "O"  # Turn off program
    CLEAR = "X"
    LOG = "L"  # configure log level
    LIST = "?"  # List options
    SAVE = "V"
    # Responses
    ACKNOWLEDGE = "A"  # Message received. Response is appended.
    ERROR = "E"  # An error occurred.
    # Deprecated
    DISCONNECT = "D"  # Deprecated, use SIGNOUT instead


class Errors(StrEnum):
    """Error messages for the control protocol."""

    # Routing errors (Coordinator)
    NOT_SIGNED_IN = "You did not sign in!"
    DUPLICATE_NAME = "The name is already taken."
    NODE_UNKNOWN = "Node is not known."
    RECEIVER_UNKNOWN = "Receiver is not in addresses list."
    # Data errors (Actors)
    NAME_NOT_FOUND = "The requested name is not known."  # name of a property or method.
    EXECUTION_FAILED = "Execution of the action failed."