"""Честная строка про картину опоздавшего индексера, которой в меню не было."""

from __future__ import annotations

from tests.usecases.reinforce.stand import Said, pictures, releases, row
from torrcast.usecases.reinforce._foreign_note import KIN_SHOWN, _foreign_note

_GUEST = [row("Другое / Other (2001) BDRip 1080p", "d", indexer="Nyaa.si")]


def test_the_late_guest_is_named_out_loud() -> None:
    """🔴 TC-238. В меню её внести уже некому, но и пропасть молча она не вправе."""
    said = Said()

    _foreign_note(releases(_GUEST), frozenset(), said)

    assert "«Nyaa.si» доехал после списка: привёз «Другое» (2001)" in said.text
    assert "в списке её не было, в отбор она не пойдёт" in said.text


def test_a_picture_from_the_menu_gets_no_line() -> None:
    """Сказать про показанную картину «её не было» значило бы соврать человеку."""
    said = Said()
    menu = frozenset({picture.key for picture in pictures(_GUEST)})

    _foreign_note(releases(_GUEST), menu, said)

    assert said.notes == []


def test_a_crowd_of_guests_speaks_in_plural_and_is_cut_short() -> None:
    """Строка одна и короткая: имена сверх трёх складываются в счёт."""
    assert KIN_SHOWN == 3
    said = Said()
    rows = [
        row(f"Картина {n} / Picture {n} (200{n}) BDRip 1080p", chr(97 + n), indexer="Nyaa.si")
        for n in range(5)
    ]

    _foreign_note(releases(rows), frozenset(), said)

    assert said.text.count("«Картина") == KIN_SHOWN, "имён ровно три, остальные счётом"
    assert "и ещё 2 - в списке их не было, в отбор они не пойдут" in said.text


def test_nothing_foreign_means_no_line_at_all() -> None:
    """Лишняя строка на каждом показе обесценивает все остальные."""
    said = Said()

    _foreign_note([], frozenset(), said)

    assert said.notes == []
