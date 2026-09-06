"""Зеркало :func:`torrcast.usecases.reinforce._aside._aside`."""

from __future__ import annotations

from tests.usecases.reinforce.stand import pictures, releases, row
from torrcast.domain.picture import Picture
from torrcast.usecases.reinforce._aside import _aside

_MINE = row("Врата Штейна / Steins;Gate [S01 + Specials + ONA] (2011-2014) BDRip", "a", seeders=40)
_WIDE = row("Steins;Gate - AniLiberty.TOP [BDRip 1080p][HEVC][1-25]", "b", seeders=61)
_ALIEN = row("Врата Штейна 0 / Steins;Gate 0 [TV] [23 из 23] (2018) BDRip 1080p", "c", seeders=12)


def _found() -> list[Picture]:
    """Картина меню - ровно та, что собрал первый круг."""
    return pictures([_MINE])


def test_the_rejected_topup_is_kept_aside_instead_of_thrown_away() -> None:
    """Раздача той же картины из отвергнутого добора не пропадает, а ложится в карман."""
    found = _found()

    put = _aside(found, releases([_MINE, _WIDE]))

    assert put == 1
    assert [r.raw_name for r in found[0].aside] == [_WIDE.title]


def test_what_is_kept_aside_does_not_enter_the_menu_pool() -> None:
    """Меню и очередь остаются ровно теми же: отложенное лежит отдельно от раздач."""
    found = _found()
    was = [r.raw_name for r in found[0].releases]

    _aside(found, releases([_MINE, _WIDE]))

    assert [r.raw_name for r in found[0].releases] == was


def test_a_picture_the_topup_never_touched_gets_nothing() -> None:
    """Своего кластера в широкой выдаче нет - картине не откладывается ничего."""
    found = _found()

    put = _aside(found, releases([_ALIEN]))

    assert put == 0
    assert found[0].aside == []
