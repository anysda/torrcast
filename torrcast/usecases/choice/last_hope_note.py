"""Строка про последнюю надежду: играем HEVC, потому что другого нет вовсе."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.release import Release
from torrcast.usecases.choice.configure import _environment_port

if TYPE_CHECKING:
    from torrcast.ports.choice_types import _Plan


def last_hope_note(plan: _Plan, release: Release) -> str:
    """Та самая честная строка про последнюю надежду; пусто — путь обычный.

    Печатается ровно тогда, когда показ берёт релиз, попавший в очередь ТОЛЬКО потому,
    что живого кандидата с нужной серией нет вовсе (:func:`hevc_hope`). Человек обязан
    услышать не только «перекодирую целиком» (:func:`torrcast.domain.recode_note.recode_note` скажет
    это следующей строкой), но и ПОЧЕМУ выбран дорогой путь: иначе «Гинтама» на HEVC и
    «Гинтама» на честном 1080p выглядят с экрана одинаково, а стоят разного.

    Строка одна, без числа: считать тут нечего — это не размен качества, а
    единственный оставшийся носитель серии.
    """
    if not (plan.last_resort and _environment_port().hevc_hope(release, plan.last_resort)):
        return ""
    what = f"серии {plan.want}" if plan.want else "картины"
    return f"живой раздачи {what} без HEVC нет - беру HEVC последней надеждой"
