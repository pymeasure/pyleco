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

import argparse
import os

from pyleco.core.security import generate_key_pair


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pyleco-keygen",
        description="Generate a Curve25519 key pair for LECO CURVE security.",
    )
    parser.add_argument("--output-dir", default=None, help="write key files to this directory")
    parser.add_argument("--name", default=None, help="name for key files (e.g. component name)")
    args = parser.parse_args()

    kp = generate_key_pair()
    public_key = kp.public_key
    secret_key = kp.secret_key

    print(f"Public key: {public_key}")
    print(f"Secret key: {secret_key}")

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        name = args.name or "key"
        pub_path = os.path.join(args.output_dir, f"{name}.public")
        sec_path = os.path.join(args.output_dir, f"{name}.secret")
        with open(pub_path, "w") as f:
            f.write(public_key + "\n")
        with open(sec_path, "w") as f:
            f.write(secret_key + "\n")
        os.chmod(sec_path, 0o600)
        print(f"Keys written to {pub_path} and {sec_path}")


if __name__ == "__main__":
    main()
