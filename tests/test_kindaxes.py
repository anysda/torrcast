"""Прибор осей умеет говорить «да»: без этого его «нет» не значит ничего.

🔴 Щуп, который на любом входе отвечает «порога нет», неотличим от сломанного. Поэтому
тут два полюса: на разделимом входе прибор ОБЯЗАН найти порог и назвать его число, на
пересекающемся - обязан вернуть улов ноль. Проверяется и несимметричность меры: порог,
дающий хотя бы одну подмену, не берётся, даже если улов при нём больше.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

SPEC = importlib.util.spec_from_file_location(
    "kindaxes", Path(__file__).resolve().parent.parent / "scripts/kindaxes.py"
)
assert SPEC is not None and SPEC.loader is not None
kindaxes = importlib.util.module_from_spec(SPEC)
sys.modules["kindaxes"] = kindaxes
SPEC.loader.exec_module(kindaxes)

GIB = 1024**3


def _release(label: str, count: int, size: int, pad: bool = True) -> dict[str, Any]:
    """Раздача из `count` одинаковых видеофайлов с голыми номерами."""
    mark = "{:02d}" if pad else "{:d}"
    return {
        "label": label,
        "torrent_name": f"{label} pack",
        "files": [[f"pack/{mark.format(i)}.mkv", size] for i in range(1, count + 1)],
    }


def _axes(rows: list[dict[str, Any]]) -> list[Any]:
    found = [kindaxes.axes_of(row) for row in rows]
    return [row for row in found if row is not None]


def test_a_separable_corpus_makes_the_probe_name_the_edge() -> None:
    """Серии по 26 файлов против франшиз по 4: порог есть, и он обязан найтись."""
    rows = _axes(
        [
            *[_release("S", 26, GIB) for _ in range(5)],
            *[_release("F", 4, 8 * GIB) for _ in range(5)],
        ]
    )
    edge, caught, missed = kindaxes.best_cut(rows, lambda r: float(r.videos), above=True)
    assert caught == 5, "прибор не нашёл разделения там, где оно есть"
    assert missed == 0
    assert 5 <= edge <= 26


def test_an_overlapping_corpus_yields_no_edge_at_all() -> None:
    """Франшиза из 26 частей закрывает ось: безопасного порога нет, улов ноль."""
    rows = _axes(
        [
            *[_release("S", 26, GIB) for _ in range(5)],
            *[_release("F", 26, 8 * GIB) for _ in range(5)],
        ]
    )
    _edge, caught, missed = kindaxes.best_cut(rows, lambda r: float(r.videos), above=True)
    assert caught == 0, "прибор назвал порог, который называет франшизу сериалом"
    assert missed == 5


def test_the_edge_never_buys_catch_with_a_single_swap() -> None:
    """Порог, ловящий больше ценой одной подмены, отвергается в пользу меньшего улова."""
    rows = _axes(
        [
            *[_release("S", 26, GIB), _release("S", 9, GIB)],
            *[_release("F", 10, 8 * GIB), _release("F", 4, 8 * GIB)],
        ]
    )
    edge, caught, _missed = kindaxes.best_cut(rows, lambda r: float(r.videos), above=True)
    assert caught == 1, "прибор купил улов подменой"
    assert edge > 10


def test_a_bare_number_is_read_with_its_leading_zero() -> None:
    """Ось нулей читает именно запись номера, а не его величину."""
    assert kindaxes._bare_number("pack/01.mkv") == (1, True)
    assert kindaxes._bare_number("pack/1.mkv") == (1, False)
    assert kindaxes._bare_number("pack/Форсаж 4.mkv") == (4, False)
    assert kindaxes._bare_number("pack/no digits here.mkv") is None
