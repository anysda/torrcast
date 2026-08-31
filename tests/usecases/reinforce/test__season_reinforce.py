"""Круг добора сезон-пака сезонной строкой по оригиналу, прежде чем честно отказать."""

from __future__ import annotations

from typing import Any

from tests.usecases.reinforce.stand import Indexer, Said, franchise, row
from torrcast.domain.args import Args
from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.reinforce._season_reinforce import _season_reinforce

#: Русский запрос принёс сериал, но ни одной раздачи спрошенного сезона.
_FIFTH = [row("Ангел / Angel S05 1080p", "a", seeders=30)]


def _asked(
    client: Indexer, *, found: list[Picture] | None = None, passport: Origin | None = None
) -> tuple[Said, tuple[list[Any], list[Picture], list[Picture]]]:
    said = Said()
    outcome = _season_reinforce(
        client,
        "ангел",
        Args(query=["ангел", "s01e01"]),
        _FIFTH,
        franchise("ангел", _FIFTH) if found is None else found,
        said,
        passport=(lambda *_a, **_k: passport) if passport is not None else None,
    )
    return said, outcome


def test_the_season_pack_is_asked_for_by_the_original_name() -> None:
    """Сезон-пак «Angel S01» русское слово не приносит - его находит сезонная строка."""
    client = Indexer([row("Ангел / Angel S01 1080p", "b", seeders=40)])

    said, (merged, _pictures, wider) = _asked(client)

    assert client.asked == ["Angel S01"]
    assert len(merged) == 2, "выдача склеена, а не заменена"
    assert [(p.title, len(p.releases)) for p in wider] == [("Ангел", 2)]
    assert said.text == "сезона 1 в выдаче не было - добрал по «Angel S01»"


def test_a_namesake_with_another_original_is_not_sewn_to_ours() -> None:
    """🔴 Без гейта «Angel S01» натащил бы десяток чужих аниме под тем же словом."""
    alien = row("Соседка-ангел / The Angel Next Door Spoils Me Rotten S01 1080p", "c", seeders=90)
    client = Indexer([alien])

    said, (merged, _pictures, wider) = _asked(client)

    assert client.asked == ["Angel S01"], "круг был"
    assert merged is _FIFTH, "а брать из него нечего"
    assert [(p.title, len(p.releases)) for p in wider] == [("Ангел", 1)]
    assert said.notes == [], "не добрали - и говорить не о чем"


def test_another_season_of_our_own_series_is_not_counted_as_the_asked_one() -> None:
    """🔴 Своё имя ещё не свой сезон: строка «Angel S01» возвращает и соседние паки.

    Гейт по оригиналу тут пропускает всё - сериал и правда наш, - и без проверки на
    спрошенный сезон третий пак поехал бы в выдачу, а показ сказал бы «добрал сезон 1»
    про сезон, которого так и нет.
    """
    client = Indexer([row("Ангел / Angel S03 1080p", "b", seeders=40)])

    said, (merged, _pictures, wider) = _asked(client)

    assert client.asked == ["Angel S01"], "круг был"
    assert merged is _FIFTH, "а спрошенного сезона в нём нет"
    assert [(p.title, len(p.releases)) for p in wider] == [("Ангел", 1)]
    assert said.notes == [], "хвастаться нечем"


def test_a_spent_goal_cancels_the_circle_and_says_so() -> None:
    """Сезонная строка - такой же второй круг, и цель она тратит так же (TC-228)."""
    client = Indexer([row("Ангел / Angel S01 1080p", "b")], spare=0.0)
    client.over_goal = True

    said, (merged, _pictures, _wider) = _asked(client)

    assert client.asked == []
    assert merged is _FIFTH
    assert said.text == ("not doing добор сезона 1: the search already spent the goal at 10s")


def test_without_a_series_in_the_pool_there_is_nothing_to_reinforce() -> None:
    """Вожака-сериала нет - сезонную строку строить не по чему."""
    movies: list[RawResult] = [row("Кино / Movie (1999) BDRip 1080p", "d")]
    client = Indexer([row("Ангел / Angel S01 1080p", "b")])

    _said, (merged, _pictures, _wider) = _asked(client, found=franchise("кино", movies))

    assert client.asked == []
    assert merged is _FIFTH


def test_a_guessed_passport_is_no_key_for_the_filter() -> None:
    """🔴 Имя, лишь признанное похожим, ключом фильтра быть не вправе (гейт TC-253).

    Оригинала у вожака нет, опора только справка - и её догадка уводит добор за чужой
    картиной под тем же русским словом.
    """
    raw = [row("Ангел S05 1080p", "e", seeders=30)]

    def _ask(about: Origin) -> Indexer:
        client = Indexer([row("Ангел / Angel S01 1080p", "b", seeders=40)])
        _season_reinforce(
            client,
            "ангел",
            Args(query=["ангел", "s01e01"]),
            raw,
            franchise("ангел", raw),
            Said(),
            passport=lambda *_a, **_k: about,
        )
        return client

    vouched = Origin(title="Angel", name="Ангел")

    assert _ask(vouched).asked == ["Angel S01"], "имя, за которое ручаются, строку и строит"
    assert _ask(Origin(title="Angel", guessed=True)).asked == ["angel S01"], (
        "догадке остаётся транслит своих же слов запроса"
    )
