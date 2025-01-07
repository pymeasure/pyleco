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

from typing import Any
from warnings import warn

from .json_utils.json_objects import Error, DataError, ErrorResponse

from .json_utils.errors import NOT_SIGNED_IN, DUPLICATE_NAME, NODE_UNKNOWN, RECEIVER_UNKNOWN  # noqa


warn("The `pyleco.errors` module is deprecated, use the objects from the `pyleco.json_utils` "
     "subpackage instead.", FutureWarning)


def generate_error_with_data(error: Error, data: Any) -> DataError:
    """Generate a DataError from an Error.

    .. deprecated:: 0.3
        Use `DataError.from_error` instead.
    """
    return DataError.from_error(error=error, data=data)


class CommunicationError(ConnectionError):
    """Something went wrong, send an `error_msg` to the recipient.

    .. deprecated:: 0.3
        Use the definition in `communicator_utils` module instead.
    """

    def __init__(self, text: str, error_payload: ErrorResponse, *args: Any) -> None:
        super().__init__(text, *args)
        self.error_payload = error_payload
