"""Готовит чистый каталог сегментов под новый показ; зовёт сценарий показа."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.stream_pack.forget_playing import forget_playing


def hls_dir(path: str) -> Path:
    """Чистый каталог сегментов. Это tmpfs: фильм на диск не пишем."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    for junk in (
        *directory.glob("v*.ts"),
        *directory.glob("v*.m4s"),
        *directory.glob("init.mp4"),
        *directory.glob("*.m3u8"),
    ):
        junk.unlink(missing_ok=True)
    forget_playing(directory)  # флажок прошлого показа картинку нового не доказывает
    return directory
