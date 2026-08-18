"""Обход детей одного элемента EBML: чем разбирается матрёшка mkv."""

from __future__ import annotations

from torrcast.domain.frames.mkv.vint import vint


def walk(buf: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    """Дети EBML-элемента: (идентификатор, размер, смещение данных)."""
    found: list[tuple[int, int, int]] = []
    i = start
    while i < end:
        try:
            ident, after = vint(buf, i, keep_marker=True)
            size, data = vint(buf, after, keep_marker=False)
        except (ValueError, IndexError):
            return found
        found.append((ident, size, data))
        # Segment длиной с весь фильм в голову не влез: его дети - да, а вот соседа за
        # ним в этом куске уже нет, и шагать туда вслепую нельзя.
        if data + size > len(buf):
            return found
        i = data + size
    return found
