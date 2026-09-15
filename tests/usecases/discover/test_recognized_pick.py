"""Зеркало выбора при узнанной картине: она первой со своими раздачами, остальные по тексту."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, row, wire_catalogue
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.usecases.discover.recognized_pick import recognized_pick

_INCEPTION = MapPicture("Начало", 2010, False, "Inception", 2_867_448)
_TYPED = [
    row("Люди Икс: Начало. Росомаха / X-Men Origins: Wolverine (2009) BDRip 1080p", "a"),
    row("Начало / Inception (2010) BDRip 720p", "b"),
]
_NAMED = [
    row("Начало / Inception (2010) BDRip 1080p", "c"),
    row("Inception.2010.2160p.UHD.BluRay.x265", "d"),
    row("Inception: The Cobol Job (2010) WEB-DL 1080p", "e"),
]


def test_the_recognized_picture_leads_with_its_own_releases_from_both_rounds() -> None:
    wire_catalogue()
    pictures, found = recognized_pick("Начало", _TYPED, _NAMED, _INCEPTION)

    assert found[0].title == "Начало"
    assert len(found[0].releases) == 3, "своя раздача из текста и обе из имён; Cobol Job - чужая"
    assert [p.title for p in found[1:]] == ["Люди Икс: Начало. Росомаха"]
    assert len(pictures) >= 3, "пул хранит всё спрошенное"


def test_a_typo_the_indexers_do_not_know_still_finds_the_picture_by_its_names() -> None:
    wire_catalogue()
    _, found = recognized_pick("Начaло", [], _NAMED[:2], _INCEPTION)
    assert [(p.title, len(p.releases)) for p in found] == [("Начало", 2)]


def test_without_a_recognized_picture_or_its_releases_the_text_decides_as_before() -> None:
    wire_catalogue()
    assert recognized_pick("Начало", _TYPED, [], None)[1] == franchise("Начало", _TYPED)
    stranger = MapPicture("Начало", 1970, False, "Nachalo", 3_000)
    assert recognized_pick("Начало", _TYPED, [], stranger)[1] == franchise("Начало", _TYPED)
