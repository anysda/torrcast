"""Чем открыть кусок CMAF: голым он не открывается, а вместе со своим заголовком - да."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.stream_pack.piece_with_head import piece_with_head


def test_a_bare_chunk_is_opened_together_with_its_own_head(tmp_path: Path) -> None:
    """🔴 Голый ``moof mdat`` ffmpeg не открывает: ``no tfhd was found``, код возврата 183.

    Ровно поэтому склейка на этом контейнере не выходила НИ РАЗУ - 196 отказов против 26
    удачных на mpegts, - и дело было не в муксере, а во входе.
    """
    head, chunk = tmp_path / "init.mp4", tmp_path / "v7.m4s"
    head.write_bytes(b"h")
    chunk.write_bytes(b"c")

    assert piece_with_head(chunk, head) == f"concat:{head}|{chunk}"


def test_a_head_that_is_not_there_does_not_turn_into_a_guess(tmp_path: Path) -> None:
    """Заголовка нет - кусок идёт как есть: угадывать за выкладку тут нечем."""
    chunk = tmp_path / "v7.m4s"
    chunk.write_bytes(b"c")

    assert piece_with_head(chunk, None) == str(chunk)
    assert piece_with_head(chunk, tmp_path / "нет.mp4") == str(chunk)
