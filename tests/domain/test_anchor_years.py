"""Зеркало :mod:`torrcast.domain.anchor_years`: год бесстрочной половины по чужому оригиналу."""

from torrcast.domain.anchor_years import anchor_years
from torrcast.domain.cluster import cluster
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release

GEASS = "Code Geass: Lelouch of the Rebellion"


def _picture(title: str, year: int | None, original: str | None = None) -> Picture:
    return Picture(
        title=title, year=year, original=original, releases=[Release(raw_name=title, title=title)]
    )


def test_a_yearless_picture_gets_the_year_of_the_one_its_original_names() -> None:
    """Русская половина несёт оригинал - ровную подпись латинской: год у той есть."""
    latin = _picture(GEASS, None)
    anchor_years([latin, _picture("Код Гиас: Восставший Лелуш", 2006, GEASS)])

    assert latin.anchor == 2006


def test_the_anchor_is_order_only_neither_year_nor_key_change() -> None:
    latin = _picture(GEASS, None)
    key = latin.key
    anchor_years([latin, _picture("Код Гиас: Восставший Лелуш", 2006, GEASS)])

    assert latin.year is None and latin.key == key
    assert latin.sort_year == 2006


def test_a_disputed_name_is_not_anchored() -> None:
    """Одно имя оригиналом у картин разных лет - которой верить, каталог не говорит."""
    latin = _picture("The Climbers", None)
    anchor_years(
        [
            latin,
            _picture("Восхождение", 1977, "The Climbers"),
            _picture("Восхождение", 2019, "The Climbers"),
        ]
    )

    assert latin.anchor is None


def test_a_yearless_claimant_claims_nothing() -> None:
    """Год берётся у датированной картины; бесстрочная соседка опорой не бывает."""
    latin = _picture("Code Geass: Lelouch of the Rebellion", None)
    anchor_years([latin, _picture("Код Гиас: Восставший Лелуш", None, GEASS)])

    assert latin.anchor is None


def test_a_yearless_picture_with_its_own_original_is_not_anchored() -> None:
    """У неё есть второе имя - класс дефекта про половину, у которой его нет вовсе."""
    named = _picture("Восставший Лелуш", None, "Code Geass: Lelouch of the Rebellion")
    anchor_years([named, _picture("Код Гиас", 2006, "Code Geass: Lelouch of the Rebellion")])

    assert named.anchor is None


def test_the_anchored_half_stands_right_behind_its_dated_twin_not_ahead() -> None:
    """Один год у половин общий, но первой стоит датированная - она несёт русский голос."""
    found = cluster(
        [
            Release(
                raw_name="Код Гиас: Восставший Лелуш / Code Geass: Lelouch of the Rebellion (2006)",
                title="Код Гиас: Восставший Лелуш",
                original="Code Geass: Lelouch of the Rebellion",
                year=2006,
                magnet="m1",
            ),
            Release(
                raw_name="Code Geass: Lelouch of the Rebellion [1-25] BDRip 1080p",
                title="Code Geass: Lelouch of the Rebellion",
                kind="tv",
                magnet="m2",
            ),
            Release(
                raw_name="Code Geass: Lelouch of the Rebellion [1-25] BDRemux",
                title="Code Geass: Lelouch of the Rebellion",
                kind="tv",
                magnet="m3",
            ),
        ]
    )

    assert [p.title for p in found] == [
        "Код Гиас: Восставший Лелуш",
        "Code Geass: Lelouch of the Rebellion",
    ]


def test_cluster_anchors_the_yearless_half_and_puts_it_before_the_dated_neighbour() -> None:
    """Склейка не сшивает половины (года у латинской нет), но хвостом она больше не едет."""
    found = cluster(
        [
            Release(
                raw_name="Код Гиас: Восставший Лелуш / Code Geass: Lelouch of the Rebellion (2006)",
                title="Код Гиас: Восставший Лелуш",
                original="Code Geass: Lelouch of the Rebellion",
                year=2006,
                magnet="m1",
            ),
            Release(
                raw_name="Code Geass: Lelouch of the Rebellion [1-25] BDRip 1080p",
                title="Code Geass: Lelouch of the Rebellion",
                kind="tv",
                magnet="m2",
            ),
            Release(
                raw_name="Code Geass: Dakkan no Roze S01E01 1080p",
                title="Code Geass: Dakkan no Roze",
                year=2024,
                kind="tv",
                magnet="m3",
            ),
        ]
    )

    latin = next(p for p in found if p.title == "Code Geass: Lelouch of the Rebellion")
    assert latin.anchor == 2006
    assert [p.title for p in found].index("Code Geass: Lelouch of the Rebellion") < [
        p.title for p in found
    ].index("Code Geass: Dakkan no Roze")
