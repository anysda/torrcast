"""Карта опорных кадров: два захода к рою вместо трёх и маленькая голова.

Проверяется не «работает вообще», а цена: у холодной раздачи каждый лишний Range-запрос
и каждый лишний мегабайт головы — это секунды старта (§7.1 SPEC-v2). Поэтому тесты
считают запросы и байты, а не только точки.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast import InfraError
from torrcast.mkv import CUES_CHUNK, HEAD_BYTES, HEAD_PEEK, Reader, keyframes, video_track


@pytest.fixture
def served(clip: str, monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Отдаём файл кусками, как рой: считаем каждый запрос и его размер."""
    body = Path(clip).read_bytes()
    asked: list[tuple[int, int]] = []

    def read(self: Reader, offset: int, size: int) -> bytes:
        asked.append((offset, size))
        data = body[offset : offset + size]
        self.taken += len(data)
        self.requests += 1
        return data

    monkeypatch.setattr(Reader, "read", read)
    return asked


def test_two_requests_and_small_head(served: list[tuple[int, int]], clip: str) -> None:
    """Карта снимается двумя заходами: маленькая голова и один кусок с места Cues."""
    found = keyframes(clip)
    assert [size for _, size in served] == [HEAD_PEEK, CUES_CHUNK]
    assert found.requests == 2
    assert found.duration > 0
    assert found.points
    assert video_track(found.points) in {p.track for p in found.points}


def test_falls_back_to_full_head(
    served: list[tuple[int, int]], clip: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Маленького куска не хватило — берём полную голову, а не сдаёмся."""
    monkeypatch.setattr("torrcast.mkv.HEAD_PEEK", 64)
    keyframes(clip)
    assert [size for _, size in served][:2] == [64, HEAD_BYTES]


def test_not_mkv_is_infra_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Не mkv — честная ошибка, по которой показ берёт ровную сетку."""
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"\x00" * (1 << 16))
    body = junk.read_bytes()

    def read(self: Reader, offset: int, size: int) -> bytes:
        return body[offset : offset + size]

    monkeypatch.setattr(Reader, "read", read)
    with pytest.raises(InfraError):
        keyframes(str(junk))
