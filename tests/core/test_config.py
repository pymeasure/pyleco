from __future__ import annotations

from unittest.mock import patch

import pytest

from pyleco.core.config import find_config_file, load_config


class TestFindConfigFile:
    def test_returns_none_when_no_files_exist(self, tmp_path: pytest.TempPath) -> None:
        search = [str(tmp_path / "a.toml"), str(tmp_path / "b.toml")]
        assert find_config_file(search_paths=search) is None

    def test_returns_first_found_file(self, tmp_path: pytest.TempPath) -> None:
        f1 = tmp_path / "a.toml"
        f2 = tmp_path / "b.toml"
        f1.write_text("[test]\nkey = 1\n")
        f2.write_text("[test]\nkey = 2\n")
        search = [str(f1), str(f2)]
        result = find_config_file(search_paths=search)
        assert result == str(f1)

    def test_returns_second_if_first_missing(self, tmp_path: pytest.TempPath) -> None:
        f2 = tmp_path / "b.toml"
        f2.write_text("[test]\nkey = 1\n")
        search = [str(tmp_path / "a.toml"), str(f2)]
        result = find_config_file(search_paths=search)
        assert result == str(f2)

    def test_default_search_paths_with_no_files(self, tmp_path: pytest.TempPath) -> None:
        with patch("pyleco.core.config._DEFAULT_SEARCH_PATHS", []):
            assert find_config_file() is None

    def test_expands_user_home(self, tmp_path: pytest.TempPath) -> None:
        f = tmp_path / "pyleco.toml"
        f.write_text("[test]\n")
        with patch("pyleco.core.config._DEFAULT_SEARCH_PATHS", [str(f)]):
            result = find_config_file()
            assert result == str(f)


class TestLoadConfig:
    def test_load_specific_path(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "pyleco.toml"
        toml_file.write_text('[security]\nmode = "CURVE"\n')
        result = load_config(path=str(toml_file))
        assert result == {"security": {"mode": "CURVE"}}

    def test_returns_empty_dict_when_no_file_found(self, tmp_path: pytest.TempPath) -> None:
        search = [str(tmp_path / "missing.toml")]
        result = load_config(search_paths=search)
        assert result == {}

    def test_toml_content_parsed_correctly(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "pyleco.toml"
        toml_file.write_text(
            '[security]\nmode = "CURVE"\n'
            'server_public_key = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
            'server_secret_key = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n'
            "[security.authorized_keys]\n"
            '"N1.Actor1" = "cccccccccccccccccccccccccccccccccccccccc"\n'
        )
        result = load_config(path=str(toml_file))
        assert result["security"]["mode"] == "CURVE"
        assert result["security"]["server_public_key"] == "a" * 40
        assert result["security"]["authorized_keys"]["N1.Actor1"] == "c" * 40

    def test_load_from_search_paths(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "pyleco.toml"
        toml_file.write_text('[security]\nmode = "NONE"\n')
        search = [str(toml_file)]
        result = load_config(search_paths=search)
        assert result == {"security": {"mode": "NONE"}}

    def test_load_first_from_search_paths(self, tmp_path: pytest.TempPath) -> None:
        f1 = tmp_path / "a.toml"
        f2 = tmp_path / "b.toml"
        f1.write_text('[section]\nkey = "first"\n')
        f2.write_text('[section]\nkey = "second"\n')
        search = [str(f1), str(f2)]
        result = load_config(search_paths=search)
        assert result["section"]["key"] == "first"
