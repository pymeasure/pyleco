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

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef,import-not-found]
    except ImportError:
        raise ImportError(
            "TOML support requires tomli for Python < 3.11. Install it: pip install tomli"
        )

__all__ = [
    "find_config_file",
    "load_config",
]

_DEFAULT_SEARCH_PATHS: list[str] = [
    "./pyleco.toml",
    "~/.pyleco.toml",
    "/etc/pyleco/pyleco.toml",
]


def _load_toml(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def find_config_file(search_paths: list[str] | None = None) -> str | None:
    paths = search_paths if search_paths is not None else _DEFAULT_SEARCH_PATHS
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            return str(p)
    return None


def load_config(path: str | None = None, search_paths: list[str] | None = None) -> dict:
    if path is not None:
        return _load_toml(path)
    found = find_config_file(search_paths=search_paths)
    if found is None:
        return {}
    return _load_toml(found)
