"""Зеркало подсказки типа справке: сериал это или фильм, и когда типа не называют."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, row
from torrcast.domain.args import Args
from torrcast.usecases.discover._asked_kind import _asked_kind

_SERIES = [row("Кухня 6 / Kuhnya 6 (2017) WEB-DL 1080p | 6 сезон, 1-20 из 20")]
_FILM = [row("Психо / Psycho (1960) BDRip 1080p")]


def test_the_kind_of_the_leader_of_the_pool_is_the_hint() -> None:
    """Выдача первого круга уже разобрана - тип берут у её вожака, а не гадают."""
    lead = franchise("кухня", _SERIES)[0]

    assert _asked_kind(lead, Args(query=["кухня"])) is True
    assert _asked_kind(franchise("психо", _FILM)[0], Args(query=["психо"])) is False


def test_an_asked_episode_says_series_even_without_a_pool() -> None:
    """🔴 TC-243. Выдача пуста, но серию назвал человек - это утверждение о сериале."""
    assert _asked_kind(None, Args(query=["клиника", "s1e1"])) is True


def test_silence_about_an_episode_is_not_a_word_about_a_film() -> None:
    """Сериал зовут и без номера: без вожака и без серии тип не назван вовсе."""
    assert _asked_kind(None, Args(query=["дедвуд"])) is None
