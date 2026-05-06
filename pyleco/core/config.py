from __future__ import annotations

from pathlib import Path
from typing import Optional

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
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            raise ImportError(
                "TOML support requires tomli for Python < 3.11. "
                "Install it: pip install tomli"
            )
    with open(path, "rb") as f:
        return tomllib.load(f)


def find_config_file(search_paths: Optional[list[str]] = None) -> Optional[str]:
    paths = search_paths if search_paths is not None else _DEFAULT_SEARCH_PATHS
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            return str(p)
    return None


def load_config(path: Optional[str] = None, search_paths: Optional[list[str]] = None) -> dict:
    if path is not None:
        return _load_toml(path)
    found = find_config_file(search_paths=search_paths)
    if found is None:
        return {}
    return _load_toml(found)
