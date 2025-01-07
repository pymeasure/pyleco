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
Names based on the classes of jsonrpc2-objects.

As jsonrpc2-objects uses pydantic models, these objects offer the `dump_model` and `dump_model_json`
methods.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass
import json
from typing import Any, List, Optional, TypeVar, Union

ErrorType = Union["DataError", "Error"]
NotificationType = Union["Notification", "ParamsNotification"]
RequestType = Union["ParamsRequest", "Request"]
ResponseType = Union["ErrorResponse", "ResultResponse"]


@dataclass
class JsonObject:
    def model_dump(self) -> dict[str, Any]:
        """Create a dictionary of the attributes."""
        return asdict(self)

    def model_dump_json(self) -> str:
        """Create a json representation."""
        return json.dumps(self.model_dump(), separators=(",", ":"))


@dataclass
class Request(JsonObject):
    """Request the result of a remote call."""

    id: Union[int, str]
    method: str
    jsonrpc: str = "2.0"


@dataclass
class ParamsRequest(JsonObject):
    """Request the result of a remote call with parameters."""

    id: Union[int, str]
    method: str
    params: Union[list, dict]
    jsonrpc: str = "2.0"


@dataclass
class Notification(JsonObject):
    """Do a remote call without requesting a response."""

    method: str
    jsonrpc: str = "2.0"


@dataclass
class ParamsNotification(JsonObject):
    """Do a remote call with parameters without requesting a response."""

    method: str
    params: Union[list, dict]
    jsonrpc: str = "2.0"


@dataclass
class ResultResponse(JsonObject):
    """A response containing a result."""

    id: Union[int, str]
    result: Any
    jsonrpc: str = "2.0"


@dataclass
class Error(JsonObject):
    """An error to be sent via an :class:`ErrorResponse`."""

    code: int
    message: str


@dataclass
class DataError(JsonObject):
    """An error with data, to be sent via an :class:`ErrorResponse`."""

    code: int
    message: str
    data: Any

    @classmethod
    def from_error(cls, error: Error, data: Any) -> DataError:
        return cls(code=error.code, message=error.message, data=data)


@dataclass
class ErrorResponse(JsonObject):
    """A response containing an error."""

    id: Optional[Union[int, str]]
    error: ErrorType
    jsonrpc: str = "2.0"

    def model_dump(self) -> dict[str, Any]:
        pre_dict = asdict(self)
        pre_dict["error"] = asdict(self.error)
        return pre_dict

"""
Batch Handling.

Not included in jsonrpc2-objects, but defined by JSONRPC 2.0
"""
BatchType = TypeVar("BatchType", RequestType, ResponseType)


class BatchObject(List[BatchType]):
    """A batch of JSONRPC message objects.

    It works like a list of appropriate message objects and offers the possibility to dump
    this batch object to a plain python object or to JSON.
    """
    # Parent class is typing.List, as Python<3.9 does not like list[BatchType]
    # Not defined by jsonrpc2-objects

    def model_dump(self) -> list[dict[str, Any]]:
        return [obj.model_dump() for obj in self]

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), separators=(",", ":"))


RequestBatch = BatchObject[RequestType]
ResponseBatch = BatchObject[ResponseType]
