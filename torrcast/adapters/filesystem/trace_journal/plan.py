"""Поля записи ``warm/plan``: чем кодируют куски живая упаковка и прогрев.

Зовёт её показ один раз на сеанс, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def plan(pack: str, warm: str, spots: tuple[int, ...], preset: str = "", mbit: float = 0.0) -> None:
    """Чем кодирует куски живая упаковка и чем - прогрев, один раз на показ.

    ``pack``/``warm`` - ``copy`` или ``recode``; ``spots`` - номера кусков, которые
    перекодируются точечно (тяжёлые). Запись существует ради одного вопроса: одинаково ли решают два
    производителя кусков одного показа. Разошлись - это видно строкой в ``cast log``, а не
    разбором аргументов ffmpeg постфактум.
    """
    emit(
        "warm", "plan", pack=pack, warm=warm, spots=list(spots), preset=preset, mbit=round(mbit, 2)
    )
