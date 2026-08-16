"""Одна строка зрителю о том, что телевизор уже занят нашим показом.
Зовёт её команда показа перед меню картин (:func:`torrcast.usecases.cast_command._cmd_play`).
"""

# ruff: noqa: F821, F822

from __future__ import annotations

__all__ = ["Entry", "_say_showing"]

from torrcast.ports.module import module
from torrcast.usecases.rank import _hms

for _module_name, _names in {"torrcast.state": ("Entry",)}.items():
    _dependency = module(_module_name)
    globals().update({name: getattr(_dependency, name) for name in _names})


def _say_showing(live: tuple[str, Entry] | None) -> None:
    """Сказать зрителю, что телевизор уже занят НАШИМ показом, и что будет дальше.

    Одна строка человеческими словами и без единого слова из машинного словаря: зритель
    вправе знать, что он сейчас прервёт, ещё до того как ответит на вопрос меню. Раньше
    вторая команда вела себя как первая - молча качала свои раздачи рядом с играющим
    фильмом и обрывала его в момент выбора; ни того, ни другого на экране видно не было.

    Занятость берётся из нашего состояния (:meth:`torrcast.state.State.showing`) и только
    оттуда: спросить сам приёмник значит подключиться к нему вторым сендером и погасить
    показ, который мы как раз и бережём (:class:`torrcast.cast.ChromecastReceiver`).
    """
    if live is None:
        return
    entry = live[1]
    what = f"«{entry.title}»" + (f", {entry.label}" if entry.label else "")
    where = f" на {_hms(entry.pos)}" if entry.pos > 0 else ""
    print(
        f"на телевизоре сейчас идёт {what}{where}. Выберешь картину - этот показ "
        f"прервётся; пока выбираешь, он идёт как шёл.",
        flush=True,
    )
