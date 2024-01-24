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

from typing import Any

from jsonrpcobjects.objects import Error, DataError, ErrorResponse

# JSON specification:
# -32000 to -32099  Server error    reserved for implementation-defined server-errors

# TODO define valid error codes: Proposal:
# general error: -32000
# Routing errors (Coordinator) between -32090 and -32099
NOT_SIGNED_IN = Error(code=-32090, message="You did not sign in!")
DUPLICATE_NAME = Error(code=-32091, message="The name is already taken.")
NODE_UNKNOWN = Error(code=-32092, message="Node is not known.")
RECEIVER_UNKNOWN = Error(code=-32093, message="Receiver is not in addresses list.")


def generate_error_with_data(error: Error, data: Any) -> DataError:
    return DataError(code=error.code, message=error.message, data=data)


class CommunicationError(ConnectionError):
    """Something went wrong, send an `error_msg` to the recipient."""

    def __init__(self, text: str, error_payload: ErrorResponse, *args: Any) -> None:
        super().__init__(text, *args)
        self.error_payload = error_payload
