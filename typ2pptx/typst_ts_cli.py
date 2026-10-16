"""Locate or download the typst-ts-cli binary.

Platform wheels bundle typst-ts-cli in ``typ2pptx/data/bin/``. Installs
without it (sdist, ``pip install git+...``) fall back to ``PATH`` and then
download the pinned release once into a per-user cache.

Only the standard library is used, so ``scripts/download_typst_ts_cli.py``
can run before the package's dependencies are installed.

Environment variables:
    TYP2PPTX_CACHE_DIR       Cache directory (default: platform user cache)
    TYP2PPTX_NO_DOWNLOAD     Set to 1 to never download automatically
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

GITHUB_RELEASE_URL = "https://github.com/Myriad-Dreamin/typst.ts/releases/download"

DEFAULT_VERSION = "v0.7.0-rc2"

PLATFORM_MAP = {
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("Linux", "armv7l"): "arm-unknown-linux-gnueabihf",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Windows", "x86"): "i686-pc-windows-msvc",
    ("Windows", "ARM64"): "aarch64-pc-windows-msvc",
}

# SHA-256 of the release archives, from the GitHub release asset digests.
# Other versions / targets are checked against the release's .sha256 files.
ARCHIVE_SHA256 = {
    ("v0.7.0-rc2", "aarch64-apple-darwin"):
        "998198f477efdb209938a76b787220bf09835ecfbb076e96fc389a5eaf8814de",
    ("v0.7.0-rc2", "x86_64-apple-darwin"):
        "06a9672fb77f2aa55f93190084d108abf6b040d5257403ab90ba8ae5e6c17596",
    ("v0.7.0-rc2", "x86_64-unknown-linux-gnu"):
        "dd2fb2b50d3f0c6d6620c45997225e0f899a41c31a331eb51a05ec762d972ccc",
    ("v0.7.0-rc2", "aarch64-unknown-linux-gnu"):
        "a1f489e8d52aefdc72cb4da2846566cb9d8adf49b6c5517c8ba896912e93e907",
    ("v0.7.0-rc2", "arm-unknown-linux-gnueabihf"):
        "fd11d50f36f076883b5fb058b62de02e8a47907f0e185cf2bf9836500a95d17a",
    ("v0.7.0-rc2", "x86_64-pc-windows-msvc"):
        "46f77fc4d16a44a40802839490db1b48756f24ee0fd8bdf554ec0b2c30e3fe38",
    ("v0.7.0-rc2", "aarch64-pc-windows-msvc"):
        "f04ef5591f357bafc8c89ad743ba707304454d7241c3f032a8dffa072f780aee",
}


def _bundled_dir() -> Path:
    return Path(__file__).resolve().parent / "data" / "bin"


def detect_target() -> str:
    """Detect the Rust-style target triple for the current platform."""
    system = platform.system()
    machine = platform.machine()

    target = PLATFORM_MAP.get((system, machine))
    if target is None:
        raise RuntimeError(
            f"Unsupported platform: {system}/{machine}. "
            f"Supported: {list(PLATFORM_MAP.keys())}"
        )
    return target


def _binary_name(target: str) -> str:
    return "typst-ts-cli.exe" if "windows" in target else "typst-ts-cli"


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


def _expected_sha256(version: str, target: str, asset_url: str) -> str:
    pinned = ARCHIVE_SHA256.get((version, target))
    if pinned:
        return pinned
    # "<hex>  <file name>"
    return _fetch(asset_url + ".sha256").decode().split()[0].lower()


def _extract_binary(data: bytes, target: str) -> bytes:
    binary_name = _binary_name(target)
    if "windows" in target:
        # v0.7.0-rc2: root level; older releases: in a directory
        candidates = [
            binary_name,
            f"typst-ts-{target}/{binary_name}",
            f"typst-ts-{target}/bin/{binary_name}",
        ]
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in candidates:
                if name in zf.namelist():
                    return zf.read(name)
            available = [n for n in zf.namelist() if "typst-ts-cli" in n]
    else:
        candidates = [
            f"typst-ts-{target}/bin/{binary_name}",   # v0.6.0 and earlier
            f"typst-ts-{target}/{binary_name}",       # v0.7.0-rc2 and later
        ]
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for name in candidates:
                try:
                    member = tar.getmember(name)
                except KeyError:
                    continue
                fileobj = tar.extractfile(member)
                if fileobj is not None:
                    return fileobj.read()
            available = [m.name for m in tar.getmembers() if "typst-ts-cli" in m.name]
    raise RuntimeError(
        f"Could not find typst-ts-cli binary in archive. "
        f"Tried: {candidates}. Available files: {available}"
    )


def download_typst_ts_cli(
    version: str = DEFAULT_VERSION,
    target: str | None = None,
    output_dir: str | None = None,
    quiet: bool = False,
) -> str:
    """Download, verify (SHA-256) and extract typst-ts-cli.

    Args:
        version: typst.ts release tag
        target: Rust target triple (default: current platform)
        output_dir: Directory for the binary (default: typ2pptx/data/bin/)
        quiet: Do not print progress

    Returns:
        Path to the extracted binary.
    """
    if target is None:
        target = detect_target()
    if output_dir is None:
        output_dir = str(_bundled_dir())

    archive_ext = "zip" if "windows" in target else "tar.gz"
    url = f"{GITHUB_RELEASE_URL}/{version}/typst-ts-{target}.{archive_ext}"

    def log(msg: str) -> None:
        if not quiet:
            print(msg, file=sys.stderr)

    log(f"Downloading {url} ...")
    data = _fetch(url)
    digest = hashlib.sha256(data).hexdigest()
    expected = _expected_sha256(version, target, url)
    if digest != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {url}: expected {expected}, got {digest}"
        )
    binary = _extract_binary(data, target)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / _binary_name(target)
    # Write next to the destination and rename, so concurrent runs never
    # see a half-written binary.
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".typst-ts-cli-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(binary)
        mode = os.stat(tmp).st_mode
        os.chmod(tmp, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp, output_path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    log(f"Installed typst-ts-cli to {output_path}")
    return str(output_path)


def cache_dir() -> Path:
    """Per-user cache directory for downloaded binaries."""
    override = os.environ.get("TYP2PPTX_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "typ2pptx"


def cached_typst_ts_cli(version: str = DEFAULT_VERSION, target: str | None = None) -> Path:
    """Path where the auto-downloaded binary for ``version`` lives."""
    target = target or detect_target()
    return cache_dir() / "typst-ts-cli" / version / target / _binary_name(target)


def find_typst_ts_cli(download: bool = True) -> str:
    """Locate typst-ts-cli, downloading it into the cache if needed.

    Search order:
    1. Bundled binary shipped inside this package (typ2pptx/data/bin/)
    2. System PATH
    3. Per-user cache (downloaded on first use unless TYP2PPTX_NO_DOWNLOAD=1)
    """
    bundled = _bundled_dir() / "typst-ts-cli"
    for candidate in (bundled, bundled.with_suffix(".exe")):
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            return str(candidate)

    system_cli = shutil.which("typst-ts-cli")
    if system_cli:
        return system_cli

    try:
        cached = cached_typst_ts_cli()
    except RuntimeError:
        cached = None
    if cached is not None and cached.is_file():
        return str(cached)

    if (cached is None or not download
            or os.environ.get("TYP2PPTX_NO_DOWNLOAD", "") not in ("", "0")):
        raise FileNotFoundError(
            "typst-ts-cli not found. Install it from "
            "https://github.com/Myriad-Dreamin/typst.ts/releases "
            "or specify its path with --typst-ts-cli"
        )

    print(f"typst-ts-cli not found; downloading {DEFAULT_VERSION} "
          f"(first run only) to {cached.parent}", file=sys.stderr)
    return download_typst_ts_cli(output_dir=str(cached.parent), quiet=True)
