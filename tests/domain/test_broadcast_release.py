"""Зеркало :mod:`torrcast.domain.broadcast_release`: спортивная трансляция по имени."""

from torrcast.domain.broadcast_release import _is_broadcast_release


def test_a_football_broadcast_is_caught_by_its_heading() -> None:
    assert _is_broadcast_release(
        "Футбол. Чемпионат Англии 2026-2027. 3-й тур. Арсенал - Челси [06.09] (2026) HDTV 720р"
    )


def test_a_racing_and_a_fight_night_are_caught_too() -> None:
    assert _is_broadcast_release(
        "Формула 1. S2026. Этап 13. Гран-при Италии. Гонка [06.09] (2026) HDTV 720р"
    )
    assert _is_broadcast_release(
        "Смешанные единоборства. UFC Fight Night 287: Hooker vs. Parnasse [05.09] (2026) WEBRip"
    )


def test_a_picture_named_by_the_same_word_stays() -> None:
    """Слово есть, заголовочной точки нет - это кино, а не трансляция."""
    assert not _is_broadcast_release("Бокс (2010) BDRip")
    assert not _is_broadcast_release("Матч-реванш. Футбол моей юности (1980) DVDRip")


def test_an_ordinary_release_is_not_flagged() -> None:
    assert not _is_broadcast_release("Брат. Часть 2 (2000) BDRip")
    assert not _is_broadcast_release("Интерстеллар / Interstellar (2014) BDRemux 1080p")
