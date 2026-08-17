"""Слова, которыми называется отсев: причина зовётся там, где считается."""

from __future__ import annotations

from torrcast.usecases.rank.drop_reasons import (
    _CODEC,
    _DISC,
    _EXTRAS,
    _HEAVY,
    _HEVC,
    _NO_EPISODE,
    _PINNED,
    _QUIET,
    _SMALL,
    _SOURCE,
    OFF_SEASON,
)

REASONS = (
    OFF_SEASON,
    _NO_EPISODE,
    _DISC,
    _EXTRAS,
    _HEAVY,
    _HEVC,
    _CODEC,
    _SMALL,
    _SOURCE,
    _QUIET,
    _PINNED,
)


def test_the_words_are_the_same_ones_cast_log_prints() -> None:
    """Порядок слов один на весь код: иначе `cast log` объяснял бы отказ иначе."""
    assert OFF_SEASON == "нужного сезона нет"
    assert _NO_EPISODE == "нужной серии нет по имени"
    assert _DISC == "образ диска"
    assert _EXTRAS == "дополнительные материалы, а не сама картина"
    assert _HEAVY == "тяжелее потолка"
    assert _HEVC == "hevc, а сплошного перекода нет"
    assert _CODEC == "кодек не тот"
    assert _SMALL == "кадр ниже 720p по имени"
    assert _SOURCE == "источник не HD"
    assert _QUIET == "имя молчит о качестве"
    assert _PINNED == "релиз назван руками"


def test_no_two_reasons_share_a_word() -> None:
    """Свёртка считает причины ключом: две одинаковые строки слились бы в одну."""
    assert len(set(REASONS)) == len(REASONS)
    assert all(reason for reason in REASONS), "пустая причина читается как «доехала»"
