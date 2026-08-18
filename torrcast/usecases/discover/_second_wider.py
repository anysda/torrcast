"""Картины после добора: найденные по русскому имени плюс подписанные именем добора."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.usecases.discover._vouched import _vouched


def _second_wider(
    pictures: list[Picture], query: str, alt: str, index: int | None, about: Origin, proven: bool
) -> tuple[list[Picture], bool]:
    """Расширенная выдача добора и ответ гейта: ручается ли за неё само имя добора.

    Спрашивали по-русски - им и выбираем; кластер сшил оба языка по оригиналу.

    🔴 **Привязка к картине.** Латинская раздача («Blue Exorcist - 01 [1080p]») не несёт
    ни русского имени, ни оригинала, поэтому кластеру нечем сшить её с русской картиной,
    а :func:`~torrcast.parse.pick_franchise` по русскому запросу до неё не достаёт.
    Привезённое добором уезжало в мусор ровно здесь: 105 раздач на 33 сида при трёх
    русских с нулём живых. Поэтому берутся ОБЕ половины - и найденная по русскому имени,
    и подписанная самим именем добора, - но вторая лишь тогда, когда за это имя ручается
    справка (:func:`_vouched`).
    """
    mine = pick_franchise(query, pictures)
    theirs = pick_franchise(f"{alt} {index}" if index else alt, pictures)
    vouched = _vouched(theirs, about, proven)
    if not (vouched or not mine):  # за это имя никто не ручается - берём лишь своё
        theirs = []
    return mine + [p for p in theirs if p.key not in {q.key for q in mine}], vouched
