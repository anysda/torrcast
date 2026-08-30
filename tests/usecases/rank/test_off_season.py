"""Слова, которыми называется отсев: причина зовётся там, где считается."""

from __future__ import annotations

import pytest

from torrcast.usecases.rank.off_season import (
    _codec,
    _disc,
    _extras,
    _heavy,
    _hevc,
    _no_episode,
    _pinned,
    _quiet,
    _small,
    _source,
    off_season,
)


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Слова отсева тут сверяются буква в букву - тест смотрит на сам русский текст."""


def test_the_words_are_the_same_ones_cast_log_prints() -> None:
    """Порядок слов один на весь код: иначе `cast log` объяснял бы отказ иначе."""
    assert off_season() == "нужного сезона нет"
    assert _no_episode() == "нужной серии нет по имени"
    assert _disc() == "образ диска"
    assert _extras() == "дополнительные материалы, а не сама картина"
    assert _heavy() == "тяжелее потолка"
    assert _hevc() == "hevc, а сплошного перекода нет"
    assert _codec() == "кодек не тот"
    assert _small() == "кадр ниже 720p по имени"
    assert _source() == "источник не HD"
    assert _quiet() == "имя молчит о качестве"
    assert _pinned() == "релиз назван руками"


def test_no_two_reasons_share_a_word() -> None:
    """Свёртка считает причины ключом: две одинаковые строки слились бы в одну."""
    reasons = (
        off_season(),
        _no_episode(),
        _disc(),
        _extras(),
        _heavy(),
        _hevc(),
        _codec(),
        _small(),
        _source(),
        _quiet(),
        _pinned(),
    )
    assert len(set(reasons)) == len(reasons)
    assert all(reason for reason in reasons), "пустая причина читается как «доехала»"
