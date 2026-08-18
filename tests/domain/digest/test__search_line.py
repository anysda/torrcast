"""Зеркало :mod:`torrcast.domain.digest._search_line`: поиск и отбор одной строкой.

Мера про то, ради чего эти строки заведены: круг по индексерам различает молчунов и
опоздавших, а свёртка отсева обязана сходиться с пулом - иначе разбор отказа врёт.
"""

from __future__ import annotations

from tests.domain.digest.rows import rec
from torrcast.domain.digest._search_line import _search_line

STAMP = "+   0.0с "


def test_an_event_of_another_phase_is_not_this_readers_business() -> None:
    """``None`` тут значит «не моё событие», а не «печатать нечего»."""
    assert _search_line(rec("buffering"), STAMP) is None


def test_the_drop_summary_adds_up_with_the_pool() -> None:
    """Очередь плюс причины отсева обязаны сходиться с пулом, и это видно глазами."""
    told = _search_line(
        rec("queue", phase="select", pool=41, queued=12, dropped={"образ диска": 4, "тяжёлый": 25}),
        STAMP,
    )

    assert told is not None
    assert "пул 41: в очереди 12, выкинуто 29" in told
    assert "образ диска 4" in told


def test_the_silent_indexers_and_the_late_ones_are_different_words() -> None:
    """Опоздавший - не молчун: круг ушёл по кворуму, а он доехал доливом (TC-118).

    Сравняй их - и причина длинного хвоста поиска перестала бы читаться из ленты.
    """
    told = _search_line(
        rec("indexers", phase="search", got={"Rutor": 12}, silent=["Nyaa"], late=["Kinozal"]),
        STAMP,
    )

    assert told is not None
    assert "молчат Nyaa" in told and "опоздали Kinozal" in told


def test_the_time_of_an_indexer_stands_next_to_its_name() -> None:
    """Секунды держатся за именем: у ответившего - после счётчика, у молчуна - вместо него."""
    told = _search_line(
        rec("indexers", phase="search", got={"Rutor": 3}, silent=["Nyaa"], ms={"Nyaa": 8000}),
        STAMP,
    )

    assert told is not None
    assert "Rutor:3" in told and "Nyaa за 8.0 с" in told


def test_an_old_record_without_the_time_field_looks_the_way_it_always_did() -> None:
    """В ленте прежних версий поля ``ms`` нет вовсе - и строка обязана остаться прежней."""
    told = _search_line(rec("indexers", phase="search", got={"Rutor": 3}), STAMP)

    assert told == f"{STAMP}индексеры Rutor:3"


def test_the_runtime_says_whether_the_length_was_known_or_guessed() -> None:
    """Знаменатель битрейта отбора: справка сказала или прикинули (TC-185)."""
    known = _search_line(rec("runtime", phase="select", secs=7200, src="facts"), STAMP)
    guessed = _search_line(rec("runtime", phase="select", secs=7200, src="guess"), STAMP)

    assert known is not None and "2:00:00 - из справки" in known
    assert guessed is not None and "прикидка" in guessed


def test_a_switch_of_the_picture_is_told_as_loudly_as_it_happened() -> None:
    """Смена КАРТИНЫ посреди отбора (TC-203) обязана быть видна в ленте, как на экране."""
    told = _search_line(
        rec("switch", phase="select", **{"from": "Дюна", "to": "Дюна 2", "why": "нет раздач"}),
        STAMP,
    )

    assert told is not None
    assert "у «Дюна» играть нечем (нет раздач) - ухожу к «Дюна 2»" in told
