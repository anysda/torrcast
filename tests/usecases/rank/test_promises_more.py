"""Стоит ли смотреть на запасной: он обещает HD и больше, чем дал верх."""

from __future__ import annotations

from tests.usecases.rank.releases import media, rel
from torrcast.usecases.rank.promises_more import promises_more


def test_a_bigger_hd_promise_is_worth_a_look() -> None:
    assert promises_more(rel(quality="1080p"), media(height=574, width=1150))


def test_a_promise_no_better_than_the_top_is_not() -> None:
    assert not promises_more(rel(quality="720p"), media())


def test_a_promise_below_hd_is_never_a_spare() -> None:
    assert not promises_more(rel(quality="480p"), media(height=360, width=640))
