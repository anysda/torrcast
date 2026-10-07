#!/usr/bin/env python3
"""Refresh the local JacRed catalogue without ever calling its search API.

The publisher exposes the FileDB archive at this URL for self-hosted copies.  This
small updater only downloads that archive, builds a replacement SQLite file beside
the live one, and lets :mod:`jacred-index` publish it atomically.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, cast

ARCHIVE = "https://jacred.su/database/latest.tar.zst"
BUILDER = Path(__file__).with_name("jacred-index.py")


class Builder(Protocol):
    def build(self, source: Path, target: Path) -> tuple[int, float]: ...


def _builder() -> Builder:
    spec = importlib.util.spec_from_file_location("jacred_index", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Builder, module)


def _etag_file(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".etag")


def refresh(target: Path) -> tuple[int, float] | None:
    """Fetch, unpack and atomically replace ``target``; keep the former index on errors."""
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    etag_file = _etag_file(target)
    headers = {"If-None-Match": etag_file.read_text().strip()} if etag_file.is_file() else {}
    request = urllib.request.Request(ARCHIVE, headers=headers)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix="refresh-") as temporary:
        work = Path(temporary)
        archive = work / "latest.tar.zst"
        try:
            with (
                urllib.request.urlopen(request, timeout=1800) as response,
                archive.open("wb") as out,
            ):
                shutil.copyfileobj(response, out)
                etag = response.headers.get("ETag")
        except urllib.error.HTTPError as error:
            if error.code == 304:
                return None
            raise
        source = work / "filedb"
        source.mkdir()
        subprocess.run(["tar", "--zstd", "-xf", archive, "-C", source], check=True)
        result = _builder().build(source, target)
        if etag:
            etag_file.write_text(etag + "\n")
        else:
            etag_file.unlink(missing_ok=True)
        return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: jacred-update.py INDEX.sqlite")
    result = refresh(Path(sys.argv[1]))
    if result is None:
        print("catalogue unchanged")
    else:
        rows, elapsed = result
        print(f"indexed {rows} releases in {elapsed:.1f} s")
