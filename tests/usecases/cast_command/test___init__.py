"""Зеркало команды показа: перечтение номера сезоном и полнота её внешнего мира."""

from __future__ import annotations

from torrcast.cli.args import Args
from torrcast.domain.cluster import cluster
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.runtime.wire import wire
from torrcast.usecases.cast_command import _cmd_play, _play_state, _season_reread


def _catalog(*names: str) -> list[Picture]:
    """Каталог картин по именам раздач - тем же разбором, что и на боевом пути."""
    return cluster([parse_release_name(name) for name in names])


def test_a_number_by_a_series_name_is_reread_as_its_season() -> None:
    """🔴 TC-363. «кухня 6» - это шестой СЕЗОН, а не шестая картина франшизы.

    Правило целиком: номер отдан сериалам линейки, и запрос переписывается на первую
    серию названного сезона. Разойдись перечтение с показом - планы строились бы по
    первому сезону там, где спрошен шестой.
    """
    pictures = _catalog(
        "Кухня 6 / Kuhnya 6 (2017) WEB-DL 1080p | 6 сезон, 1-20 из 20",
        "Кухня 6 / Kuhnya 6 (2017) SATRip | 6 сезон [1-20 из 20]",
    )
    found = pick_franchise("кухня", pictures)
    reread = _season_reread(Args(query=["кухня", "6"]), "кухня", 6, found, pictures)
    assert reread is not None, "номер при имени сериала обязан стать сезоном"
    assert reread.query == ["кухня", "s6e1"]


def test_a_number_by_a_film_name_stays_a_part_number() -> None:
    """А у фильма сезонов не бывает: «форсаж 5» остаётся пятой картиной линейки."""
    pictures = _catalog(
        "Форсаж / The Fast and the Furious (2001) BDRip 1080p",
        "Форсаж 5 / Fast Five (2011) BDRip 1080p",
    )
    found = pick_franchise("форсаж", pictures)
    assert _season_reread(Args(query=["форсаж", "5"]), "форсаж", 5, found, pictures) is None


def test_the_composition_root_hands_the_command_its_whole_outside_world() -> None:
    """Каждое имя внешнего мира команда получает от корня - или падает на живом показе.

    Слоты объявлены аннотациями и до слова корня пусты: забытый в
    :func:`torrcast.runtime.wire.wire` слот виден здесь, а не ``NameError``'ом посреди
    показа, когда первые куски уже уехали на приёмник. Список берётся у самого модуля,
    поэтому новый слот забыть в этой проверке нельзя.
    """
    wire()
    slots = [name for name in _play_state.__annotations__ if name.startswith("_play_")]
    assert slots, "у команды показа обязаны быть объявленные слоты внешнего мира"
    assert [name for name in slots if not hasattr(_play_state, name)] == []
    assert _cmd_play is not None
