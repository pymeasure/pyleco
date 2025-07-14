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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, List, Optional, Sequence, TypeVar, Union
from warnings import warn

ErrorType = Union["DataError", "Error", "JsonRpcError"]
NotificationType = Union["Notification", "ParamsNotification"]
RequestType = Union[
    "ParamsRequest", "Request", "ParamsNotification", "Notification", "JsonRpcRequest"
]
ResponseType = Union["ErrorResponse", "ResultResponse", "JsonRpcResponse"]


class JsonRpcBase(ABC):
    """Any JSON-RPC 2.0 message object."""

    @abstractmethod
    def model_dump(self) -> dict[str, Any]:
        """Return a plain Python dictionary representation."""
        ...  # pragma: nocover

    def model_dump_json(self) -> str:
        """Return JSON string representation."""
        return json.dumps(self.model_dump(), separators=(",", ":"))


# for backward compatibility
JsonObject = JsonRpcBase


@dataclass
class JsonRpcRequest(JsonRpcBase):
    """JSON-RPC 2.0 Request message."""

    method: str
    params: Optional[Union[list[Any], dict[str, Any]]] = None
    id: Optional[Union[str, int]] = None
    jsonrpc: str = field(default="2.0", init=True)

    def __post_init__(self):
        """Validate the request after initialization"""
        if not isinstance(self.method, str) or not self.method:
            raise ValueError("Method must be a non-empty string")

        if self.params is not None and not isinstance(self.params, (list, dict)):
            raise ValueError("Params must be a list, dict, or None")

        if self.id is not None and not isinstance(self.id, (str, int)):
            raise ValueError("ID must be a string, int, or None")

    @property
    def is_notification(self) -> bool:
        """Check if this is a notification (no id field)."""
        return self.id is None

    def model_dump(self) -> dict[str, Any]:
        """Return a plain Python dictionary representation."""
        result: dict[str, Any] = {}
        if self.id is not None:
            result["id"] = self.id
        result["method"] = self.method
        if self.params is not None:
            result["params"] = self.params
        result["jsonrpc"] = self.jsonrpc
        return result


@dataclass
class Request(JsonRpcRequest):
    """Request the result of a remote call."""

    def __init__(self, id: Union[int, str], method: str, jsonrpc: str = "2.0"):
        super().__init__(id=id, method=method, params=None, jsonrpc=jsonrpc)


@dataclass
class ParamsRequest(JsonRpcRequest):
    """Request the result of a remote call with parameters."""

    def __init__(
        self, id: Union[int, str], method: str, params: Union[list, dict], jsonrpc: str = "2.0"
    ):
        super().__init__(id=id, method=method, params=params, jsonrpc=jsonrpc)


@dataclass
class Notification(JsonRpcRequest):
    """Do a remote call without requesting a response."""

    def __init__(self, method: str, jsonrpc: str = "2.0"):
        super().__init__(id=None, method=method, params=None, jsonrpc=jsonrpc)


@dataclass
class ParamsNotification(JsonRpcRequest):
    """Do a remote call with parameters without requesting a response."""

    def __init__(self, method: str, params: Union[list, dict], jsonrpc: str = "2.0"):
        super().__init__(id=None, method=method, params=params, jsonrpc=jsonrpc)


@dataclass
class JsonRpcResponse(JsonRpcBase):
    """JSON-RPC 2.0 Response message."""

    id: Optional[Union[str, int]]
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None
    jsonrpc: str = field(default="2.0", init=True)

    def __post_init__(self):
        """Validate the response after initialization."""
        if self.result is not None and self.error is not None:
            raise ValueError("Response cannot have both result and error")

        if self.id is not None and not isinstance(self.id, (str, int)):
            raise ValueError("ID must be a string, int, or None")

        if self.error is not None and not isinstance(self.error, JsonRpcError):
            raise ValueError("Error must be a JsonRpcError instance")

    def model_dump(self) -> dict[str, Any]:
        """Return a plain Python dictionary representation."""
        result: dict[str, Any] = {"id": self.id}
        if self.error is not None:
            result["error"] = self.error.model_dump()
        else:
            result["result"] = self.result
        result["jsonrpc"] = self.jsonrpc
        return result


@dataclass
class ResultResponse(JsonRpcResponse):
    """A response containing a result."""

    def __init__(self, id: Optional[Union[int, str]], result: Any, jsonrpc: str = "2.0"):
        super().__init__(id=id, result=result, jsonrpc=jsonrpc)


