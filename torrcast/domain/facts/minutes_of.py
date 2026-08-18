"""Строка хронометража обратно в минуты; зовёт отбор релизов."""

from __future__ import annotations

from torrcast.domain.facts.patterns import _RUNTIME_RE


def minutes_of(runtime: str) -> int:
    """«2 ч 49 мин» → 169 минут; пусто или не разобралось — ноль. Обратное :func:`hms`.

    Число, а не строка, нужно отбору: битрейт релиза считается делением размера на
    длительность, и до сих пор в знаменателе стояла прикидка «фильм это два часа»
    (:data:`torrcast.domain.runtime_guess.RUNTIME_GUESS`). У «Интерстеллара» (2 ч 49 мин) она
    завышает битрейт в 1.4 раза, и честные 1080p отсекались потолком на ровном месте.

    Разбирается именно готовая строка, а не отдельное поле: хронометраж уже приехал в
    справке и уже лежит в её кэше (:func:`_cached`), а лишнее поле пришлось бы заводить
    вместе с миграцией кэша ради того же самого числа.
    """
    match = _RUNTIME_RE.match(runtime.strip())
    if match is None:
        return 0
    hours, rest = match.group(1), match.group(2)
    return int(hours or 0) * 60 + int(rest or 0)
