"""Зеркало :mod:`torrcast.usecases.discover.season_reread`: номер запроса как сезон.

Прочтение одно на двоих - круг поиска и офлайн-переигровка щупом, - и мера тут ровно
про то, что оно ОДНО: у сериала номер становится сезоном, у фильма остаётся номером
части линейки.
"""

from __future__ import annotations

from torrcast.domain.args import Args
from torrcast.domain.cluster import cluster
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.usecases.discover.season_reread import _season_asked, season_reread


def _catalog(*names: str) -> list[Picture]:
    return cluster([parse_release_name(name) for name in names])


def test_a_number_by_a_series_name_asks_for_a_season() -> None:
    """🔴 TC-363. У сериала номер это сезон, и решает это сезонная машинерия, а не разбор."""
    pictures = _catalog(
        "Кухня 6 / Kuhnya 6 (2017) WEB-DL 1080p | 6 сезон, 1-20 из 20",
        "Кухня 6 / Kuhnya 6 (2017) SATRip | 6 сезон [1-20 из 20]",
    )

    assert _season_asked(pick_franchise("кухня", pictures), "кухня", pictures) is True


def test_a_number_by_a_film_name_asks_for_nothing_of_the_kind() -> None:
    """У фильма сезонов не бывает - номер остаётся номером части линейки."""
    pictures = _catalog(
        "Форсаж / The Fast and the Furious (2001) BDRip 1080p",
        "Форсаж 5 / Fast Five (2011) BDRip 1080p",
    )

    assert _season_asked(pick_franchise("форсаж", pictures), "форсаж", pictures) is False


def test_an_empty_find_asks_for_nothing() -> None:
    """Картины не нашлось - перечитывать нечего, и сезон тут ни при чём."""
    assert _season_asked([], "кухня", []) is False


def test_the_reread_rewrites_the_query_to_the_first_episode() -> None:
    """Правило сработало - запрос переписывается на первую серию названного сезона."""
    pictures = _catalog("Кухня 6 / Kuhnya 6 (2017) WEB-DL 1080p | 6 сезон, 1-20 из 20")
    found = pick_franchise("кухня", pictures)

    reread = season_reread(Args(query=["кухня", "6"]), "кухня", 6, found, pictures)

    assert reread is not None and reread.query == ["кухня", "s6e1"]


def test_without_a_number_there_is_nothing_to_reread() -> None:
    """Номера в запросе нет - трогать его незачем."""
    pictures = _catalog("Кухня 6 / Kuhnya 6 (2017) WEB-DL 1080p | 6 сезон, 1-20 из 20")
    found = pick_franchise("кухня", pictures)

    assert season_reread(Args(query=["кухня"]), "кухня", None, found, pictures) is None
