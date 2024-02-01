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

from typing import Any, Union

from jsonrpc2pyclient._irpcclient import IRPCClient  # type: ignore
from jsonrpcobjects.objects import Error


# according to error raised by IRPCClient if decoding fails.
INVALID_SERVER_RESPONSE = Error(code=-32000, message="Invalid response from server.")


class RPCGenerator(IRPCClient):
    """Builds and interprets json rpc messages."""

    # TODO it stores an always growing list of "id"s, if you do not call "get_result".

    def build_request_str(self, method: str, *args, **kwargs) -> str:
        if args and kwargs:
            raise ValueError(
                "You may not specify list of positional arguments "
                "and give additional keyword arguments at the same time.")
        return self._build_request(method=method, params=kwargs or list(args) or None
                                   ).model_dump_json()

    def get_result_from_response(self, data: Union[bytes, str]) -> Any:
        """Get the result of that object or raise an error."""
        return self._get_result_from_response(data=data)

    def clear_id_list(self) -> None:
        """Reset the list of created ids."""
        self._ids: dict[int, int] = {}
