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

"""
Based on jsonrpc2-objects

This module provides exceptions for each JSON-RPC 2.0 error.

There is one Exception defined for each pre-defined JSON-RPC 2.0 error.
Additionally, there is a ServerError for implementation-defined errors.

Each exception extends a base exception JSONRPCError.
"""


from typing import Optional, Type

from .json_objects import DataError, Error, ErrorType

# JSONRPC 2.0 defined errors
INVALID_REQUEST = Error(code=-32600, message="Invalid Request")
METHOD_NOT_FOUND = Error(code=-32601, message="Method not found")
INVALID_PARAMS = Error(code=-32602, message="Invalid params")
INTERNAL_ERROR = Error(code=-32603, message="Internal error")
PARSE_ERROR = Error(code=-32700, message="Parse error")

# -32000 to -32099  Server error    reserved for implementation-defined server-errors
# general error: -32000
SERVER_ERROR = Error(code=-32000, message="Server error")

# LECO defined errors
# Routing errors (Coordinator) between -32090 and -32099
NOT_SIGNED_IN = Error(code=-32090, message="You did not sign in!")
DUPLICATE_NAME = Error(code=-32091, message="The name is already taken.")
NODE_UNKNOWN = Error(code=-32092, message="Node is not known.")
RECEIVER_UNKNOWN = Error(code=-32093, message="Receiver is not in addresses list.")

# Error during deserialization error of the server's response
INVALID_SERVER_RESPONSE = Error(code=-32000, message="Invalid response from server.")


class JSONRPCError(Exception):
    """Base error that all JSON RPC exceptions extend."""

    def __init__(self, error: ErrorType) -> None:
        msg = f"{error.code}: {error.message}"
        self.rpc_error = error
        if isinstance(error, DataError):
            msg += f"\nError Data: {error.data}"
        super().__init__(msg)


class ParseError(JSONRPCError):
    """Error raised when invalid JSON was received by the server."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super().__init__(error or PARSE_ERROR)


class InvalidRequest(JSONRPCError):
    """Error raised when the JSON sent is not a valid Request object."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super().__init__(error or INVALID_REQUEST)


class MethodNotFound(JSONRPCError):
    """Error raised when the method does not exist / is not available."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super().__init__(error or METHOD_NOT_FOUND)


class InvalidParams(JSONRPCError):
    """Error raised when invalid method parameter(s) are supplied."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super().__init__(error or INVALID_PARAMS)


class InternalError(JSONRPCError):
    """Error raised when there is an internal JSON-RPC error."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super().__init__(error or INTERNAL_ERROR)


class ServerError(JSONRPCError):
    """Error raised when a server error occurs."""

    def __init__(self, error: ErrorType) -> None:
        super().__init__(error)


def get_exception_by_code(code: int) -> Optional[Type[JSONRPCError]]:
    """Get the JSON-RPC error corresponding to an error code.

    :param code: The JSON-RPC error code.
    :return: JSON RPC error object or None.
    """
    return {
        -32600: InvalidRequest,
        -32601: MethodNotFound,
        -32602: InvalidParams,
        -32603: InternalError,
        -32700: ParseError,
    }.get(code)
