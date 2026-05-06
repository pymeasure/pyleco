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

from argparse import ArgumentParser
import logging
from typing import TYPE_CHECKING

from pyleco.core.security import load_security_config

if TYPE_CHECKING:
    from pyleco.core.security import SecurityConfig


parser = ArgumentParser()
parser.add_argument("-r", "--host", help="set the host name of this Node's Coordinator")
parser.add_argument("-n", "--name", help="set the application name")
parser.add_argument(
    "-q",
    "--quiet",
    action="count",
    default=0,
    help="decrease the logging level by one, may be used more than once",
)
parser.add_argument(
    "-v",
    "--verbose",
    action="count",
    default=0,
    help="increase the logging level by one, may be used more than once",
)
parser.add_argument(
    "--security-mode", choices=["NONE", "CURVE"], default=None, help="security mode (default: NONE)"
)
parser.add_argument("--server-secret-key", default=None, help="server secret key for CURVE mode")
parser.add_argument(
    "--server-public-key", default=None, help="server public key (for client-side configuration)"
)
parser.add_argument("--client-secret-key", default=None, help="client secret key for CURVE mode")
parser.add_argument("--client-public-key", default=None, help="client public key for CURVE mode")
parser.add_argument(
    "--data-server-public-key", default=None, help="proxy server public key for data protocol"
)
parser.add_argument(
    "--authorized-keys-dir", default=None, help="directory of authorized client public keys"
)
parser.add_argument(
    "--curve-any-authenticated",
    action="store_true",
    default=None,
    help="accept any authenticated CURVE client",
)
parser.add_argument("--config", default=None, help="path to TOML config file")


def parse_command_line_parameters(
    parser: ArgumentParser = parser,
    logger: logging.Logger | None = None,
    arguments: list[str] | None = None,
    parser_description: str | None = None,
    logging_default: int = logging.WARNING,
) -> dict:
    """Parse the command line parameters and return a dictionary for GUIs.

    :param parser: parser to use, for example with more settings.
    :param logger: The logger whose log level to set. Defaults to "__main__" logger.
    :param list arguments: Arguments for the parser to parse. Per default, take it from `sys.argv`.
    :param str parser_description: Override the parsers program description description.
    :param int logging_default: Default level for logging.
    :return: Dictionary with keyword arguments parsed from the command line parameters.
    """
    if parser_description is not None:
        parser.description = parser_description
    kwargs = vars(parser.parse_args(arguments))
    verbosity = logging_default + (kwargs.pop("quiet", 0) - kwargs.pop("verbose", 0)) * 10
    if logger is None:
        logger = logging.getLogger("__main__")
    logger.setLevel(verbosity)
    for key, value in list(kwargs.items()):
        if value is None:
            del kwargs[key]
    return kwargs


_SECURITY_KWARG_KEYS = (
    "security_mode",
    "server_secret_key",
    "server_public_key",
    "client_secret_key",
    "client_public_key",
    "data_server_public_key",
    "authorized_keys_dir",
    "curve_any_authenticated",
)


def build_security_config_from_kwargs(kwargs: dict) -> SecurityConfig:
    config_path = kwargs.pop("config", None)
    cli_security_args: dict = {}
    for key in _SECURITY_KWARG_KEYS:
        value = kwargs.pop(key, None)
        if value is not None:
            cli_key = key
            if key == "security_mode":
                cli_key = "mode"
            cli_security_args[cli_key] = value
    return load_security_config(config_path=config_path, cli_args=cli_security_args)
