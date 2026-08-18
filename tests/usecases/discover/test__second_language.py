"""Зеркало второго захода латиницей: добор склеивает выдачи и не подменяет картину."""

from __future__ import annotations

from tests.usecases.discover.world import Indexer, Said, franchise, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover._second_language import _second_language

#: Два русских DVDRip'а: пул тощий, и повод переспросить оригиналом есть.
_RU = [row(f"Психо / Psycho (1960) DVDRip {n}", chr(97 + n), seeders=3) for n in range(2)]
#: Сорок латинских 1080p, до которых русский запрос не достаёт.
_LATIN = [row(f"Psycho.1960.1080p.BluRay.x264-GRP{n}", f"z{n}", seeders=60) for n in range(40)]


def _second(
    answers: dict[str, list[RawResult]], about: Origin, query: str = "психо"
) -> tuple[Said, list[RawResult], list[Picture]]:
    wire_catalogue()
    said = Said()
    raw, _pictures, found = _second_language(
        Indexer(answers=answers),
        query,
        Args(query=[query]),
        _RU,
        franchise(query, _RU),
        said,
        passport=lambda *_a, **_k: about,
    )
    return said, raw, found


def test_the_two_answers_are_glued_not_replaced() -> None:
    """Русские имена несут озвучки и оригинал - выбрасывать их добор не вправе."""
    said, raw, found = _second({"psycho": _LATIN}, Origin(title="Psycho", year=1960))

    assert len(raw) == 42
    assert sum(len(p.releases) for p in found) == 42
    assert "по-русски раздач 2 - добрал по «Psycho»: стало 42" in said.text


def test_a_top_up_that_brought_nothing_leaves_the_pool_as_it_was() -> None:
    """Хуже стать не может: добор ничего не дал - остаётся прежний результат целиком."""
    said, raw, found = _second({"psycho": []}, Origin(title="Psycho", year=1960))

    assert len(raw) == 2
    assert [p.title for p in found] == ["Психо"]
    assert "добор по «Psycho» ничего не дал" in said.text


def test_a_guessed_name_of_another_picture_is_not_followed_at_all() -> None:
    """🔴 TC-253. Справка нашла лишь похожее имя - круга по индексерам тут не бывает."""
    about = Origin(title="Psycho", name="Психоз", guessed=True)

    said, raw, _found = _second({"psycho": _LATIN}, about)

    assert len(raw) == 2, "за чужой картиной не идут"
    assert "справка нашла лишь похожее имя «Психоз»" in said.text


def test_the_same_name_twice_pays_for_no_second_circle() -> None:
    """На «cast psycho» оригинал из выдачи - «Psycho»: ходить тем же именем незачем."""
    wire_catalogue()
    said = Said()
    client = Indexer(answers={"psycho": _LATIN})

    _second_language(
        client,
        "psycho",
        Args(query=["psycho"]),
        _RU,
        franchise("психо", _RU),
        said,
        passport=lambda *_a, **_k: Origin(title="Psycho", year=1960),
    )

    assert client.asked == []
