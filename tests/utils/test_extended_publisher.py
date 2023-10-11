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

import pytest

from pyleco.test import FakeContext

try:
    import numpy as np  # type: ignore
    import pint  # type: ignore
except ModuleNotFoundError:
    pytest.skip("Numpy or pint is not installed", allow_module_level=True)
else:
    from pyleco.utils.extended_publisher import ExtendedPublisher, PowerEncoder


ureg = pint.UnitRegistry()


@pytest.fixture
def publisher() -> ExtendedPublisher:
    return ExtendedPublisher(host="localhost", context=FakeContext())  # type: ignore


class Test_PowerEncoder:
    @pytest.fixture
    def encoder(self) -> PowerEncoder:
        return PowerEncoder()

    def test_numpy_number(self, encoder):
        assert encoder.encode(np.array((5, 7.5), dtype=np.float16)) == "[5.0, 7.5]"

    def test_pint(self, encoder):
        assert encoder.encode(5 * ureg.cm) == '"5 cm"'

    def test_combination(self, encoder):
        assert encoder.encode([np.array((5, 7.5), dtype=np.float16), 7.25 * ureg.km,
                               9]) == '[[5.0, 7.5], "7.25 km", 9]'
