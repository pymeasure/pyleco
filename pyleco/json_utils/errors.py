"""This module provides exceptions for each JSON-RPC 2.0 error.

There is one Exception defined for each pre-defined JSON-RPC 2.0 error.
Additionally, there is a ServerError for implementation-defined errors.

Each exception extends a base exception JSONRPCError.

Copied from jsonrpc2-objects
"""

__all__ = (
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "InternalError",
    "InvalidParams",
    "InvalidRequest",
    "JSONRPCError",
    "METHOD_NOT_FOUND",
    "MethodNotFound",
    "PARSE_ERROR",
    "ParseError",
    "ServerError",
    "get_exception_by_code",
)

from typing import Optional, Type

from .json_objects import DataError, Error, ErrorType

SERVER_ERROR = Error(code=-32000, message="Server error")
INVALID_REQUEST = Error(code=-32600, message="Invalid Request")
METHOD_NOT_FOUND = Error(code=-32601, message="Method not found")
INVALID_PARAMS = Error(code=-32602, message="Invalid params")
INTERNAL_ERROR = Error(code=-32603, message="Internal error")
PARSE_ERROR = Error(code=-32700, message="Parse error")


class JSONRPCError(Exception):
    """Base error that all JSON RPC exceptions extend."""

    def __init__(self, error: ErrorType) -> None:
        msg = f"{error.code}: {error.message}"
        self.rpc_error = error
        if isinstance(error, DataError):
            msg += f"\nError Data: {error.data}"
        super(JSONRPCError, self).__init__(msg)


class ParseError(JSONRPCError):
    """Error raised when invalid JSON was received by the server."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super(ParseError, self).__init__(error or PARSE_ERROR)


class InvalidRequest(JSONRPCError):
    """Error raised when the JSON sent is not a valid Request object."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super(InvalidRequest, self).__init__(error or INVALID_REQUEST)


class MethodNotFound(JSONRPCError):
    """Error raised when the method does not exist / is not available."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super(MethodNotFound, self).__init__(error or METHOD_NOT_FOUND)


class InvalidParams(JSONRPCError):
    """Error raised when invalid method parameter(s) are supplied."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super(InvalidParams, self).__init__(error or INVALID_PARAMS)


class InternalError(JSONRPCError):
    """Error raised when there is an internal JSON-RPC error."""

    def __init__(self, error: Optional[ErrorType] = None) -> None:
        super(InternalError, self).__init__(error or INTERNAL_ERROR)


class ServerError(JSONRPCError):
    """Error raised when a server error occurs."""

    def __init__(self, error: ErrorType) -> None:
        super(ServerError, self).__init__(error)


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
