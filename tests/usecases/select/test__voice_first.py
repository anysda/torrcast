"""Очередь по звуку: заявившая русскую дорожку раздача спрашивается раньше молчащей."""

from __future__ import annotations

import pytest

from tests.usecases.select.world import plan, release
from torrcast.domain.args import Args
from torrcast.domain.catalogs.tongue import EN, _choose_tongue
from torrcast.domain.picture import Picture
from torrcast.usecases.select._voice_first import _voice_first

_ASKED = Args(query=["кино"])
_SILENT = release("Us (2019) BDRip 1080p", seeders=90)
_SAID = release("Мы / Us (2019) BDRip 1080p | Дубляж", seeders=20)
_DEAD = release("Мы / Us (2019) BDRip 1080p | Дубляж", seeders=1)


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - очередь под русской ручкой."""


def test_a_release_that_names_a_russian_track_is_asked_before_silent_ones() -> None:
    """🔴 У «Мы» молчащий №1 читался 11-15 с и отпадал, заявивший ждал очереди."""
    queue = plan(_SILENT, _SILENT, _SAID).candidates(_ASKED)

    assert queue == [3, 1, 2]


def test_the_rest_of_the_queue_keeps_its_order() -> None:
    """Вперёд выходят заявившие в своём порядке, прочие за ними в своём."""
    ranked = [_SILENT, _SAID, _SILENT, _SAID]

    assert _voice_first(Picture(title="Мы", year=2019), ranked, [1, 2, 3, 4]) == [2, 4, 1, 3]


def test_a_dead_swarm_does_not_jump_the_queue_by_its_name() -> None:
    """Заявка без роя срок не спасает: мёртвый сид не отдаст и паспорт."""
    assert _voice_first(Picture(title="Мы", year=2019), [_SILENT, _DEAD], [1, 2]) == [1, 2]


def test_a_native_picture_keeps_its_queue() -> None:
    """Своя дорожка отечественной картины именем не подписывается."""
    kitchen = Picture(title="Кухня", year=2012, native=True)
    assert _voice_first(kitchen, [_SILENT, _SAID], [1, 2]) == [1, 2]


def test_the_english_product_keeps_its_queue() -> None:
    """Под английской ручкой заявка русского звука ничего не обещает."""
    _choose_tongue(EN)
    assert _voice_first(Picture(title="Us", year=2019), [_SILENT, _SAID], [1, 2]) == [1, 2]
