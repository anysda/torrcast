"""Общий заголовок показа: кладётся один раз, целиком и не поверх чужого."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.lay_head import lay_head

if TYPE_CHECKING:
    from pathlib import Path


def _head(where: Path, mark: bytes) -> Path:
    ready = where / "готовый.mp4"
    ready.write_bytes(mark)
    return ready


def test_the_head_of_the_show_is_laid_out_whole(tmp_path: Path) -> None:
    """Приёмник читает заголовок один раз: недописанный стоил бы ему всего показа."""
    out = tmp_path / "out"
    out.mkdir()

    lay_head(_head(tmp_path, "параметры".encode()), out)

    assert (out / "init.mp4").read_bytes() == "параметры".encode()
    assert not (out / "init.mp4.part").exists()


def test_the_head_the_show_already_has_is_the_one_that_stays(tmp_path: Path) -> None:
    """Куски с этим заголовком уже уехали - разойтись с ними приёмнику нельзя."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "init.mp4").write_bytes("живой".encode())

    lay_head(_head(tmp_path, "прогретый".encode()), out)

    assert (out / "init.mp4").read_bytes() == "живой".encode()


def test_a_head_that_is_not_there_leaves_the_show_without_one(tmp_path: Path) -> None:
    """Выдумывать заголовок нельзя: лучше его отсутствие, чем чужие параметры."""
    out = tmp_path / "out"
    out.mkdir()

    lay_head(tmp_path / "нет.mp4", out)

    assert not (out / "init.mp4").exists()
    assert not (out / "init.mp4.part").exists(), "недописанный обрывок остался лежать"