@dataclass
class JsonRpcError(JsonRpcBase):
    """JSON-RPC 2.0 Error object."""

    code: int
    message: str
    data: Optional[Any] = None

    def __post_init__(self):
        """Validate the error after initialization."""
        if not isinstance(self.code, int):
            raise ValueError("Error code must be an integer")
        if not isinstance(self.message, str):
            raise ValueError("Error message must be a string")

    def model_dump(self) -> dict[str, Any]:
        """Return a plain Python dictionary representation."""
        result = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result

    def with_data(self, data: Any) -> JsonRpcError:
        return self.from_error(self, data=data)

    @classmethod
    def from_error(cls, error: JsonRpcError, data: Any) -> JsonRpcError:
        return cls(code=error.code, message=error.message, data=data)


@dataclass
class Error(JsonRpcError):
    """An error to be sent via an :class:`ErrorResponse`."""

    def __init__(self, code: int, message: str):
        super().__init__(code=code, message=message)


@dataclass
class DataError(JsonRpcError):
    """An error with data, to be sent via an :class:`ErrorResponse`."""

    def __init__(self, code: int, message: str, data: Any):
        super().__init__(code=code, message=message, data=data)


@dataclass
class ErrorResponse(JsonRpcResponse):
    """A response containing an error."""

    def __init__(
        self,
        id: Optional[Union[int, str]],
        error: ErrorType,
        jsonrpc: str = "2.0",
    ):
        super().__init__(id=id, error=error, jsonrpc=jsonrpc)


class BatchContentType(Enum):
    REQUESTS = "requests"
    RESPONSES = "responses"
    MIXED = "mixed"


@dataclass
class JsonRpcBatch:
    """JSON-RPC 2.0 Batch request/response."""

    items: Sequence[Union[JsonRpcRequest, JsonRpcResponse]]

    def __post_init__(self):
        """Validate the batch after initialization"""
        if not isinstance(self.items, list) or len(self.items) == 0:
            raise ValueError("Batch must contain at least one item")

        for item in self.items:
            if not isinstance(item, (JsonRpcRequest, JsonRpcResponse)):
                raise ValueError("All batch items must be JsonRpcRequest or JsonRpcResponse")

    @property
    def batch_type(self) -> BatchContentType:
        if all([isinstance(item, JsonRpcRequest) for item in self.items]):
            return BatchContentType.REQUESTS
        elif all([isinstance(item, JsonRpcResponse) for item in self.items]):
            return BatchContentType.RESPONSES
        else:
            return BatchContentType.MIXED

    @property
    def is_request_batch(self) -> bool:
        """Check if batch contains only requests"""
        return self.batch_type == BatchContentType.REQUESTS

    @property
    def is_response_batch(self) -> bool:
        """Check if batch contains only responses"""
        return self.batch_type == BatchContentType.RESPONSES

    @property
    def is_mixed_batch(self) -> bool:
        """Check if batch contains mixed requests and responses"""
        return self.batch_type == BatchContentType.MIXED

    @property
    def requests(self) -> list[JsonRpcRequest]:
        """Get all requests from the batch"""
        return [item for item in self.items if isinstance(item, JsonRpcRequest)]

    @property
    def responses(self) -> list[JsonRpcResponse]:
        """Get all responses from the batch"""
        return [item for item in self.items if isinstance(item, JsonRpcResponse)]

    @property
    def notifications(self) -> list[JsonRpcRequest]:
        """Get all notifications (requests without id) from the batch"""
        return [
            item for item in self.items if isinstance(item, JsonRpcRequest) and item.is_notification
        ]

    def get_request_by_id(self, request_id: Union[str, int]) -> Optional[JsonRpcRequest]:
        """Find a request by its ID"""
        for item in self.items:
            if isinstance(item, JsonRpcRequest) and item.id == request_id:
                return item
        return None

    def get_response_by_id(self, response_id: Union[str, int]) -> Optional[JsonRpcResponse]:
        """Find a response by its ID"""
        for item in self.items:
            if isinstance(item, JsonRpcResponse) and item.id == response_id:
                return item
        return None

    def model_dump(self) -> list[dict[str, Any]]:
        """Return list of dictionaries for batch"""
        return [item.model_dump() for item in self.items]

    def model_dump_json(self) -> str:
        """Return JSON string representation of batch"""
        return json.dumps(self.model_dump(), separators=(",", ":"))


BatchType = TypeVar("BatchType", RequestType, ResponseType)


class BatchObject(List[BatchType]):
    """A batch of JSONRPC message objects.

    .. deprecated:: 0.6.0
        Use the :class:`JsonRpcBatch` class instead.

    It works like a list of appropriate message objects and offers the possibility to dump
    this batch object to a plain python object or to JSON.
    """

    def __init__(self, *args, **kwargs) -> None:
        warn("The `BatchObject` is deprecated, use a `JsonRpcBatch` instead.", FutureWarning)
        return super().__init__(*args, **kwargs)

    def model_dump(self) -> list[dict[str, Any]]:
        return [obj.model_dump() for obj in self]

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), separators=(",", ":"))


class RequestBatch(BatchObject[RequestType]):
    pass


class ResponseBatch(BatchObject[ResponseType]):
    pass
