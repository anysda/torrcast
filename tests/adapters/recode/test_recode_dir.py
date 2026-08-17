"""Каталог перекодированных кусков: имя, по которому его находят обе стороны."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.recode.recode_dir import RECODE_DIR


def test_the_name_is_the_one_both_sides_build_their_path_from() -> None:
    """Кодировщик кладёт кусок в этот каталог, а выкладка берёт его оттуда же.

    Разойдись имя хоть в букве - перекод будет готов, а показ его не найдёт и отпустит
    тяжёлую копию.
    """
    assert RECODE_DIR == "recode"
    assert Path("/show") / RECODE_DIR == Path("/show/recode")
