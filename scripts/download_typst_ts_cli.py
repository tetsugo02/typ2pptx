#!/usr/bin/env python3
"""Download typst-ts-cli binary for the current (or specified) platform.

Usage:
    python scripts/download_typst_ts_cli.py              # auto-detect platform
    python scripts/download_typst_ts_cli.py --target x86_64-unknown-linux-gnu
    python scripts/download_typst_ts_cli.py --version v0.6.0

The implementation lives in typ2pptx/typst_ts_cli.py (standard library only),
which typ2pptx also uses to download the binary on first run when it is not
bundled. This script works before the package's dependencies are installed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Import the module by path so that typ2pptx's dependencies are not needed.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from typ2pptx.typst_ts_cli import DEFAULT_VERSION, download_typst_ts_cli  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Download typst-ts-cli binary for bundling with typ2pptx",
    )
    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"typst.ts release version (default: {DEFAULT_VERSION})",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Rust target triple (default: auto-detect)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: typ2pptx/data/bin/)",
    )
    args = parser.parse_args()

    try:
        download_typst_ts_cli(
            version=args.version,
            target=args.target,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
