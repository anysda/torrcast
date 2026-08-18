"""Зеркало расширенной выдачи добора: своё по русскому имени плюс подписанное добором."""

from __future__ import annotations

from tests.usecases.discover.world import pictures, row
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._second_wider import _second_wider

#: Картина, за которой шли: фильм Шепитько 1977 года.
_ASCENT = row("Восхождение (1977) BDRip 1080p", "a", seeders=20)
#: Однофамилец из широкого латинского поиска: китайская картина 2019 года. Русский
#: запрос до неё не достаёт вовсе - её приносит только имя добора.
_CLIMBERS = row("The Climbers (2019) BDRip 1080p", "b", seeders=33)
_POOL = pictures([_ASCENT, _CLIMBERS])


def test_a_vouched_name_adds_its_half_to_ours() -> None:
    """🔴 Привезённое добором уезжало в мусор ровно тут: берутся ОБЕ половины."""
    about = Origin(title="The Climbers", year=2019)

    wider, vouched = _second_wider(_POOL, "восхождение", "The Climbers", None, about, True)

    assert vouched is True
    assert [p.title for p in wider] == ["Восхождение", "The Climbers"]


def test_a_year_that_argues_leaves_only_what_was_ours() -> None:
    """Справка знает 1977, а под именем добора приехал 2019 - это чужая картина."""
    about = Origin(title="The Climbers", year=1977)

    wider, vouched = _second_wider(_POOL, "восхождение", "The Climbers", None, about, True)

    assert vouched is False
    assert [p.title for p in wider] == ["Восхождение"]


def test_nothing_of_ours_lets_the_top_up_answer_alone() -> None:
    """Русский запрос не нашёл ничего - подписанное именем добора и есть весь ответ."""
    about = Origin(title="The Climbers", year=1977)

    wider, vouched = _second_wider(_POOL, "нет такой картины", "The Climbers", None, about, True)

    assert vouched is False, "год всё ещё спорит - ручательства нет"
    assert [p.title for p in wider] == ["The Climbers"], "своего нет, и брать больше нечего"
