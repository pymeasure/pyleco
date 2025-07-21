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
from typing import Optional

import pytest

from pyleco.core.message import Message, MessageTypes
from pyleco.utils.rpc_handler import RpcHandler
from pyleco.json_utils.json_objects import ResultResponse, ParamsRequest


@pytest.fixture
def handler() -> RpcHandler:
    return RpcHandler()

def test_handle_binary_return_value(handler: RpcHandler):
    payload = [b"abc", b"def"]
    result = handler._handle_binary_return_value((None, payload))
    assert result is None
    assert handler.additional_response_payload == payload


class Test_generate_binary_method:
    @pytest.fixture
    def binary_method(self):
        def binary_method(index: int, additional_payload: list[bytes]) -> tuple[None, list[bytes]]:
            """Docstring of binary method."""
            return None, [additional_payload[index]]
        return binary_method

    @pytest.fixture(params=(True, False))
    def modified_binary_method(self, handler: RpcHandler, binary_method, request):
        handler.current_message = Message(
            "rec", "send", data=b"", additional_payload=[b"0", b"1", b"2", b"3"]
        )
        self._accept_binary_input = request.param
        mod = handler._generate_binary_capable_method(
            binary_method, accept_binary_input=self._accept_binary_input, return_binary_output=True
        )
        self.handler = handler
        return mod

    def test_name(self, binary_method, modified_binary_method):
        assert modified_binary_method.__name__ == binary_method.__name__

    def test_docstring(self, modified_binary_method, binary_method):
        doc_addition = (
            "(binary input output method)"
            if self._accept_binary_input
            else "(binary output method)"
        )
        assert modified_binary_method.__doc__ == binary_method.__doc__ + "\n" + doc_addition

    @pytest.mark.parametrize(
        "input, output, string",
        (
            (False, False, "(binary method)"),
            (True, False, "(binary input method)"),
            (False, True, "(binary output method)"),
            (True, True, "(binary input output method)"),
        ),
    )
    def test_docstring_without_original_docstring(
        self, handler: RpcHandler, input, output, string
    ):
        def binary_method(additional_payload):
            return 7
        mod = handler._generate_binary_capable_method(
            binary_method, accept_binary_input=input, return_binary_output=output
        )
        assert mod.__doc__ == string

    def test_annotation(self, modified_binary_method, binary_method):
        assert modified_binary_method.__annotations__ == binary_method.__annotations__

    def test_functionality_kwargs(self, modified_binary_method):
        if self._accept_binary_input:
            assert modified_binary_method(index=1) is None
        else:
            assert (
                modified_binary_method(index=1, additional_payload=[b"0", b"1", b"2", b"3"]) is None
            )
        assert self.handler.additional_response_payload == [b"1"]

    def test_functionality_args(self, modified_binary_method):
        if self._accept_binary_input:
            assert modified_binary_method(1) is None
        else:
            assert modified_binary_method(1, [b"0", b"1", b"2", b"3"]) is None
        assert self.handler.additional_response_payload == [b"1"]

    def test_binary_input_from_message(self, handler: RpcHandler):
        handler.current_message = Message("rec", "send", data=b"", additional_payload=[b"0"])

        def binary_method(additional_payload = None):
            return 7
        mod = handler._generate_binary_capable_method(
            binary_method, accept_binary_input=True, return_binary_output=False
        )
        assert mod() == 7


class Test_process_json_message_with_created_binary:
    payload_in: list[bytes]
    payload_out: list[bytes]

    @pytest.fixture(
        params=(
            # normally created binary method
            {"method": "do_binary", "params": [5]},  # with a list
            {"method": "do_binary", "params": [5, None]},  # with a list with None
            {"method": "do_binary", "params": {"data": 5}},  # a dictionary
            # manually created binary method
            {"method": "do_binary_manually", "params": [5]},
            {"method": "do_binary_manually", "params": {"data": 5}},
        ),
        ids=(
            "created, list",
            "created, list with None",
            "created, dict",
            "manual, list",
            "manual, dict",
        ),
    )
    def data(self, request) -> ParamsRequest:
        """Create a request with a list and a dict of other parameters."""
        return ParamsRequest(8, **request.param)

    @pytest.fixture
    def handler_b(self, handler: RpcHandler):
        test_class = self
        class SpecialHandler(RpcHandler):
            def do_binary_manually(self, data: int) -> int:
                test_class.payload_in = self.current_message.payload[1:]
                self.additional_response_payload = test_class.payload_out
                return data

            def do_binary(
                self, data: int, additional_payload: Optional[list[bytes]] = None
            ) -> tuple[int, list[bytes]]:
                test_class.payload_in = additional_payload  # type: ignore
                return data, test_class.payload_out

        handler = SpecialHandler(title="abc")  # type: ignore

        handler.register_rpc_method(handler.do_binary_manually)
        handler.register_binary_rpc_method(
            handler.do_binary, accept_binary_input=True, return_binary_output=True
        )
        return handler

    def test_message_stored(self, handler_b: RpcHandler, data):
        m_in = Message("abc", data=data, message_type=MessageTypes.JSON)
        handler_b.process_request(m_in)
        assert handler_b.current_message == m_in

    def test_empty_additional_payload(self, handler_b: RpcHandler, data):
        m_in = Message("abc", data=data, message_type=MessageTypes.JSON)
        handler_b.process_request(m_in)
        assert handler_b.additional_response_payload is None

    def test_binary_payload_available(self, handler_b: RpcHandler, data):
        m_in = Message(
            "abc", data=data, message_type=MessageTypes.JSON, additional_payload=[b"def"]
        )
        self.payload_out = []
        handler_b.process_request(m_in)
        assert self.payload_in == [b"def"]

    def test_binary_payload_sent(self, handler_b: RpcHandler, data):
        m_in = Message("abc", data=data, message_type=MessageTypes.JSON)
        self.payload_out = [b"ghi"]
        response = handler_b.process_request(m_in)
        assert isinstance(response, Message)
        assert response.payload[1:] == [b"ghi"]
        assert response.data == ResultResponse(8, 5).model_dump()
