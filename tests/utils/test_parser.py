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

import logging

import pytest

from pyleco.utils.parser import parser, parse_command_line_parameters


class Test_parse_command_line_parameters:
    @pytest.fixture
    def parsed_kwargs(self):
        self.parser = parser
        return parse_command_line_parameters(parser=self.parser,
                                             arguments=["-v", "--name", "name_value", "-v"],
                                             parser_description="Some description",
                                             logging_default=logging.WARNING
                                             )

    def test_parser_description(self, parsed_kwargs):
        assert self.parser.description == "Some description"

    def test_kwargs(self, parsed_kwargs):
        assert parsed_kwargs == {'name': "name_value"}

    def test_logging_level(self, parsed_kwargs):
        assert logging.getLogger("__main__").level == logging.DEBUG
