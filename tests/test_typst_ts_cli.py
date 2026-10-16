"""Tests for locating / downloading typst-ts-cli (no network access)."""
import hashlib
import io
import os
import tarfile
import zipfile

import pytest

from typ2pptx import typst_ts_cli as tsc

FAKE_BINARY = b"#!/bin/sh\necho typst-ts-cli\n"


def _tar_gz(target, layout="flat"):
    name = (f"typst-ts-{target}/typst-ts-cli" if layout == "flat"
            else f"typst-ts-{target}/bin/typst-ts-cli")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(FAKE_BINARY)
        tar.addfile(info, io.BytesIO(FAKE_BINARY))
    return buf.getvalue()


def _zip(target):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("typst-ts-cli.exe", FAKE_BINARY)
    return buf.getvalue()


@pytest.fixture
def fake_release(monkeypatch):
    """Serve fake archives (and .sha256 files) instead of GitHub."""
    served = {}

    def fetch(url):
        served.setdefault("urls", []).append(url)
        if url.endswith(".sha256"):
            data = served[url[:-len(".sha256")]]
            return f"{hashlib.sha256(data).hexdigest()}  archive\n".encode()
        return served[url]

    monkeypatch.setattr(tsc, "_fetch", fetch)

    def add(version, target, data, pin=True):
        ext = "zip" if "windows" in target else "tar.gz"
        url = f"{tsc.GITHUB_RELEASE_URL}/{version}/typst-ts-{target}.{ext}"
        served[url] = data
        if pin:
            monkeypatch.setitem(tsc.ARCHIVE_SHA256, (version, target),
                                hashlib.sha256(data).hexdigest())
        return url

    add.served = served
    return add


class TestDownload:

    @pytest.mark.parametrize("layout", ["flat", "bin"])
    def test_extracts_and_marks_executable(self, fake_release, tmp_path, layout):
        target = "x86_64-unknown-linux-gnu"
        fake_release("v9", target, _tar_gz(target, layout))
        path = tsc.download_typst_ts_cli("v9", target, str(tmp_path), quiet=True)
        assert open(path, "rb").read() == FAKE_BINARY
        assert os.access(path, os.X_OK)

    def test_windows_zip(self, fake_release, tmp_path):
        target = "x86_64-pc-windows-msvc"
        fake_release("v9", target, _zip(target))
        path = tsc.download_typst_ts_cli("v9", target, str(tmp_path), quiet=True)
        assert path.endswith("typst-ts-cli.exe")
        assert open(path, "rb").read() == FAKE_BINARY

    def test_sha256_mismatch_writes_nothing(self, fake_release, tmp_path, monkeypatch):
        target = "aarch64-apple-darwin"
        fake_release("v9", target, _tar_gz(target))
        monkeypatch.setitem(tsc.ARCHIVE_SHA256, ("v9", target), "0" * 64)
        with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
            tsc.download_typst_ts_cli("v9", target, str(tmp_path), quiet=True)
        assert list(tmp_path.iterdir()) == []

    def test_unpinned_version_uses_release_sha256(self, fake_release, tmp_path):
        target = "aarch64-apple-darwin"
        url = fake_release("v-unpinned", target, _tar_gz(target), pin=False)
        tsc.download_typst_ts_cli("v-unpinned", target, str(tmp_path), quiet=True)
        assert url + ".sha256" in fake_release.served["urls"]

    def test_default_version_is_pinned_for_all_supported_targets(self):
        released = set(tsc.PLATFORM_MAP.values()) - {"i686-pc-windows-msvc"}  # not released
        for target in released:
            assert (tsc.DEFAULT_VERSION, target) in tsc.ARCHIVE_SHA256


class TestFind:

    @pytest.fixture
    def isolated(self, monkeypatch, tmp_path):
        """No bundled binary, nothing on PATH, empty cache."""
        monkeypatch.setattr(tsc, "_bundled_dir", lambda: tmp_path / "bundled")
        monkeypatch.setattr(tsc.shutil, "which", lambda name: None)
        monkeypatch.setattr(tsc, "detect_target", lambda: "x86_64-unknown-linux-gnu")
        monkeypatch.setenv("TYP2PPTX_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.delenv("TYP2PPTX_NO_DOWNLOAD", raising=False)
        return tmp_path

    def test_downloads_once_into_cache(self, isolated, fake_release):
        target = "x86_64-unknown-linux-gnu"
        fake_release(tsc.DEFAULT_VERSION, target, _tar_gz(target))
        first = tsc.find_typst_ts_cli()
        assert first == str(tsc.cached_typst_ts_cli())
        assert first.startswith(str(isolated / "cache"))
        n_fetches = len(fake_release.served["urls"])
        assert tsc.find_typst_ts_cli() == first
        assert len(fake_release.served["urls"]) == n_fetches  # cached

    def test_prefers_bundled_then_path(self, isolated, monkeypatch):
        bundled = isolated / "bundled" / "typst-ts-cli"
        bundled.parent.mkdir()
        bundled.write_bytes(FAKE_BINARY)
        bundled.chmod(0o755)
        assert tsc.find_typst_ts_cli() == str(bundled)
        bundled.unlink()
        monkeypatch.setattr(tsc.shutil, "which", lambda name: "/usr/bin/typst-ts-cli")
        assert tsc.find_typst_ts_cli() == "/usr/bin/typst-ts-cli"

    def test_no_download_env(self, isolated, monkeypatch):
        monkeypatch.setenv("TYP2PPTX_NO_DOWNLOAD", "1")
        with pytest.raises(FileNotFoundError, match="typst-ts-cli not found"):
            tsc.find_typst_ts_cli()
