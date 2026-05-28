from __future__ import annotations
#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2026 PyLECO Developers
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

from unittest.mock import patch

import pytest

from pyleco.core.security import KeyPair
from pyleco.utils.keygen import main


FAKE_PUBLIC = "a" * 40
FAKE_SECRET = "b" * 40


def _mock_key_pair():
    return KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET)


class TestKeygenMainWithoutOutputDir:
    @patch("pyleco.utils.keygen.generate_key_pair", _mock_key_pair)
    def test_prints_keys(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["pyleco-keygen"]):
            main()
        captured = capsys.readouterr()
        assert f"Public key: {FAKE_PUBLIC}" in captured.out
        assert f"Secret key: {FAKE_SECRET}" in captured.out


class TestKeygenMainWithOutputDir:
    @patch("pyleco.utils.keygen.generate_key_pair", _mock_key_pair)
    def test_writes_key_files(self, tmp_path: pytest.TempPath) -> None:
        with patch(
            "sys.argv",
            [
                "pyleco-keygen",
                "--output-dir",
                str(tmp_path),
                "--name",
                "test_component",
            ],
        ):
            main()
        pub_path = tmp_path / "test_component.public"
        sec_path = tmp_path / "test_component.secret"
        assert pub_path.exists()
        assert sec_path.exists()
        assert pub_path.read_text() == FAKE_PUBLIC + "\n"
        assert sec_path.read_text() == FAKE_SECRET + "\n"

    @patch("pyleco.utils.keygen.generate_key_pair", _mock_key_pair)
    def test_default_name_is_key(self, tmp_path: pytest.TempPath) -> None:
        with patch(
            "sys.argv",
            [
                "pyleco-keygen",
                "--output-dir",
                str(tmp_path),
            ],
        ):
            main()
        assert (tmp_path / "key.public").exists()
        assert (tmp_path / "key.secret").exists()

    @patch("pyleco.utils.keygen.generate_key_pair", _mock_key_pair)
    def test_creates_output_dir(self, tmp_path: pytest.TempPath) -> None:
        output_dir = tmp_path / "subdir" / "nested"
        with patch(
            "sys.argv",
            [
                "pyleco-keygen",
                "--output-dir",
                str(output_dir),
                "--name",
                "comp",
            ],
        ):
            main()
        assert (output_dir / "comp.public").exists()
        assert (output_dir / "comp.secret").exists()

    @patch("pyleco.utils.keygen.generate_key_pair", _mock_key_pair)
    def test_secret_key_file_restricted_permissions(self, tmp_path: pytest.TempPath) -> None:
        with patch(
            "sys.argv",
            [
                "pyleco-keygen",
                "--output-dir",
                str(tmp_path),
                "--name",
                "test",
            ],
        ):
            main()
        sec_path = tmp_path / "test.secret"
        mode = sec_path.stat().st_mode & 0o777
        assert mode == 0o600
